import base64
import hashlib
import json

import httpx
import pytest
import respx

from failurelab.fixtures import fixture
from failurelab.runner import run_experiment
from failurelab.runner_service import capture_artifacts
from failurelab.schemas import ExperimentPlan

PNG = b"\x89PNG\r\n\x1a\nowned-capture"


def test_capture_retains_bytes_before_checkout_is_removed(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    image = output / "screenshot.png"
    image.write_bytes(PNG)
    report = json.dumps({"suites": [{"results": [{"attachments": [{"path": str(image)}]}]}]})
    captured = capture_artifacts(report, output, "h1-baseline")
    image.unlink()
    assert len(captured) == 1
    assert base64.b64decode(captured[0].data_base64) == PNG
    assert captured[0].sha256 == hashlib.sha256(PNG).hexdigest()


def test_capture_rejects_files_outside_output_and_oversized_content(tmp_path, monkeypatch):
    from failurelab import runner_service

    image = tmp_path / "private.png"
    image.write_bytes(PNG)
    report = json.dumps({"attachments": [{"path": str(image)}]})
    with pytest.raises(ValueError, match="escaped"):
        capture_artifacts(report, tmp_path / "output", "h1-baseline")
    monkeypatch.setattr(runner_service, "MAX_CAPTURE_BYTES", len(PNG) - 1)
    with pytest.raises(ValueError, match="capture limit"):
        capture_artifacts(report, tmp_path, "h1-baseline")


@pytest.fixture
def remote_payload():
    return {
        "hypothesis_id": "h1",
        "intervention": "restore_response",
        "baseline_passes": 0,
        "intervention_passes": 3,
        "repetitions": 3,
        "verdict": "inconclusive",
        "duration_ms": 20,
        "observations": ["Recorded assertions"],
        "artifacts": ["h1-baseline-0.png"],
        "artifact_payloads": [
            {
                "name": "h1-baseline-0.png",
                "sha256": hashlib.sha256(PNG).hexdigest(),
                "data_base64": base64.b64encode(PNG).decode(),
            }
        ],
    }


def remote_case(settings, store):
    configured = settings.model_copy(update={"runner_url": "https://runner.example"})
    case_id, _ = store.create(fixture("api_contract"))
    plan = ExperimentPlan(hypothesis_id="h1", intervention="restore_response", rationale="Compare")
    return configured, store.get(case_id), plan


@respx.mock
def test_remote_artifacts_are_validated_persisted_and_replayable(settings, store, remote_payload):
    configured, case, plan = remote_case(settings, store)
    respx.post("https://runner.example/experiments").mock(
        return_value=httpx.Response(200, json=remote_payload)
    )
    result = run_experiment(configured, store, case, plan)
    assert result.verdict == "supported"  # Recomputed from counts, not the supplied verdict.
    assert len(result.artifacts) == 1
    assert store.artifact_path(case["id"], result.artifacts[0]).read_bytes() == PNG
    assert "artifact_payloads" not in result.model_dump()
    assert run_experiment(configured, store, case, plan) == result


@pytest.mark.parametrize("damage", ["hash", "declaration", "base64", "oversize"])
@respx.mock
def test_remote_artifact_failures_do_not_write_files(settings, store, remote_payload, damage):
    configured, case, plan = remote_case(settings, store)
    if damage == "hash":
        remote_payload["artifact_payloads"][0]["sha256"] = "0" * 64
    elif damage == "declaration":
        remote_payload["artifacts"] = []
    elif damage == "base64":
        remote_payload["artifact_payloads"][0]["data_base64"] = "invalid!!"
    else:
        configured = configured.model_copy(update={"max_artifact_bytes": 1024})
        remote_payload["artifact_payloads"][0]["data_base64"] = "A" * 5000
    respx.post("https://runner.example/experiments").mock(
        return_value=httpx.Response(200, json=remote_payload)
    )
    with pytest.raises(RuntimeError):
        run_experiment(configured, store, case, plan)
    assert not list((settings.data_dir / "artifacts").glob("**/runner-*"))
