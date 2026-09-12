"""Transactional investigations, leased jobs, append-only events, and content-addressed evidence."""

import hashlib
import json
import re
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import (
    Column,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    and_,
    create_engine,
    event,
    insert,
    or_,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError

from failurelab.config import Settings

metadata = MetaData()
cases = Table(
    "investigations",
    metadata,
    Column("id", String(40), primary_key=True),
    Column("dedupe_key", String(200), unique=True, nullable=False),
    Column("title", Text, nullable=False),
    Column("repository", String(200), nullable=False),
    Column("commit_sha", String(40), nullable=False),
    Column("test_name", Text, nullable=False),
    Column("source", String(30), nullable=False),
    Column("scenario", String(40)),
    Column("status", String(40), nullable=False),
    Column("stage", String(40), nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    Column("lease_until", Float, default=0),
    Column("attempts", Integer, default=0),
    Column("payload", Text, nullable=False),
    Column("result", Text),
    Column("error", Text),
)
events = Table(
    "events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("case_id", String(40), nullable=False, index=True),
    Column("event_key", String(200), unique=True, nullable=False),
    Column("at", String(40), nullable=False),
    Column("stage", String(40), nullable=False),
    Column("message", Text, nullable=False),
    Column("data", Text, nullable=False),
)
reviews = Table(
    "reviews",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("case_id", String(40), nullable=False, index=True),
    Column("at", String(40), nullable=False),
    Column("decision", String(40), nullable=False),
    Column("note", Text, nullable=False),
)


def now() -> str:
    return datetime.now(UTC).isoformat()


def redact(text: str) -> str:
    text = re.sub(
        r"\b(?:gh[pousr]_[A-Za-z0-9_]{16,}|github_pat_[A-Za-z0-9_]{16,}|hf_[A-Za-z0-9]{16,}|sk-[A-Za-z0-9_-]{16,})",
        "[REDACTED]",
        text,
    )
    return re.sub(
        r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?|(?:api[_-]?key|password|secret|token)\s*[:=]\s*)[^\s,;\"}]+",
        r"\1[REDACTED]",
        text,
    )


class Store:
    def __init__(self, settings: Settings):
        settings.prepare()
        self.settings = settings
        args = (
            {"check_same_thread": False, "timeout": 30}
            if settings.db_url.startswith("sqlite")
            else {}
        )
        self.engine = create_engine(settings.db_url, connect_args=args, pool_pre_ping=True)
        if settings.db_url.startswith("sqlite"):

            @event.listens_for(self.engine, "connect")
            def sqlite_setup(connection, _):
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("PRAGMA busy_timeout=30000")

        metadata.create_all(self.engine)

    def close(self):
        self.engine.dispose()

    def create(
        self, payload: dict, *, source="manual", scenario=None, dedupe_key=None
    ) -> tuple[str, bool]:
        case_id = "inv-" + uuid.uuid4().hex[:12]
        key = dedupe_key or case_id
        clean = dict(payload)
        clean["evidence"] = []
        for item in payload["evidence"]:
            entry = dict(item)
            entry["content"] = redact(entry.get("content", ""))
            entry["sha"] = hashlib.sha256(entry["content"].encode()).hexdigest()
            clean["evidence"].append(entry)
        with self.engine.begin() as conn:
            existing = conn.execute(select(cases.c.id).where(cases.c.dedupe_key == key)).scalar()
            if existing:
                return existing, False
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    insert(cases).values(
                        id=case_id,
                        dedupe_key=key,
                        title=redact(payload["title"]),
                        repository=payload["repository"],
                        commit_sha=payload["commit_sha"],
                        test_name=payload["test_name"],
                        source=source,
                        scenario=scenario,
                        status="queued",
                        stage="queued",
                        created_at=now(),
                        updated_at=now(),
                        payload=json.dumps(clean),
                        attempts=0,
                        lease_until=0,
                    )
                )
        except IntegrityError:
            with self.engine.connect() as conn:
                existing = conn.execute(
                    select(cases.c.id).where(cases.c.dedupe_key == key)
                ).scalar_one()
            return existing, False
        self.event(
            case_id, "queued", "Investigation queued. Evidence snapshot preserved.", key="queued"
        )
        return case_id, True

    @staticmethod
    def decode(row):
        item = dict(row._mapping)
        item["payload"] = json.loads(item["payload"])
        item["result"] = json.loads(item["result"]) if item["result"] else None
        item.pop("dedupe_key", None)
        item.pop("lease_until", None)
        return item

    def get(self, case_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(cases).where(cases.c.id == case_id)).first()
        return self.decode(row) if row else None

    def list(self, limit=100) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(cases).order_by(cases.c.created_at.desc()).limit(limit)
            ).all()
        return [self.decode(row) for row in rows]

    def claim(self) -> str | None:
        current = time.time()
        eligible = and_(
            or_(
                cases.c.status == "queued",
                and_(cases.c.status == "running", cases.c.lease_until < current),
            ),
            cases.c.attempts < 3,
        )
        with self.engine.begin() as conn:
            conn.execute(
                update(cases)
                .where(
                    and_(
                        cases.c.status == "running",
                        cases.c.lease_until < current,
                        cases.c.attempts >= 3,
                    )
                )
                .values(
                    status="failed",
                    error="Worker lease expired after three attempts. Inspect events and retry.",
                    updated_at=now(),
                )
            )
            row = conn.execute(
                select(cases.c.id, cases.c.attempts)
                .where(eligible)
                .order_by(cases.c.created_at)
                .limit(1)
            ).first()
            if not row:
                return None
            result = conn.execute(
                update(cases)
                .where(and_(cases.c.id == row.id, eligible))
                .values(
                    status="running",
                    attempts=row.attempts + 1,
                    lease_until=current + self.settings.lease_seconds,
                    updated_at=now(),
                )
            )
            return row.id if result.rowcount == 1 else None

    def heartbeat(self, case_id):
        with self.engine.begin() as conn:
            conn.execute(
                update(cases)
                .where(and_(cases.c.id == case_id, cases.c.status == "running"))
                .values(lease_until=time.time() + self.settings.lease_seconds)
            )

    def event(self, case_id: str, stage: str, message: str, data=None, key=None):
        event_key = f"{case_id}:{key or uuid.uuid4().hex}"
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    insert(events).values(
                        case_id=case_id,
                        event_key=event_key,
                        at=now(),
                        stage=stage,
                        message=redact(message),
                        data=json.dumps(data or {}),
                    )
                )
                conn.execute(
                    update(cases).where(cases.c.id == case_id).values(stage=stage, updated_at=now())
                )
        except IntegrityError:
            pass  # A checkpoint replay must not append the same event twice.

    def timeline(self, case_id):
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(events).where(events.c.case_id == case_id).order_by(events.c.id)
            ).all()
        return [{**dict(r._mapping), "data": json.loads(r.data)} for r in rows]

    def finish(self, case_id, result):
        with self.engine.begin() as conn:
            conn.execute(
                update(cases)
                .where(cases.c.id == case_id)
                .values(
                    status="completed",
                    stage="report",
                    result=json.dumps(result),
                    lease_until=0,
                    updated_at=now(),
                    error=None,
                )
            )

    def fail(self, case_id, error):
        with self.engine.begin() as conn:
            conn.execute(
                update(cases)
                .where(cases.c.id == case_id)
                .values(
                    status="failed", error=redact(error)[:1000], lease_until=0, updated_at=now()
                )
            )
        self.event(case_id, "failed", redact(error)[:1000])

    def retry(self, case_id) -> bool:
        with self.engine.begin() as conn:
            result = conn.execute(
                update(cases)
                .where(and_(cases.c.id == case_id, cases.c.status == "failed"))
                .values(status="queued", error=None, attempts=0, lease_until=0, updated_at=now())
            )
            return result.rowcount == 1

    def review(self, case_id, decision, note):
        with self.engine.begin() as conn:
            conn.execute(
                insert(reviews).values(
                    case_id=case_id, at=now(), decision=decision, note=redact(note)
                )
            )

    def get_reviews(self, case_id):
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(reviews).where(reviews.c.case_id == case_id).order_by(reviews.c.id.desc())
            ).all()
        return [dict(r._mapping) for r in rows]

    def artifact_path(self, case_id: str, name: str):
        if not re.fullmatch(r"inv-[a-f0-9]{12}", case_id):
            raise ValueError("Invalid investigation ID")
        if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,150}", name) or name in {".", ".."}:
            raise ValueError("Invalid artifact name")
        directory = self.settings.data_dir / "artifacts" / case_id
        directory.mkdir(parents=True, exist_ok=True)
        path = (directory / name).resolve()
        if path.parent != directory.resolve():
            raise ValueError("Invalid artifact path")
        return path

    @contextmanager
    def checkpointer(self):
        if self.settings.db_url.startswith("postgresql"):
            from langgraph.checkpoint.postgres import PostgresSaver

            url = self.settings.db_url.replace("postgresql+psycopg://", "postgresql://")
            with PostgresSaver.from_conn_string(url) as saver:
                saver.setup()
                yield saver
        else:
            from langgraph.checkpoint.sqlite import SqliteSaver

            with SqliteSaver.from_conn_string(
                str(self.settings.data_dir / "checkpoints.db")
            ) as saver:
                yield saver
