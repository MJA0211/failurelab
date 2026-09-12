import concurrent.futures
import time

import pytest
from sqlalchemy import update

from failurelab.fixtures import fixture, seed
from failurelab.store import cases, redact


def test_idempotent_ingestion_preserves_original(store):
    payload = fixture("overlay")
    first, created = store.create(payload, dedupe_key="delivery-1")
    payload["title"] = "Changed after delivery"
    second, repeated = store.create(payload, dedupe_key="delivery-1")
    assert created and not repeated and first == second
    assert store.get(first)["title"] != payload["title"]
    assert len(store.list()) == 1


def test_competing_workers_claim_once(store):
    case_id, _ = store.create(fixture("overlay"))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(pool.map(lambda _: store.claim(), range(4)))
    assert claims.count(case_id) == 1
    assert claims.count(None) == 3


def test_expired_lease_recovered_and_attempts_bounded(store):
    case_id, _ = store.create(fixture("overlay"))
    assert store.claim() == case_id
    with store.engine.begin() as conn:
        conn.execute(update(cases).where(cases.c.id == case_id).values(lease_until=time.time() - 1))
    assert store.claim() == case_id
    assert store.get(case_id)["attempts"] == 2
    with store.engine.begin() as conn:
        conn.execute(update(cases).where(cases.c.id == case_id).values(lease_until=0, attempts=3))
    assert store.claim() is None
    assert store.get(case_id)["status"] == "failed"
    assert store.retry(case_id)
    assert store.claim() == case_id


def test_replayed_event_not_duplicated(store):
    case_id, _ = store.create(fixture("unknown"))
    store.event(case_id, "collect", "collected", key="same-stage")
    store.event(case_id, "collect", "collected", key="same-stage")
    assert len(store.timeline(case_id)) == 2


@pytest.mark.parametrize("name", ["../secret", "..", "a/b", "C:\\secret", "file:stream", "a%2fb"])
def test_artifact_traversal_rejected(store, name):
    case_id, _ = store.create(fixture("unknown"))
    with pytest.raises(ValueError):
        store.artifact_path(case_id, name)


def test_evidence_redaction_before_storage(store):
    payload = fixture("overlay")
    payload["evidence"][0]["content"] += (
        "\nAuthorization: Bearer ghp_abcdefghijklmnopqrstuvwxyz123456\napi_key=private-key"
    )
    case_id, _ = store.create(payload)
    evidence = store.get(case_id)["payload"]["evidence"][0]
    assert "private-key" not in evidence["content"]
    assert "ghp_" not in evidence["content"]
    assert len(evidence["sha"]) == 64


def test_seed_is_idempotent(store):
    seed(store)
    seed(store)
    assert len(store.list()) == 4


def test_review_is_append_only(store):
    case_id, _ = store.create(fixture("unknown"))
    store.review(case_id, "accepted", "First opinion")
    store.review(case_id, "rejected", "Second opinion")
    assert [r["decision"] for r in store.get_reviews(case_id)] == ["rejected", "accepted"]


def test_redact_keeps_useful_error_text():
    assert redact("Timeout 5000ms: selector not found") == "Timeout 5000ms: selector not found"
