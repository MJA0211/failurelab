import json

import pytest
from pydantic import ValidationError

from failurelab.runner_service import RunnerRequest, parse_test_result, validate_manifest


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
