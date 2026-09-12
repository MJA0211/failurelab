"""Opt-in live-provider acceptance: eight model calls at most; owned fixtures only."""

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from failurelab.agents import PROMPT_VERSION
from failurelab.config import Settings
from failurelab.fixtures import fixture
from failurelab.store import Store
from failurelab.workflow import Worker


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
        "prompt_version": PROMPT_VERSION,
        "vision": settings.model_vision,
        "scope": "Four owned synthetic fixtures; live integration acceptance, not held-out accuracy.",
        "cases": [],
    }
    store = Store(settings)
    try:
        for scenario in ("overlay", "selector", "api_contract", "unknown"):
            case_id, _ = store.create(fixture(scenario), source="demo", scenario=scenario)
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
            }
            summary["cases"].append(row)
            summary["passed"] = len(summary["cases"]) == 4 and all(
                item["passed"] for item in summary["cases"]
            )
            (output / "acceptance.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
            print(json.dumps(row), flush=True)
            if not row["passed"]:
                print("Acceptance stopped at the first failure. Inspect retained local events.")
                break
    finally:
        store.close()
    print(f"Acceptance report: {output / 'acceptance.json'}")
    return 0 if summary.get("passed") else 1


if __name__ == "__main__":
    sys.exit(main())
