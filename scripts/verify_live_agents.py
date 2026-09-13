"""Opt-in live-provider acceptance: eight model calls at most; owned fixtures only."""

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from failurelab.agents import PROMPT_VERSION, TOOL_DESCRIPTION_VERSION, TOOL_SCHEMA_SHA256
from failurelab.config import Settings
from failurelab.fixtures import fixture
from failurelab.store import Store
from failurelab.workflow import Investigator, Worker


def failure_status(case, timeline, passed):
    if passed:
        return "passed"
    categories = [e["data"]["category"] for e in timeline if e["stage"] == "failure_category"]
    if categories and categories[-1] == "provider_unavailable":
        return "provider_unavailable"
    if case["status"] == "completed" or categories and categories[-1] == "agent_failed":
        return "agent_failed"
    return "test_harness_failed"


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / "var" / "live-acceptance" / uuid4().hex
    try:
        settings = Settings(
            _env_file=root / ".env",
            model_mode="chat",
            data_dir=output,
            database_url="",
            host="127.0.0.1",
            seed_demo=False,
            worker_enabled=False,
            runner_url="",
            runner_token="",
            max_model_calls=2,
            max_experiments=1,
        )
    except Exception:
        print("Live configuration is incomplete or invalid. Check .env locally; no calls made.")
        return 2
    summary = {
        "started_at": datetime.now(UTC).isoformat(),
        "mode": settings.model_mode,
        "model": settings.model_name,
        "provider": settings.model_base_url,
        "prompt_version": PROMPT_VERSION,
        "tool_description_version": TOOL_DESCRIPTION_VERSION,
        "tool_schema_sha256": TOOL_SCHEMA_SHA256,
        "vision": settings.model_vision,
        "implementation_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip(),
        "implementation_dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip()
        ),
        "implementation_sha256": {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in (
                "src/failurelab/fixtures.py",
                "src/failurelab/runner.py",
                "src/failurelab/agents.py",
                "src/failurelab/schemas.py",
                "src/failurelab/workflow.py",
                "scripts/verify_live_agents.py",
            )
        },
        "scope": "Four owned synthetic fixtures; live integration acceptance, not held-out accuracy.",
        "cases": [],
    }
    store = Store(settings)
    try:
        for scenario in ("overlay", "selector", "api_contract", "unknown"):
            case_id, _ = store.create(fixture(scenario), source="demo", scenario=scenario)
            investigator = Investigator(settings, store)
            config = {"configurable": {"thread_id": case_id}}
            # Freeze only investigation-time evidence before either agent runs. Scenario
            # labels and expected outcomes remain in the scoring process, never agent data.
            with store.checkpointer() as saver:
                graph = investigator.graph(saver)
                graph.invoke(
                    {"case_id": case_id, "runtime": investigator.runtime()},
                    config,
                    interrupt_before=["diagnose"],
                )
                frozen = graph.get_state(config)
                if frozen.next != ("diagnose",):
                    raise RuntimeError("Acceptance failed to freeze before diagnosis")
            snapshot = {
                "evidence": frozen.values["evidence"],
                "retrieved": frozen.values["retrieved"],
            }
            snapshot_bytes = json.dumps(snapshot, indent=2).encode()
            (output / f"{case_id}-input.json").write_bytes(snapshot_bytes)
            Worker(settings, store).tick()
            case = store.get(case_id)
            report = case.get("result") or {}
            timeline = store.timeline(case_id)
            calls = sum(event["stage"] == "model_call" for event in timeline)
            usage = report.get("model_usage", [])
            hypotheses = report.get("hypotheses", [])
            experiments = report.get("experiments", [])
            artifacts = {}
            for experiment in experiments:
                for name in experiment["artifacts"]:
                    path = store.artifact_path(case_id, name)
                    if path.is_file() and path.stat().st_size:
                        artifacts[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            checks = {
                "completed": case["status"] == "completed",
                "chat_mode": report.get("versions", {}).get("mode") == "chat",
                "two_live_stages": calls == 2 and len(usage) == 2,
                "expected_cause": bool(hypotheses) and hypotheses[0]["cause"] == scenario,
                "expected_outcome": report.get("outcome")
                == ("inconclusive" if scenario == "unknown" else "supported"),
                "missing_evidence_reported": scenario != "unknown"
                or bool(report.get("missing_evidence")),
                "browser_evidence_or_abstention": (
                    not experiments
                    if scenario == "unknown"
                    else (
                        bool(artifacts)
                        and bool(experiments)
                        and all(
                            e["baseline_passes"] == 0
                            and e["intervention_passes"] == e["repetitions"]
                            and e["verdict"] == "supported"
                            for e in experiments
                        )
                    )
                ),
            }
            row = {
                "scenario": scenario,
                "case_id": case_id,
                "status": failure_status(case, timeline, all(checks.values())),
                "fixture_commit_label": case["commit_sha"],
                "fixture_commit_note": "Synthetic fixture label, not a fetched Git commit; implementation hashes freeze the executable fixture.",
                "original_failure": next(
                    e["content"] for e in snapshot["evidence"] if e["id"] == "e-log"
                ),
                "input_snapshot_sha256": hashlib.sha256(snapshot_bytes).hexdigest(),
                "evidence_ids": [e["id"] for e in snapshot["evidence"]],
                "retrieved_ids": [e["id"] for e in snapshot["retrieved"]],
                "checks": checks,
                "passed": all(checks.values()),
                "metrics": report.get("metrics", {}),
                "observed_causes": [h["cause"] for h in hypotheses],
                "observed_experiments": [
                    {
                        k: e[k]
                        for k in (
                            "intervention",
                            "baseline_passes",
                            "intervention_passes",
                            "repetitions",
                            "verdict",
                        )
                    }
                    for e in experiments
                ],
                "artifact_sha256": artifacts,
                "diagnosis": hypotheses,
                "plan": next((e["data"]["plans"] for e in timeline if e["stage"] == "plan"), []),
                "experiments": experiments,
                "model_usage": [e["data"] for e in timeline if e["stage"] == "model_usage"],
                "provider_errors": [e["data"] for e in timeline if e["stage"] == "provider_error"],
                "error": case["error"],
                "human_review": "pending",
            }
            with store.checkpointer() as saver:
                checkpoint = investigator.graph(saver).get_state(config)
            row["checkpoint"] = {
                "id": checkpoint.config["configurable"].get("checkpoint_id"),
                "next": list(checkpoint.next),
                "created_at": checkpoint.created_at,
            }
            row["agent_diagnosis"] = checkpoint.values.get("diagnosis")
            row["model_call_attempts"] = calls
            (output / f"{case_id}-record.json").write_text(
                json.dumps(
                    {
                        "case": case,
                        "events": timeline,
                        "checkpoint_values": checkpoint.values,
                        "reviews": store.get_reviews(case_id),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            summary["cases"].append(row)
            summary["passed"] = len(summary["cases"]) == 4 and all(
                item["passed"] for item in summary["cases"]
            )
            (output / "acceptance.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
            print(
                json.dumps(
                    {k: row[k] for k in ("scenario", "case_id", "status", "passed", "metrics")}
                ),
                flush=True,
            )
            if not row["passed"]:
                print("Acceptance stopped at the first failure. Inspect retained local events.")
                break
    except Exception as exc:
        summary["passed"] = False
        summary["status"] = "test_harness_failed"
        summary["harness_error"] = type(exc).__name__
        (output / "acceptance.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print("Live acceptance harness failed; inspect retained local state. No pass recorded.")
    finally:
        store.close()
    print(f"Acceptance report: {output / 'acceptance.json'}")
    return 0 if summary.get("passed") else 1


if __name__ == "__main__":
    sys.exit(main())
