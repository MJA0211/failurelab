import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from failurelab.api import create_app
from failurelab.config import Settings
from failurelab.fixtures import fixture


def test_create_read_and_invalid_review(client):
    response = client.post("/api/investigations", json=fixture("overlay"))
    assert response.status_code == 201
    case_id = response.json()["id"]
    case = client.get(f"/api/investigations/{case_id}").json()
    assert case["status"] == "queued"
    assert len(case["events"]) == 1
    assert (
        client.post(
            f"/api/investigations/{case_id}/reviews",
            json={"decision": "accepted", "note": "Looks supported"},
        ).status_code
        == 409
    )
    assert client.get(f"/api/investigations/{case_id}/report").status_code == 409
    assert client.post(f"/api/investigations/{case_id}/retry").status_code == 409


def test_health_config_metrics_and_no_benchmark(client):
    assert client.get("/healthz").json()["status"] == "ok"
    config = client.get("/api/config").json()
    assert config["model_mode"] == "baseline"
    assert "model_api_key" not in config
    assert client.get("/api/metrics").json()["total"] == 0
    assert client.get("/api/evaluations").json()["available"] is False


def test_unknown_ids_are_404(client):
    assert client.get("/api/investigations/missing").status_code == 404
    assert client.get("/api/artifacts/missing/failure.png").status_code == 404


def test_manual_artifact_reference_and_duplicate_ids_rejected(client):
    payload = fixture("overlay")
    payload["evidence"][0]["artifact"] = "private.png"
    assert client.post("/api/investigations", json=payload).status_code == 422
    payload = fixture("overlay")
    payload["evidence"].append(payload["evidence"][0])
    assert client.post("/api/investigations", json=payload).status_code == 422


def test_hostile_origin_and_oversize_body_rejected(client):
    assert (
        client.post(
            "/api/demo",
            json={"scenario": "overlay"},
            headers={"Origin": "https://malicious.example"},
        ).status_code
        == 403
    )
    assert client.post("/api/demo", content=b"x" * 2_000_001).status_code == 413


def test_dns_rebinding_host_is_rejected_on_loopback(client):
    response = client.get(
        "/api/investigations",
        headers={"Host": "attacker.example", "Origin": "http://attacker.example"},
    )
    assert response.status_code == 403


def test_non_loopback_requires_auth():
    with pytest.raises(ValidationError):
        Settings(host="0.0.0.0", api_token="", _env_file=None)


def test_provider_misconfiguration_fails_explicitly():
    with pytest.raises(ValidationError):
        Settings(model_mode="chat", model_api_key="", _env_file=None)


def test_auth_protects_reads_writes_and_artifacts(settings):
    secured = settings.model_copy(
        update={"api_token": __import__("pydantic").SecretStr("private-test-token")}
    )
    with TestClient(create_app(secured), base_url="http://127.0.0.1") as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/api/config").status_code == 401
        assert client.post("/api/demo", json={"scenario": "overlay"}).status_code == 401
        assert (
            client.get(
                "/api/config", headers={"Authorization": "Bearer private-test-token"}
            ).status_code
            == 200
        )
        assert (
            client.get("/api/config", headers={"Authorization": "Bearer wrong"}).status_code == 401
        )


def test_webhook_signature_and_duplicate_delivery(settings):
    from pydantic import SecretStr

    settings = settings.model_copy(
        update={"webhook_secret": SecretStr("webhook-secret"), "github_repositories": "test/repo"}
    )
    event = {
        "action": "completed",
        "repository": {"full_name": "test/repo"},
        "workflow_run": {
            "id": 123,
            "head_sha": "a" * 40,
            "name": "Playwright",
            "conclusion": "failure",
            "run_attempt": 1,
        },
    }
    raw = json.dumps(event).encode()
    signature = "sha256=" + hmac.new(b"webhook-secret", raw, hashlib.sha256).hexdigest()
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
        assert client.post("/api/webhooks/github", content=raw).status_code == 401
        headers = {"X-Hub-Signature-256": signature, "X-GitHub-Event": "workflow_run"}
        first = client.post("/api/webhooks/github", content=raw, headers=headers)
        second = client.post("/api/webhooks/github", content=raw, headers=headers)
        assert first.status_code == 200, first.text
        assert first.json()["created"] and not second.json()["created"]
        assert first.json()["id"] == second.json()["id"]
        assert (
            client.post("/api/webhooks/github", content=raw + b" ", headers=headers).status_code
            == 401
        )


def test_unknown_demo_scenario_rejected(client):
    assert client.post("/api/demo", json={"scenario": "arbitrary_shell"}).status_code == 422


@pytest.mark.parametrize(
    "origin",
    [
        "https://127.0.0.1",
        "http://localhost:5173",
        "http://127.0.0.1:8787",
        "ftp://127.0.0.1",
        "null",
        "http://127.0.0.1:invalid",
        "http://[invalid",
        "http://user@127.0.0.1",
        "http://127.0.0.1/path",
    ],
)
def test_cross_origin_or_malformed_requests_cannot_create_cases(client, origin):
    response = client.post("/api/demo", json={"scenario": "overlay"}, headers={"Origin": origin})
    assert response.status_code == 403
    assert client.get("/api/investigations").json() == []
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"] == "no-store"


def test_same_origin_including_default_port_is_accepted(client):
    response = client.post(
        "/api/demo", json={"scenario": "overlay"}, headers={"Origin": "http://127.0.0.1:80"}
    )
    assert response.status_code == 201


def test_development_proxy_preserves_same_origin(client):
    response = client.post(
        "/api/demo",
        json={"scenario": "overlay"},
        headers={"Host": "localhost:5173", "Origin": "http://localhost:5173"},
    )
    assert response.status_code == 201


def test_testserver_is_not_a_production_host_exception(client):
    assert client.get("/api/investigations", headers={"Host": "testserver"}).status_code == 403


@pytest.mark.parametrize(
    "host", ["[invalid", "localhost:invalid", "user@localhost", "localhost/path"]
)
def test_malformed_host_is_rejected_without_server_error(client, host):
    response = client.get("/api/config", headers={"Host": host})
    assert response.status_code == 403
    assert response.headers["Cache-Control"] == "no-store"


def test_duplicate_origin_headers_are_rejected(client):
    response = client.post(
        "/api/demo",
        json={"scenario": "overlay"},
        headers=[("Origin", "http://127.0.0.1"), ("Origin", "https://attacker.example")],
    )
    assert response.status_code == 403
    assert client.get("/api/investigations").json() == []


def test_non_ascii_bearer_header_is_unauthorized(settings):
    from pydantic import SecretStr

    secured = settings.model_copy(update={"api_token": SecretStr("private-test-token")})
    with TestClient(create_app(secured), base_url="http://127.0.0.1") as client:
        response = client.get("/api/config", headers=[(b"authorization", b"Bearer \xff")])
        assert response.status_code == 401


def test_non_ascii_webhook_signature_is_unauthorized(settings):
    from pydantic import SecretStr

    secured = settings.model_copy(update={"webhook_secret": SecretStr("webhook-secret")})
    with TestClient(create_app(secured), base_url="http://127.0.0.1") as client:
        response = client.post(
            "/api/webhooks/github", content=b"{}", headers=[(b"x-hub-signature-256", b"\xff")]
        )
        assert response.status_code == 401
