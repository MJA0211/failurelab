import hashlib
import hmac
import json
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from failurelab import __version__
from failurelab.config import Settings
from failurelab.fixtures import fixture, seed
from failurelab.integrations import GitHub, IntegrationError, npm_metadata
from failurelab.schemas import DemoRequest, Evidence, GitHubImport, InvestigationInput, Review
from failurelab.store import Store
from failurelab.workflow import Worker


def origin_identity(value: str) -> tuple[str, str, int]:
    """Parse a serialized HTTP origin without silently accepting URL credentials or paths."""
    if any(ord(char) <= 32 or ord(char) >= 127 for char in value):
        raise ValueError("Invalid origin characters")
    parsed = urlparse(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.netloc.endswith(":")
        or "\\" in parsed.netloc
    ):
        raise ValueError("Invalid HTTP origin")
    port = parsed.port if parsed.port is not None else (443 if parsed.scheme == "https" else 80)
    return parsed.scheme, parsed.hostname, port


def create_app(settings: Settings | None = None):
    settings = settings or Settings()
    store = Store(settings)
    worker = Worker(settings, store)

    @asynccontextmanager
    async def lifespan(_app):
        if settings.seed_demo:
            seed(store)
        if settings.worker_enabled:
            worker.start()
        yield
        worker.stop()
        store.close()

    app = FastAPI(
        title="FailureLab",
        version=__version__,
        lifespan=lifespan,
        description="Evidence-first CI investigations. Demo execution is limited to owned browser fixtures.",
    )
    app.state.store, app.state.worker, app.state.settings = store, worker, settings

    @app.middleware("http")
    async def boundary(request, call_next):
        try:
            if (
                len(request.headers.getlist("host")) != 1
                or len(request.headers.getlist("origin")) > 1
            ):
                raise ValueError("Ambiguous origin")
            target = origin_identity(f"{request.scope['scheme']}://{request.headers['host']}")
            origin = request.headers.get("origin")
            if origin is not None and origin_identity(origin) != target:
                raise ValueError("Cross-origin request")
        except ValueError:
            return JSONResponse({"detail": "Origin or Host is not allowed"}, status_code=403)
        if settings.host in {"localhost", "127.0.0.1", "::1"} and target[1] not in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            return JSONResponse(
                {"detail": "Host is not allowed for a loopback workspace"}, status_code=403
            )
        if request.method in {"POST", "PUT", "PATCH"}:
            size, chunks = 0, []
            async for chunk in request.stream():
                size += len(chunk)
                if size > 2_000_000:
                    return JSONResponse({"detail": "Request body exceeds 2 MB"}, status_code=413)
                chunks.append(chunk)
            request._body = b"".join(chunks)
        return await call_next(request)

    @app.middleware("http")
    async def response_headers(request, call_next):
        # Registered outside the boundary so rejected requests receive these headers too.
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = (
            "no-store" if request.scope["path"].startswith("/api") else "no-cache"
        )
        return response

    def authorize(authorization: str | None = Header(default=None)):
        token = settings.api_token.get_secret_value()
        if token and not secrets.compare_digest(
            (authorization or "").encode(), ("Bearer " + token).encode()
        ):
            raise HTTPException(401, "An API token is required")

    auth = [Depends(authorize)]

    def case_or_404(case_id):
        case = store.get(case_id)
        if not case:
            raise HTTPException(404, "Investigation not found")
        return case

    @app.get("/healthz")
    def health():
        return {"status": "ok", "version": __version__}

    @app.get("/api/config", dependencies=auth)
    def configuration():
        return {
            "version": __version__,
            "model_mode": settings.model_mode,
            "model_name": settings.model_name
            if settings.model_mode == "chat"
            else "Deterministic signature baseline",
            "retrieval_mode": settings.retrieval_mode,
            "github_configured": bool(settings.allowed_repositories),
            "github_repositories": sorted(settings.allowed_repositories),
            "runner_configured": bool(settings.runner_url),
            "worker_enabled": settings.worker_enabled,
            "max_experiments": settings.max_experiments,
            "max_model_calls": settings.max_model_calls,
            "vision_enabled": settings.model_vision,
            "authentication": bool(settings.api_token.get_secret_value()),
        }

    @app.get("/api/investigations", dependencies=auth)
    def investigations():
        items = store.list()
        return [{k: v for k, v in item.items() if k != "payload"} for item in items]

    @app.get("/api/investigations/{case_id}", dependencies=auth)
    def investigation(case_id: str):
        return {
            **case_or_404(case_id),
            "events": store.timeline(case_id),
            "reviews": store.get_reviews(case_id),
        }

    @app.post("/api/investigations", status_code=201, dependencies=auth)
    def create(payload: InvestigationInput):
        ids = [e.id for e in payload.evidence]
        if len(ids) != len(set(ids)):
            raise HTTPException(422, "Evidence IDs must be unique")
        if any(e.artifact for e in payload.evidence):
            raise HTTPException(422, "Manual input cannot reference server artifact paths")
        case_id, created = store.create(payload.model_dump())
        return {"id": case_id, "created": created}

    @app.post("/api/demo", status_code=201, dependencies=auth)
    def demo(payload: DemoRequest):
        case_id, _ = store.create(
            fixture(payload.scenario), source="demo", scenario=payload.scenario
        )
        return {"id": case_id}

    @app.post("/api/investigations/{case_id}/retry", dependencies=auth)
    def retry(case_id: str):
        case_or_404(case_id)
        if not store.retry(case_id):
            raise HTTPException(409, "Only failed investigations can be retried")
        return {"id": case_id, "status": "queued"}

    @app.post("/api/investigations/{case_id}/rerun", status_code=201, dependencies=auth)
    def rerun(case_id: str):
        case = case_or_404(case_id)
        if case["status"] in {"queued", "running"}:
            raise HTTPException(409, "Wait for the current investigation to finish")
        payload = {**case["payload"], "parent_id": case_id}
        new_id, _ = store.create(payload, source=case["source"], scenario=case["scenario"])
        return {"id": new_id, "parent_id": case_id}

    @app.post("/api/investigations/{case_id}/reviews", status_code=201, dependencies=auth)
    def review(case_id: str, payload: Review):
        if case_or_404(case_id)["status"] != "completed":
            raise HTTPException(409, "Wait for the investigation report before reviewing")
        store.review(case_id, payload.decision, payload.note)
        return {"saved": True}

    @app.get("/api/investigations/{case_id}/report", dependencies=auth)
    def report(case_id: str, format: str = "json"):
        case = case_or_404(case_id)
        if not case["result"]:
            raise HTTPException(409, "Report is not ready")
        if format == "markdown":
            result = case["result"]
            lines = [
                f"# {case['title']}",
                "",
                f"Repository: {case['repository']} · Commit: {case['commit_sha']}",
                f"Mode: {result['versions']['mode']} · Source: {case['source']}",
                "",
                result["summary"],
                "",
                "## Hypotheses",
            ]
            for h in result["hypotheses"]:
                lines += [
                    f"\n### {h['title']} — {h['status']}",
                    h["explanation"],
                    "Evidence: " + ", ".join(h["evidence_ids"]),
                ]
            lines += ["\n## Experiments"]
            for e in result["experiments"]:
                lines += [
                    f"- {e['intervention']}: {e['verdict']}; baseline {e['baseline_passes']}/{e['repetitions']}, intervention {e['intervention_passes']}/{e['repetitions']} passes."
                ]
            lines += ["\n## Evidence"]
            for e in result["evidence"]:
                lines += [f"- {e['id']}: {e['title']} ({e['source']}) SHA-256: {e.get('sha', '')}"]
            lines += [
                "\n## Limits",
                *["- " + x for x in result["limitations"] + result["missing_evidence"]],
            ]
            return PlainTextResponse(
                "\n".join(lines),
                headers={"Content-Disposition": f'attachment; filename="{case_id}.md"'},
            )
        if format != "json":
            raise HTTPException(422, "Choose json or markdown")
        return JSONResponse(
            {
                "investigation": case,
                "events": store.timeline(case_id),
                "reviews": store.get_reviews(case_id),
            },
            headers={"Content-Disposition": f'attachment; filename="{case_id}.json"'},
        )

    @app.get("/api/artifacts/{case_id}/{name}", dependencies=auth)
    def artifact(case_id: str, name: str):
        case_or_404(case_id)
        try:
            path = store.artifact_path(case_id, name)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if not path.exists() or path.suffix not in {".png", ".zip", ".json"}:
            raise HTTPException(404, "Artifact not found")
        return FileResponse(
            path,
            media_type="image/png" if path.suffix == ".png" else "application/octet-stream",
            filename=None if path.suffix == ".png" else name,
        )

    @app.post("/api/integrations/github/import", dependencies=auth)
    def github_import(payload: GitHubImport):
        client = GitHub(settings)
        try:
            data = client.describe_run(payload.repository, payload.run_id)
            if payload.test_name:
                data["test_name"] = payload.test_name
            case_id, created = store.create(
                data,
                source="github",
                dedupe_key=f"github:{payload.repository.lower()}:{payload.run_id}:{data['run_attempt']}",
            )
            return {"id": case_id, "created": created}
        except IntegrationError as exc:
            raise HTTPException(400, str(exc)) from exc
        finally:
            client.close()

    @app.get("/api/integrations/npm", dependencies=auth)
    def package_metadata(package: str, version: str):
        try:
            return npm_metadata(package, version)
        except (ValueError, IntegrationError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/webhooks/github")
    async def github_webhook(request: Request):
        secret = settings.webhook_secret.get_secret_value()
        if not secret:
            raise HTTPException(503, "GitHub webhook is not configured")
        raw = await request.body()
        expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(
            expected.encode(), request.headers.get("x-hub-signature-256", "").encode()
        ):
            raise HTTPException(401, "Invalid webhook signature")
        if request.headers.get("x-github-event") == "ping":
            return {"received": True}
        if request.headers.get("x-github-event") != "workflow_run":
            return {"ignored": True}
        try:
            event = json.loads(raw)
            run = event["workflow_run"]
            if event.get("action") != "completed" or run.get("conclusion") not in {
                "failure",
                "timed_out",
            }:
                return {"ignored": True}
            repo = event["repository"]["full_name"]
            if repo.lower() not in settings.allowed_repositories:
                raise HTTPException(403, "Repository is not allowlisted")
            payload = InvestigationInput(
                title=(run.get("display_title") or run.get("name") or "Workflow failed")[:200],
                repository=repo,
                commit_sha=run["head_sha"],
                test_name=(run.get("name") or "GitHub Actions")[:300],
                evidence=[
                    Evidence(
                        id="e-run",
                        title="Workflow metadata",
                        kind="metadata",
                        content=json.dumps(
                            {"run_id": run["id"], "attempt": run.get("run_attempt", 1)}
                        ),
                        source=run.get("html_url", ""),
                    )
                ],
            ).model_dump()
            payload.update(run_id=run["id"], run_attempt=run.get("run_attempt", 1))
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(422, "Invalid workflow_run payload") from exc
        case_id, created = store.create(
            payload,
            source="github",
            dedupe_key=f"github:{repo.lower()}:{run['id']}:{payload['run_attempt']}",
        )
        return {"id": case_id, "created": created}

    @app.get("/api/evaluations", dependencies=auth)
    def evaluations():
        path = settings.data_dir / "evaluation.json"
        if not path.exists():
            return {
                "available": False,
                "message": "Run uv run failurelab evaluate to produce measured results.",
            }
        return {"available": True, **json.loads(path.read_text(encoding="utf-8"))}

    @app.get("/api/metrics", dependencies=auth)
    def metrics():
        items = store.list(10000)
        completed = [c for c in items if c["status"] == "completed"]
        return {
            "total": len(items),
            "completed": len(completed),
            "running": sum(c["status"] in {"queued", "running"} for c in items),
            "failed": sum(c["status"] == "failed" for c in items),
            "supported": sum(c["result"]["outcome"] == "supported" for c in completed),
            "experiments": sum(len(c["result"]["experiments"]) for c in completed),
            "model_calls": sum(c["result"]["metrics"]["model_calls"] for c in completed),
        }

    frontend = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if frontend.exists():
        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

        @app.get("/")
        def index():
            return FileResponse(frontend / "index.html")
    else:

        @app.get("/")
        def unbuilt():
            return {
                "application": "FailureLab",
                "message": "Build the frontend with npm ci and npm run build in frontend/.",
                "api_docs": "/docs",
            }

    return app
