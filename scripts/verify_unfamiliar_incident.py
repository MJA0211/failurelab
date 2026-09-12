"""Execute the frozen authored CI incident. Ground truth is never loaded by this script."""

import argparse
import hashlib
import json
import re
import secrets
import subprocess
import threading
import time
import uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from pydantic import SecretStr

from failurelab.agents import Agents, baseline_diagnosis
from failurelab.config import Settings
from failurelab.integrations import GitHub
from failurelab.runner_service import RunnerRequest
from failurelab.store import Store
from failurelab.workflow import Investigator

ROOT = Path(__file__).resolve().parents[1]
REPO = "MJA0211/failurelab-ci-validation"
COMMIT = "92b61b0eb9a55a73886394979d66cc158f3a99e8"
RUN_ID = 34719385585
TEST = "invoice displays the agreed total"
OUTPUT = ROOT / "var/unfamiliar"
DATA = OUTPUT / "workspace"
STATE = OUTPUT / "investigation.json"
BRIDGE_TOKEN = secrets.token_hex(32)


def gh(*args, data=None):
    result = subprocess.run(
        ["gh", *args],
        input=json.dumps(data) if data is not None else None,
        text=True,
        capture_output=True,
        timeout=50,
    )
    if result.returncode:
        raise RuntimeError("GitHub CLI operation failed: " + result.stderr[:500])
    return result.stdout


def dispatch(payload):
    request_id = uuid.uuid4().hex
    gh(
        "api",
        f"repos/{REPO}/actions/workflows/experiment.yml/dispatches",
        "--input",
        "-",
        data={
            "ref": "main",
            "inputs": {"request_id": request_id, "request_json": json.dumps(payload)},
        },
    )
    start = time.monotonic()
    run_id = None
    while time.monotonic() - start < 540:
        if run_id is None:
            runs = json.loads(
                gh("api", f"repos/{REPO}/actions/workflows/experiment.yml/runs?per_page=10")
            )["workflow_runs"]
            match = next(
                (r for r in runs if r["display_title"] == "experiment-" + request_id), None
            )
            if match:
                run_id = match["id"]
                print(
                    f"Real Linux experiment: https://github.com/{REPO}/actions/runs/{run_id}",
                    flush=True,
                )
        else:
            run = json.loads(gh("api", f"repos/{REPO}/actions/runs/{run_id}"))
            if run["status"] == "completed":
                output = OUTPUT / "runner-transfers" / str(run_id)
                output.mkdir(parents=True, exist_ok=True)
                gh(
                    "run",
                    "download",
                    str(run_id),
                    "--repo",
                    REPO,
                    "--name",
                    "experiment-result",
                    "--dir",
                    str(output),
                )
                if run["conclusion"] != "success":
                    raise RuntimeError(
                        f"Linux experiment workflow {run_id} failed; inspect retained runner output"
                    )
                data = json.loads((output / "result.json").read_text(encoding="utf-8"))
                data["environment"]["transport"] = (
                    "GitHub Actions dispatch and artifact return; live runner HTTP executed inside VM"
                )
                return data
        time.sleep(10)
    raise RuntimeError("Linux experiment exceeded the acceptance transport time budget")


app = FastAPI()


@app.post("/experiments")
def experiment(request: RunnerRequest, authorization: str = Header(default="")):
    if not secrets.compare_digest(authorization, "Bearer " + BRIDGE_TOKEN):
        raise HTTPException(401)
    if (request.repository.lower(), request.commit_sha, request.test_name) != (
        REPO.lower(),
        COMMIT,
        TEST,
    ):
        raise HTTPException(403)
    return dispatch(request.model_dump())


def main():
    global STATE, DATA, OUTPUT, RUN_ID
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["collect", "compare", "run"])
    parser.add_argument("--attempt", choices=["1", "2", "3"], default="1")
    parser.add_argument("--run-id", type=int, default=RUN_ID)
    parser.add_argument("--workspace", default="unfamiliar")
    args = parser.parse_args()
    if args.run_id <= 0 or not re.fullmatch(r"[a-z0-9-]{1,50}", args.workspace):
        parser.error("Use a positive run ID and a bounded lowercase workspace name")
    RUN_ID = args.run_id
    OUTPUT = ROOT / "var" / args.workspace
    DATA = OUTPUT / "workspace"
    STATE = OUTPUT / "investigation.json"
    if args.attempt != "1":
        STATE = STATE.with_name(f"investigation-{args.attempt}.json")
    token = gh("auth", "token").strip()
    settings = Settings(
        data_dir=DATA,
        database_url="",
        model_mode="chat",
        seed_demo=False,
        worker_enabled=False,
        github_repositories=REPO,
        github_token=SecretStr(token),
        runner_url="http://127.0.0.1:8790",
        runner_token=SecretStr(BRIDGE_TOKEN),
        max_experiments=1,
        max_model_calls=3,
    )
    store = Store(settings)
    server = None
    try:
        investigator = Investigator(settings, store)
        if args.phase == "collect":
            if STATE.exists():
                raise RuntimeError("Frozen investigation already exists; do not overwrite it")
            client = GitHub(settings)
            try:
                payload = client.describe_run(REPO, RUN_ID)
            finally:
                client.close()
            assert payload["commit_sha"] == COMMIT
            payload["test_name"] = TEST
            case_id, _ = store.create(payload, source="github")
            config = {"configurable": {"thread_id": case_id}}
            with store.checkpointer() as saver:
                graph = investigator.graph(saver)
                graph.invoke(
                    {"case_id": case_id, "started": time.time(), "runtime": investigator.runtime()},
                    config,
                    interrupt_before=["diagnose"],
                )
                state = graph.get_state(config)
                evidence = state.values["evidence"]
                selected = state.values["retrieved"]
                assert state.next == ("diagnose",)
            visible = json.dumps(evidence)
            for forbidden in ["major-units", "price / 100", "root_cause", "expected_intervention"]:
                assert forbidden not in visible, "Ground-truth or repair-control leakage"
            record = {
                "case_id": case_id,
                "evidence": evidence,
                "retrieved": selected,
                "snapshot_sha256": hashlib.sha256(visible.encode()).hexdigest(),
                "model_visible_exclusions_checked": True,
            }
            STATE.write_text(json.dumps(record, indent=2), encoding="utf-8")
            print(
                json.dumps(
                    {
                        "case_id": case_id,
                        "evidence_count": len(evidence),
                        "retrieved_ids": [e["id"] for e in selected],
                        "snapshot_sha256": record["snapshot_sha256"],
                    }
                ),
                flush=True,
            )
        elif args.phase == "compare":
            record = json.loads(STATE.read_text(encoding="utf-8"))
            rows = []
            for name, evidence in [
                ("deterministic", record["evidence"]),
                ("llm_logs", [e for e in record["evidence"] if e["kind"] == "log"]),
                ("llm_retrieval", record["retrieved"]),
            ]:
                started = time.perf_counter()
                usage = []
                if name == "deterministic":
                    result = baseline_diagnosis(evidence)
                else:
                    agents = Agents(settings)
                    result = agents.diagnose(evidence)
                    usage = agents.usage
                row = {
                    "mode": name,
                    "diagnosis": result.model_dump(),
                    "usage": usage,
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                    "evidence_ids": [e["id"] for e in evidence],
                }
                rows.append(row)
                (OUTPUT / "comparisons.json").write_text(
                    json.dumps(rows, indent=2), encoding="utf-8"
                )
                print(
                    json.dumps(
                        {
                            "mode": name,
                            "cause": result.hypotheses[0].cause,
                            "duration_ms": row["duration_ms"],
                        }
                    ),
                    flush=True,
                )
        else:
            record = json.loads(STATE.read_text(encoding="utf-8"))
            server = uvicorn.Server(
                uvicorn.Config(app, host="127.0.0.1", port=8790, access_log=False)
            )
            thread = threading.Thread(target=server.run, daemon=True)
            thread.start()
            for _ in range(50):
                if server.started:
                    break
                time.sleep(0.1)
            assert server.started
            investigator.run(record["case_id"])
            case = store.get(record["case_id"])
            output = {
                "case": case,
                "events": store.timeline(case["id"]),
                "reviews": store.get_reviews(case["id"]),
            }
            destination = (
                "final-investigation.json"
                if args.attempt == "1"
                else f"final-investigation-{args.attempt}.json"
            )
            (OUTPUT / destination).write_text(json.dumps(output, indent=2), encoding="utf-8")
            print(
                json.dumps(
                    {
                        "status": case["status"],
                        "outcome": case["result"]["outcome"],
                        "metrics": case["result"]["metrics"],
                    }
                ),
                flush=True,
            )
    finally:
        if server:
            server.should_exit = True
            thread.join(timeout=10)
        store.close()


if __name__ == "__main__":
    main()
