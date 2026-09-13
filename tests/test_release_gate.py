import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
import respx
from pydantic import SecretStr
from sqlalchemy import update

from failurelab import __version__
from failurelab.agents import AgentOutputError, Agents, ProviderUnavailable
from failurelab.fixtures import fixture
from failurelab.store import cases
from failurelab.workflow import Investigator, Worker


def chat(settings):
    return settings.model_copy(
        update={
            "model_mode": "chat",
            "model_base_url": "https://provider.example/v1",
            "model_api_key": SecretStr("test-provider-secret"),
        }
    )


@respx.mock
@pytest.mark.parametrize("status", [401, 402, 429, 503])
def test_provider_failure_is_distinct_and_has_no_raw_response(settings, store, status):
    respx.post("https://provider.example/v1/chat/completions").mock(
        return_value=httpx.Response(status, text="Authorization: Bearer private-material")
    )
    case_id, _ = store.create(fixture("unknown"))
    assert Worker(chat(settings), store).tick()
    timeline = store.timeline(case_id)
    assert (
        next(e["data"]["category"] for e in timeline if e["stage"] == "failure_category")
        == "provider_unavailable"
    )
    assert (
        next(e["data"]["http_status"] for e in timeline if e["stage"] == "provider_error") == status
    )
    assert not any(e["stage"] in {"model_usage", "diagnose", "experiment"} for e in timeline)
    assert "private-material" not in json.dumps(timeline)
    assert store.get(case_id)["result"] is None


@respx.mock
def test_transport_failure_is_not_model_output(settings, store):
    respx.post("https://provider.example/v1/chat/completions").mock(
        side_effect=httpx.ConnectTimeout("sensitive transport details")
    )
    case_id, _ = store.create(fixture("unknown"))
    with pytest.raises(ProviderUnavailable, match="transport failed"):
        Agents(chat(settings), store, case_id).diagnose(fixture("unknown")["evidence"])
    data = store.timeline(case_id)[-1]["data"]
    assert data["transport_error"] == "ConnectTimeout" and data["http_status"] is None
    assert "sensitive" not in json.dumps(store.timeline(case_id))


@respx.mock
@pytest.mark.parametrize("body", ["not json", "[]", '{"choices": []}'])
def test_http_success_with_invalid_output_is_agent_failure(settings, body):
    respx.post("https://provider.example/v1/chat/completions").mock(
        return_value=httpx.Response(200, text=body)
    )
    with pytest.raises(AgentOutputError):
        Agents(chat(settings)).diagnose(fixture("unknown")["evidence"])


def forbid_work(*args, **kwargs):
    raise AssertionError("Replay attempted new investigation work")


def test_duplicate_replay_preserves_results_and_makes_no_calls(settings, store, monkeypatch):
    case_id, _ = store.create(fixture("unknown"))
    investigator = Investigator(settings, store)
    investigator.run(case_id)
    first, events = store.get(case_id), store.timeline(case_id)
    for stage in ("collect", "diagnose", "plan", "execute"):
        monkeypatch.setattr(investigator, stage, forbid_work)
    investigator.run(case_id)
    investigator.run(case_id)
    assert store.get(case_id) == first
    assert store.timeline(case_id) == events


def test_missing_completed_checkpoint_cannot_restart_inference(settings, store, monkeypatch):
    case_id, _ = store.create(fixture("unknown"))
    investigator = Investigator(settings, store)
    investigator.run(case_id)
    (settings.data_dir / "checkpoints.db").unlink()
    monkeypatch.setattr(investigator, "collect", forbid_work)
    with pytest.raises(RuntimeError, match="checkpoint is missing"):
        investigator.run(case_id)
    assert store.get(case_id)["status"] == "completed"


def test_checkpoint_report_mismatch_is_rejected(settings, store):
    case_id, _ = store.create(fixture("unknown"))
    investigator = Investigator(settings, store)
    investigator.run(case_id)
    preserved = store.get(case_id)["result"]
    with store.engine.begin() as connection:
        connection.execute(
            update(cases).where(cases.c.id == case_id).values(result='{"outcome":"supported"}')
        )
    with pytest.raises(RuntimeError, match="differs from the preserved report"):
        investigator.run(case_id)
    assert store.get(case_id)["result"] != preserved


def test_corrupt_checkpoint_database_fails_closed(settings, store, monkeypatch):
    case_id, _ = store.create(fixture("unknown"))
    (settings.data_dir / "checkpoints.db").write_bytes(b"invalid database")
    monkeypatch.setattr(Investigator, "collect", forbid_work)
    assert Worker(settings, store).tick()
    case = store.get(case_id)
    assert case["status"] == "failed" and case["result"] is None
    assert not any(e["stage"] == "model_call" for e in store.timeline(case_id))


def test_checkpoint_identity_cannot_redirect_execution(settings, store):
    case_id, _ = store.create(fixture("unknown"))
    investigator = Investigator(settings, store)
    config = {"configurable": {"thread_id": case_id}}
    with store.checkpointer() as saver:
        graph = investigator.graph(saver)
        graph.invoke(
            {"case_id": case_id, "runtime": investigator.runtime()},
            config,
            interrupt_before=["diagnose"],
        )
        graph.update_state(config, {"case_id": "inv-000000000000"})
    with pytest.raises(RuntimeError, match="identity is invalid"):
        investigator.run(case_id)
    assert not any(e["stage"] == "model_call" for e in store.timeline(case_id))


def test_cli_version_requires_no_provider_configuration(monkeypatch):
    monkeypatch.setenv("FAILURELAB_MODEL_MODE", "invalid")
    result = subprocess.run(
        [sys.executable, "-m", "failurelab.cli", "--version"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0 and result.stdout.strip() == f"FailureLab {__version__}"


def test_changed_tool_contract_cannot_resume_pending_checkpoint(settings, store, monkeypatch):
    from failurelab import workflow

    case_id, _ = store.create(fixture("unknown"))
    investigator = Investigator(settings, store)
    config = {"configurable": {"thread_id": case_id}}
    with store.checkpointer() as saver:
        investigator.graph(saver).invoke(
            {"case_id": case_id, "runtime": investigator.runtime()},
            config,
            interrupt_before=["diagnose"],
        )
    monkeypatch.setattr(workflow, "TOOL_SCHEMA_SHA256", "d" * 64)
    with pytest.raises(RuntimeError, match="configuration changed"):
        investigator.run(case_id)
    assert not any(e["stage"] == "model_call" for e in store.timeline(case_id))


def test_acceptance_separates_provider_agent_and_harness_failures():
    spec = importlib.util.spec_from_file_location(
        "live_acceptance", Path(__file__).parents[1] / "scripts/verify_live_agents.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    classify = module.failure_status
    assert classify({"status": "completed"}, [], True) == "passed"
    assert classify({"status": "completed"}, [], False) == "agent_failed"
    assert (
        classify(
            {"status": "failed"},
            [{"stage": "failure_category", "data": {"category": "provider_unavailable"}}],
            False,
        )
        == "provider_unavailable"
    )
    assert classify({"status": "failed"}, [], False) == "test_harness_failed"
