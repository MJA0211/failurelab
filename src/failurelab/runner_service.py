"""Deploy ONLY in a disposable Linux VM. This service executes allowlisted repository code.

The API server does not import this module. A single runner handles one experiment at a time;
the VM must be destroyed between untrusted repositories. See docs/runner-protocol.md.
"""

import base64
import hashlib
import json
import os
import re
import secrets
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import Field

from failurelab.runner import verdict
from failurelab.schemas import ExperimentPlan, RunnerArtifact, RunnerResponse, StrictModel

MAX_CAPTURE_BYTES = 6_000_000


def capture_artifacts(report, output_dir, prefix):
    """Retain bounded PNG/trace attachments before the disposable checkout is removed."""
    payloads = []
    total = 0
    if any(p.is_symlink() for p in [output_dir, *output_dir.parents]):
        raise ValueError("Runner output directory must not contain symlinks")
    root = output_dir.resolve()

    def visit(value):
        nonlocal total
        if isinstance(value, dict):
            for attachment in value.get("attachments", []):
                if not isinstance(attachment, dict) or not attachment.get("path"):
                    continue
                path = Path(attachment["path"])
                if path.suffix.lower() not in {".png", ".zip"}:
                    continue
                if not path.is_absolute():
                    raise ValueError("Runner attachment path must be absolute")
                # Refuse links at every level, including links into an otherwise valid root.
                if not path.resolve().is_relative_to(root) or any(
                    p.is_symlink() for p in [path, *path.parents]
                ):
                    raise ValueError("Runner attachment escaped the output directory")
                size = path.stat().st_size
                if not path.is_file() or size > MAX_CAPTURE_BYTES - total or len(payloads) >= 8:
                    raise ValueError("Runner artifact capture limit exceeded")
                data = path.read_bytes()
                if len(data) != size or not data.startswith(
                    b"\x89PNG\r\n\x1a\n" if path.suffix.lower() == ".png" else b"PK\x03\x04"
                ):
                    raise ValueError("Runner attachment has invalid content")
                total += size
                payloads.append(
                    RunnerArtifact(
                        name=f"{prefix}-{len(payloads)}{path.suffix.lower()}",
                        sha256=hashlib.sha256(data).hexdigest(),
                        data_base64=base64.b64encode(data).decode("ascii"),
                    )
                )
            for key, child in value.items():
                if key != "attachments":
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(json.loads(report))
    return payloads


class RunnerRequest(StrictModel):
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    commit_sha: str = Field(pattern=r"^[a-fA-F0-9]{40}$")
    test_name: str = Field(min_length=1, max_length=300)
    plan: ExperimentPlan


def command(args, cwd, env, timeout):
    # No shell and no concatenated repository-supplied commands. The VM is still the boundary:
    # node, package dependencies, Playwright config, and application code are arbitrary code.
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen(
            args, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT, start_new_session=True
        )
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise RuntimeError("Runner command exceeded its time budget") from None
        finally:
            # Playwright web servers must not survive an experiment condition.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        output.seek(0, 2)
        size = output.tell()
        if size > 4_000_000:
            raise RuntimeError("Runner output exceeded 4 MB")
        output.seek(0)
        return process.returncode, output.read().decode("utf-8", errors="replace")


def parse_test_result(report):
    data = json.loads(report)
    records = []

    def visit(suite, prefix=""):
        title = prefix + "/" + suite.get("title", "")
        for spec in suite.get("specs", []):
            for test in spec.get("tests", []):
                results = test.get("results", [])
                if test.get("expectedStatus", "passed") != "passed" or len(results) != 1:
                    raise ValueError(
                        "Expected exactly one non-skipped test execution without retries"
                    )
                records.append(
                    (
                        title + "/" + spec.get("title", "") + "/" + test.get("projectName", ""),
                        results[0].get("status"),
                    )
                )
        for nested in suite.get("suites", []):
            visit(nested, title)

    for suite in data.get("suites", []):
        visit(suite)
    if not records or any(status not in {"passed", "failed", "timedOut"} for _, status in records):
        raise ValueError("No valid test assertions were executed")
    return all(status == "passed" for _, status in records), sorted(name for name, _ in records)


def validate_manifest(path, intervention):
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1:
        raise ValueError("Unsupported runner manifest version")
    mapping = data.get("interventions", {})
    if intervention != "repeat_baseline" and intervention not in mapping:
        raise ValueError("Repository does not declare the requested intervention")
    env = mapping.get(intervention, {}).get("env", {})
    if not isinstance(env, dict) or any(
        not re.fullmatch(r"FAILURELAB_[A-Z0-9_]{1,70}", key)
        or not isinstance(value, str)
        or len(value) > 200
        for key, value in env.items()
    ):
        raise ValueError("Interventions may only set bounded FAILURELAB_ environment values")
    return env


def execute(request: RunnerRequest, manifest_digest: str):
    # Validate again at the execution boundary, including direct/internal callers.
    repository, commit_sha = request.repository, request.commit_sha
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}", repository):
        raise ValueError("Invalid repository name")
    if any(part in {".", ".."} for part in repository.split("/")):
        raise ValueError("Invalid repository name")
    if not re.fullmatch(r"[a-fA-F0-9]{40}", commit_sha):
        raise ValueError("A full commit SHA is required")
    start = time.perf_counter()
    # Credentials and service configuration never enter child environments.
    env = {
        "PATH": os.defpath + ":/usr/local/bin",
        "CI": "1",
        "LANG": "C.UTF-8",
        "PLAYWRIGHT_BROWSERS_PATH": os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/ms-playwright"),
    }
    with tempfile.TemporaryDirectory(prefix="failurelab-run-") as temp:
        root = Path(temp)
        env["HOME"] = str(root / "home")
        Path(env["HOME"]).mkdir()
        for args in (
            ["git", "init", "."],
            [
                "git",
                "-c",
                "protocol.file.allow=never",
                "fetch",
                "--depth=1",
                "--",
                f"https://github.com/{repository}.git",
                commit_sha,
            ],
            ["git", "checkout", "--detach", "FETCH_HEAD"],
        ):
            code, _ = command(args, root, env, 40)
            if code:
                raise RuntimeError("Pinned repository checkout failed")
        _, sha = command(["git", "rev-parse", "HEAD"], root, env, 10)
        if sha.strip().lower() != request.commit_sha.lower():
            raise RuntimeError("Checkout SHA mismatch")
        manifest = root / ".failurelab" / "runner.json"
        if manifest.is_symlink() or not manifest.is_file():
            raise RuntimeError("A reviewed .failurelab/runner.json manifest is required")
        if hashlib.sha256(manifest.read_bytes()).hexdigest() != manifest_digest:
            raise RuntimeError("Runner manifest differs from the operator-reviewed SHA-256")
        intervention_env = validate_manifest(manifest, request.plan.intervention)
        if not (root / "package-lock.json").is_file():
            raise RuntimeError("A package-lock.json is required for reproducibility")
        code, _ = command(
            ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"], root, env, 90
        )
        if code:
            raise RuntimeError("Locked dependency installation failed")
        cli = root / "node_modules" / "@playwright" / "test" / "cli.js"
        if not cli.is_file():
            raise RuntimeError("Repository must declare @playwright/test in its lockfile")
        observations, expected_tests = [], None
        artifacts = []
        counts = {"baseline": 0, "intervention": 0}
        for repetition in range(request.plan.repetitions):
            for condition in ("baseline", "intervention"):
                run_env = {**env, **(intervention_env if condition == "intervention" else {})}
                output_dir = root / ".failurelab-output" / f"{condition}-{repetition}"
                _, output = command(
                    [
                        "node",
                        str(cli),
                        "test",
                        "--grep=" + re.escape(request.test_name),
                        "--retries=0",
                        "--workers=1",
                        "--reporter=json",
                        "--trace=on",
                        "--output=" + str(output_dir),
                    ],
                    root,
                    run_env,
                    30,
                )
                passed, tests = parse_test_result(output)
                if repetition == 0:
                    artifacts.extend(
                        capture_artifacts(
                            output, output_dir, f"{request.plan.hypothesis_id}-{condition}"
                        )
                    )
                if expected_tests is None:
                    expected_tests = tests
                if tests != expected_tests:
                    raise RuntimeError("The intervention changed the selected assertion set")
                counts[condition] += int(passed)
                observations.append(
                    f"{condition} {repetition + 1}: {'PASS' if passed else 'FAIL'}; {len(tests)} unchanged assertions"
                )
        if sum(len(a.data_base64) for a in artifacts) > 8_000_000:
            raise ValueError("Combined runner artifacts exceeded the transfer limit")
        return RunnerResponse(
            hypothesis_id=request.plan.hypothesis_id,
            intervention=request.plan.intervention,
            baseline_passes=counts["baseline"],
            intervention_passes=counts["intervention"],
            repetitions=request.plan.repetitions,
            verdict=verdict(
                counts["baseline"],
                counts["intervention"],
                request.plan.repetitions,
                request.plan.intervention,
            ),
            duration_ms=int((time.perf_counter() - start) * 1000),
            observations=observations,
            artifacts=[a.name for a in artifacts],
            artifact_payloads=artifacts,
            environment={
                "runner": "isolated-repository-runner-v1",
                "commit_sha": sha.strip(),
                "manifest_sha256": manifest_digest,
                "lockfile_sha256": hashlib.sha256(
                    (root / "package-lock.json").read_bytes()
                ).hexdigest(),
            },
        )


def create_runner_app():
    token = os.environ.get("FAILURELAB_RUNNER_TOKEN", "")
    if not token or len(token) < 24:
        raise RuntimeError(
            "Runner requires a random FAILURELAB_RUNNER_TOKEN of at least 24 characters"
        )
    if os.name != "posix":
        raise RuntimeError("Repository runner requires a disposable Linux VM")
    allowlist = json.loads(os.environ.get("FAILURELAB_RUNNER_MANIFESTS", "{}"))
    cache = Path(os.environ.get("FAILURELAB_RUNNER_CACHE", "/tmp/failurelab-results"))
    cache.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    app = FastAPI(title="FailureLab isolated repository runner")

    @app.post("/experiments")
    def experiment(
        request: RunnerRequest,
        authorization: str = Header(default=""),
        idempotency_key: str = Header(default=""),
    ):
        if not secrets.compare_digest(authorization.encode(), ("Bearer " + token).encode()):
            raise HTTPException(401, "Invalid runner credentials")
        digest = allowlist.get(request.repository.lower())
        if not digest:
            raise HTTPException(403, "Repository has no operator-reviewed manifest")
        if not idempotency_key or len(idempotency_key) > 200:
            raise HTTPException(422, "A bounded idempotency key is required")
        key = hashlib.sha256((idempotency_key + request.model_dump_json()).encode()).hexdigest()
        path = cache / (key + ".json")
        if not lock.acquire(blocking=False):
            raise HTTPException(429, "Runner is busy")
        try:
            if path.exists():
                return RunnerResponse.model_validate_json(path.read_text(encoding="utf-8"))
            try:
                result = execute(request, digest)
            except (RuntimeError, ValueError, OSError) as exc:
                raise HTTPException(422, str(exc)[:500]) from exc
            path.write_text(result.model_dump_json(), encoding="utf-8")
            return result
        finally:
            lock.release()

    return app
