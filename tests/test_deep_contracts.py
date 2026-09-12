import io
import json
import zipfile

import httpx
import pytest
import respx
from pydantic import SecretStr

from failurelab.agents import Agents, baseline_diagnosis
from failurelab.fixtures import fixture
from failurelab.integrations import GitHub, IntegrationError, read_archive
from failurelab.runner import run_experiment
from failurelab.schemas import ExperimentPlan
from failurelab.workflow import Investigator, Worker


def test_report_exports_reviews_and_rerun_preserve_history(client):
    case_id = client.post("/api/investigations", json=fixture("unknown")).json()["id"]
    Worker(client.app.state.settings, client.app.state.store).tick()
    assert (
        client.post(
            f"/api/investigations/{case_id}/reviews",
            json={"decision": "needs_evidence", "note": "Need the original browser trace"},
        ).status_code
        == 201
    )
    exported = client.get(f"/api/investigations/{case_id}/report").json()
    assert exported["reviews"][0]["decision"] == "needs_evidence"
    markdown = client.get(f"/api/investigations/{case_id}/report?format=markdown")
    assert markdown.status_code == 200 and "SHA-256" in markdown.text
    assert client.get(f"/api/investigations/{case_id}/report?format=html").status_code == 422
    again = client.post(f"/api/investigations/{case_id}/rerun")
    assert again.status_code == 201
    assert again.json()["id"] != case_id
    assert client.get(f"/api/investigations/{case_id}").json()["status"] == "completed"
    assert client.post(f"/api/investigations/{again.json()['id']}/rerun").status_code == 409


def test_artifact_endpoint_restricts_extensions(client):
    case_id = client.post("/api/demo", json={"scenario": "unknown"}).json()["id"]
    store = client.app.state.store
    store.artifact_path(case_id, "result.json").write_text("{}")
    store.artifact_path(case_id, "code.py").write_text("secret")
    assert client.get(f"/api/artifacts/{case_id}/result.json").status_code == 200
    assert client.get(f"/api/artifacts/{case_id}/code.py").status_code == 404


def test_full_github_collection_pins_attempt_and_commit(settings, store):
    settings = settings.model_copy(update={"github_repositories": "owner/repo"})
    sha = "c" * 40
    paths = []

    def handler(request):
        path = request.url.path
        paths.append(path)
        if path.endswith("/runs/42"):
            return httpx.Response(
                200, json={"head_sha": sha, "name": "Browser CI", "run_attempt": 2}
            )
        if path.endswith("/attempts/2/jobs"):
            return httpx.Response(
                200, json={"jobs": [{"id": 12, "name": "checkout", "conclusion": "failure"}]}
            )
        if path.endswith("/jobs/12/logs"):
            return httpx.Response(
                200, text="locator.click: release-overlay intercepts pointer events"
            )
        if path.endswith("/commits/" + sha):
            return httpx.Response(
                200, json={"files": [{"filename": "src/app.tsx", "patch": "+ fixed overlay"}]}
            )
        if path.endswith("/artifacts"):
            return httpx.Response(200, json={"artifacts": []})
        raise AssertionError(path)

    github = GitHub(settings, httpx.MockTransport(handler))
    payload = github.describe_run("owner/repo", 42)
    case_id, _ = store.create(payload, source="github")
    evidence = github.collect(store.get(case_id), store)
    assert any("/attempts/2/jobs" in p for p in paths)
    assert all(sha in e["source"] for e in evidence if e["kind"] == "code")
    assert all(len(e["sha"]) == 64 for e in evidence)
    assert any(e["kind"] == "log" for e in evidence)
    github.close()


@respx.mock
def test_github_redirect_never_forwards_credentials(settings):
    settings = settings.model_copy(update={"github_token": SecretStr("sensitive-github-token")})
    respx.get("https://api.github.com/download").mock(
        return_value=httpx.Response(
            302, headers={"location": "https://test.blob.core.windows.net/artifact"}
        )
    )

    def storage(request):
        assert "authorization" not in request.headers
        return httpx.Response(200, content=b"log content")

    respx.get("https://test.blob.core.windows.net/artifact").mock(side_effect=storage)
    github = GitHub(settings)
    assert github.download("/download") == b"log content"
    github.close()


def test_nested_trace_and_png_are_preserved_without_extraction(store):
    inner, outer = io.BytesIO(), io.BytesIO()
    with zipfile.ZipFile(inner, "w") as archive:
        archive.writestr("0.trace", '{"type":"action","error":"timeout"}')
    with zipfile.ZipFile(outer, "w") as archive:
        archive.writestr("test/trace.zip", inner.getvalue())
        archive.writestr("../../screenshot.png", b"\x89PNG\r\n\x1a\nowned-test-data")
        archive.writestr("fake.png", b"not a png")
    case_id, _ = store.create(fixture("unknown"))
    evidence = read_archive(outer.getvalue(), store, case_id, "123", 100000)
    assert len(evidence) == 2
    assert {e["kind"] for e in evidence} == {"log", "image"}
    assert all(store.artifact_path(case_id, e["artifact"]).exists() for e in evidence)


@pytest.mark.parametrize("status", [401, 403, 404])
def test_github_access_errors_are_actionable(settings, status):
    github = GitHub(settings, httpx.MockTransport(lambda r: httpx.Response(status)))
    with pytest.raises(IntegrationError, match=f"HTTP {status}"):
        github.get("/anything")
    github.close()


@respx.mock
def test_remote_runner_cannot_self_certify_or_invent_pass_counts(settings, store):
    settings = settings.model_copy(
        update={
            "runner_url": "https://runner.example",
            "runner_token": SecretStr("test-runner-token"),
        }
    )
    case_id, _ = store.create(fixture("overlay"))
    plan = ExperimentPlan(
        hypothesis_id="h1", intervention="remove_overlay", rationale="Test overlay", repetitions=3
    )
    result = {
        "hypothesis_id": "h1",
        "intervention": "remove_overlay",
        "baseline_passes": 0,
        "intervention_passes": 0,
        "repetitions": 3,
        "verdict": "supported",
        "duration_ms": 10,
        "observations": ["failed comparison"],
    }
    endpoint = respx.post("https://runner.example/experiments")
    endpoint.mock(return_value=httpx.Response(200, json=result))
    assert run_experiment(settings, store, store.get(case_id), plan).verdict == "contradicted"
    result["intervention_passes"] = 9
    endpoint.mock(return_value=httpx.Response(200, json=result))
    with pytest.raises(RuntimeError, match="impossible"):
        run_experiment(settings, store, store.get(case_id), plan)
    result["intervention_passes"] = 3
    result["hypothesis_id"] = "h2"
    endpoint.mock(return_value=httpx.Response(200, json=result))
    with pytest.raises(RuntimeError, match="does not match"):
        run_experiment(settings, store, store.get(case_id), plan)


@respx.mock
def test_failed_model_calls_consume_persistent_budget(settings, store):
    settings = settings.model_copy(
        update={
            "model_mode": "chat",
            "model_base_url": "https://models.example/v1",
            "model_api_key": SecretStr("test"),
            "max_model_calls": 1,
        }
    )
    endpoint = respx.post("https://models.example/v1/chat/completions").mock(
        return_value=httpx.Response(500)
    )
    case_id, _ = store.create(fixture("unknown"))
    with pytest.raises(RuntimeError, match="HTTP 500"):
        Agents(settings, store, case_id).diagnose(fixture("unknown")["evidence"])
    with pytest.raises(RuntimeError, match="budget exhausted"):
        Agents(settings, store, case_id).diagnose(fixture("unknown")["evidence"])
    assert endpoint.call_count == 1


@respx.mock
def test_plan_rejects_unknown_hypothesis_and_duplicate_interventions(settings):
    settings = settings.model_copy(
        update={
            "model_mode": "chat",
            "model_base_url": "https://models.example/v1",
            "model_api_key": SecretStr("test"),
        }
    )
    diagnosis = baseline_diagnosis(fixture("overlay")["evidence"])
    plan = {"hypothesis_id": "h2", "intervention": "remove_overlay", "rationale": "test"}
    endpoint = respx.post("https://models.example/v1/chat/completions")
    endpoint.mock(
        return_value=httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps({"experiments": [plan]})}}]}
        )
    )
    with pytest.raises(RuntimeError, match="unknown hypothesis"):
        Agents(settings).plan(diagnosis, fixture("overlay")["evidence"])
    plan["hypothesis_id"] = "h1"
    endpoint.mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps({"experiments": [plan, plan]})}}]},
        )
    )
    with pytest.raises(RuntimeError, match="one intervention"):
        Agents(settings).plan(diagnosis, fixture("overlay")["evidence"])


def test_changed_inference_config_cannot_relabel_existing_checkpoint(settings, store, monkeypatch):
    case_id, _ = store.create(fixture("unknown"), source="demo", scenario="unknown")
    investigator = Investigator(settings, store)
    monkeypatch.setattr(investigator, "plan", lambda _: (_ for _ in ()).throw(RuntimeError("stop")))
    with pytest.raises(RuntimeError):
        investigator.run(case_id)
    changed = Investigator(settings.model_copy(update={"model_name": "different-model"}), store)
    with pytest.raises(RuntimeError, match="configuration changed"):
        changed.run(case_id)


def test_copied_example_environment_is_valid(tmp_path):
    from pathlib import Path

    from failurelab.config import Settings

    source = Path(__file__).resolve().parents[1] / ".env.example"
    assert Settings(_env_file=source).model_mode == "baseline"
