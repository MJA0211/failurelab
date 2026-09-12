import json
import re

import pytest
from pydantic import ValidationError

from failurelab.runner_service import RunnerRequest, parse_test_result, validate_manifest


@pytest.mark.parametrize("test_name", ["--config=/tmp/evil.js", "--help", "checkout [v2].*"])
def test_runner_test_names_cannot_become_command_options(monkeypatch, test_name):
    import hashlib

    from failurelab import runner_service

    manifest = b'{"version":1,"interventions":{"remove_overlay":{"env":{}}}}'
    observed = []

    def fake_command(args, cwd, env, timeout):
        if args[:2] == ["git", "init"]:
            (cwd / ".failurelab").mkdir()
            (cwd / ".failurelab/runner.json").write_bytes(manifest)
            (cwd / "package-lock.json").write_text("{}")
            cli = cwd / "node_modules/@playwright/test/cli.js"
            cli.parent.mkdir(parents=True)
            cli.write_text("// owned contract fixture")
        if args[:2] == ["git", "rev-parse"]:
            return 0, "a" * 40
        if args[0] == "node":
            observed.append(args)
            # Parse the option boundary instead of accepting an unbound second argument.
            grep_values = [arg.partition("=")[2] for arg in args if arg.startswith("--grep=")]
            assert len(grep_values) == 1
            assert re.fullmatch(grep_values[0], test_name)
            assert test_name not in args
            assert not any(arg.startswith("--config=") or arg == "--help" for arg in args)
            return 0, report()
        return 0, ""

    monkeypatch.setattr(runner_service, "command", fake_command)
    request = RunnerRequest(
        repository="owner/repo",
        commit_sha="a" * 40,
        test_name=test_name,
        plan={"hypothesis_id": "h1", "intervention": "remove_overlay", "rationale": "test"},
    )
    runner_service.execute(request, hashlib.sha256(manifest).hexdigest())
    assert len(observed) == request.plan.repetitions * 2


def report(status="passed", expected="passed", results=None):
    return json.dumps(
        {
            "suites": [
                {
                    "title": "checkout",
                    "specs": [
                        {
                            "title": "places order",
                            "tests": [
                                {
                                    "expectedStatus": expected,
                                    "projectName": "chromium",
                                    "results": results or [{"status": status}],
                                }
                            ],
                        }
                    ],
                }
            ]
        }
    )


def test_remote_report_requires_real_unchanged_assertions():
    passed, names = parse_test_result(report())
    assert passed and names == ["/checkout/places order/chromium"]
    assert parse_test_result(report("failed"))[0] is False
    with pytest.raises(ValueError):
        parse_test_result('{"suites": []}')
    with pytest.raises(ValueError):
        parse_test_result(report(expected="skipped"))
    with pytest.raises(ValueError):
        parse_test_result(report(results=[{"status": "failed"}, {"status": "passed"}]))


def test_manifest_cannot_inject_path_or_shell(tmp_path):
    path = tmp_path / "runner.json"
    path.write_text(
        json.dumps(
            {"version": 1, "interventions": {"remove_overlay": {"env": {"PATH": "/malicious"}}}}
        )
    )
    with pytest.raises(ValueError, match="FAILURELAB_"):
        validate_manifest(path, "remove_overlay")
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "interventions": {"remove_overlay": {"env": {"FAILURELAB_DISABLE_OVERLAY": "1"}}},
            }
        )
    )
    assert validate_manifest(path, "remove_overlay") == {"FAILURELAB_DISABLE_OVERLAY": "1"}
    with pytest.raises(ValueError, match="does not declare"):
        validate_manifest(path, "restore_selector")


def test_remote_runner_requires_full_commit_sha():
    with pytest.raises(ValidationError):
        RunnerRequest(
            repository="owner/repo",
            commit_sha="abc1234",
            test_name="checkout",
            plan={"hypothesis_id": "h1", "intervention": "remove_overlay", "rationale": "test"},
        )


def test_runner_rejects_malformed_credentials_before_execution(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from failurelab import runner_service

    token = "runner-test-token-with-24-characters"
    # Exercise only the HTTP contract on Windows; no repository code is executed.
    monkeypatch.setattr(
        runner_service,
        "os",
        SimpleNamespace(
            name="posix",
            environ={
                "FAILURELAB_RUNNER_TOKEN": token,
                "FAILURELAB_RUNNER_CACHE": str(tmp_path / "runner-cache"),
            },
        ),
    )

    def forbidden(*args):
        pytest.fail("Unauthenticated or unreviewed requests must not execute code")

    monkeypatch.setattr(runner_service, "execute", forbidden)
    payload = {
        "repository": "owner/repo",
        "commit_sha": "a" * 40,
        "test_name": "checkout",
        "plan": {"hypothesis_id": "h1", "intervention": "remove_overlay", "rationale": "test"},
    }
    with TestClient(runner_service.create_runner_app()) as client:
        assert (
            client.post(
                "/experiments", json=payload, headers=[(b"authorization", b"Bearer \xff")]
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/experiments", json=payload, headers={"Authorization": "Bearer " + token}
            ).status_code
            == 403
        )
