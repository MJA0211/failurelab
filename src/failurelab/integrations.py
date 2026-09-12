"""Bounded GitHub and npm ingestion. Redirects never receive API credentials."""

import hashlib
import io
import json
import re
import time
import zipfile
from urllib.parse import quote, urlparse

import httpx

from failurelab.schemas import Evidence, InvestigationInput
from failurelab.store import redact


class IntegrationError(RuntimeError):
    pass


class GitHub:
    def __init__(self, settings, transport=None):
        self.settings = settings
        self.client = httpx.Client(
            base_url="https://api.github.com",
            timeout=20,
            follow_redirects=False,
            transport=transport,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "FailureLab/0.1",
                **(
                    {"Authorization": "Bearer " + settings.github_token.get_secret_value()}
                    if settings.github_token.get_secret_value()
                    else {}
                ),
            },
        )

    def close(self):
        self.client.close()

    def allowed(self, repository):
        if (
            not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
            or repository.lower() not in self.settings.allowed_repositories
        ):
            raise IntegrationError("Repository is not in FAILURELAB_GITHUB_REPOSITORIES")

    def get(self, path):
        for attempt in range(3):
            response = self.client.get(path)
            if response.status_code not in {429, 502, 503, 504}:
                break
            if attempt < 2:
                time.sleep(0.25 * 2**attempt)
        if response.status_code != 200:
            raise IntegrationError(
                f"GitHub returned HTTP {response.status_code}. Check repository access, artifact retention, and API limits."
            )
        if len(response.content) > self.settings.max_artifact_bytes:
            raise IntegrationError("GitHub response exceeded the ingestion limit")
        return response.json()

    def download(self, path):
        response = self.client.get(path)
        if response.status_code == 200:
            if len(response.content) > self.settings.max_artifact_bytes:
                raise IntegrationError("Download exceeded the ingestion limit")
            return response.content
        if response.status_code not in {301, 302, 303, 307, 308}:
            raise IntegrationError(f"Artifact unavailable (HTTP {response.status_code})")
        location = response.headers.get("location", "")
        parsed = urlparse(location)
        host = parsed.hostname or ""
        if (
            parsed.scheme != "https"
            or parsed.username
            or not any(
                host.endswith(suffix)
                for suffix in (
                    ".blob.core.windows.net",
                    ".githubusercontent.com",
                    ".actions.githubusercontent.com",
                    ".github.com",
                )
            )
        ):
            raise IntegrationError("Artifact redirect host is outside the GitHub storage allowlist")
        # A fresh client intentionally has no GitHub Authorization header.
        with httpx.Client(timeout=30, follow_redirects=False) as client:
            with client.stream("GET", location) as stream:
                if stream.status_code != 200:
                    raise IntegrationError("GitHub storage download failed")
                chunks, size = [], 0
                for chunk in stream.iter_bytes():
                    size += len(chunk)
                    if size > self.settings.max_artifact_bytes:
                        raise IntegrationError("Artifact exceeded the ingestion limit")
                    chunks.append(chunk)
        return b"".join(chunks)

    def describe_run(self, repository, run_id):
        self.allowed(repository)
        run = self.get(f"/repos/{repository}/actions/runs/{run_id}")
        payload = InvestigationInput(
            title=(run.get("display_title") or run.get("name") or "GitHub workflow failure")[:200],
            repository=repository,
            commit_sha=run["head_sha"],
            test_name=(run.get("name") or "GitHub Actions")[:300],
            evidence=[
                Evidence(
                    id="e-run",
                    title="Workflow metadata",
                    kind="metadata",
                    content=json.dumps(
                        {
                            "run_id": run_id,
                            "run_attempt": run.get("run_attempt", 1),
                            "conclusion": run.get("conclusion"),
                            "html_url": run.get("html_url"),
                        }
                    ),
                    source=run.get("html_url", ""),
                )
            ],
        ).model_dump()
        payload["run_id"] = run_id
        payload["run_attempt"] = run.get("run_attempt", 1)
        return payload

    def collect(self, case, store):
        repo, sha = case["repository"], case["commit_sha"]
        self.allowed(repo)
        run_id = case["payload"]["run_id"]
        attempt = case["payload"].get("run_attempt", 1)
        prefix = f"/repos/{repo}"
        items = list(case["payload"]["evidence"])
        warnings = []
        jobs = self.get(f"{prefix}/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100").get(
            "jobs", []
        )
        for job in [j for j in jobs if j.get("conclusion") in {"failure", "timed_out"}][:4]:
            try:
                content = self.download(f"{prefix}/actions/jobs/{job['id']}/logs").decode(
                    "utf-8", errors="replace"
                )
                # Preserve the tail: failures usually follow setup output.
                items.append(
                    Evidence(
                        id=f"e-job-{job['id']}",
                        title=job["name"][:300],
                        kind="log",
                        content=redact(content[-80_000:]),
                        source=job.get("html_url", ""),
                    ).model_dump()
                )
            except IntegrationError as exc:
                warnings.append(str(exc))
        commit = self.get(f"{prefix}/commits/{sha}")
        for index, file in enumerate(commit.get("files", [])[:12]):
            if file.get("patch"):
                items.append(
                    Evidence(
                        id=f"e-code-{index}",
                        title=file["filename"][:300],
                        kind="code",
                        content=file["patch"][:40_000],
                        source=f"https://github.com/{repo}/blob/{sha}/{quote(file['filename'])}",
                    ).model_dump()
                )
        try:
            artifacts = self.get(f"{prefix}/actions/runs/{run_id}/artifacts?per_page=100").get(
                "artifacts", []
            )
            for artifact in [
                a
                for a in artifacts
                if not a.get("expired")
                and a.get("size_in_bytes", 0) <= self.settings.max_artifact_bytes
            ][:3]:
                raw = self.download(f"{prefix}/actions/artifacts/{artifact['id']}/zip")
                items.extend(
                    read_archive(
                        raw,
                        store,
                        case["id"],
                        f"{artifact['id']}",
                        self.settings.max_artifact_bytes,
                    )
                )
        except (IntegrationError, zipfile.BadZipFile, ValueError) as exc:
            warnings.append(f"Diagnostic artifact ingestion: {exc}")
        for item in items:
            item["content"] = redact(item.get("content", ""))
            if item["kind"] != "image":
                item["sha"] = hashlib.sha256(item["content"].encode()).hexdigest()
        if warnings:
            store.event(
                case["id"],
                "collect",
                "Some upstream evidence was unavailable",
                {"warnings": warnings},
                key="ingestion-warnings",
            )
        return items[:40]


def read_archive(raw, store, case_id, prefix, max_bytes):
    result = []
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        if len(entries) > 200 or sum(e.file_size for e in entries) > max_bytes * 3:
            raise ValueError("Archive expansion limit exceeded")
        for index, entry in enumerate(entries):
            if entry.is_dir() or entry.file_size > max_bytes or len(result) >= 12:
                continue
            # Never extract paths from archives; every file gets an application-generated name.
            extension = entry.filename.rsplit(".", 1)[-1].lower()
            eid = f"e-artifact-{prefix}-{index}"
            if extension in {"txt", "log", "json", "trace", "network"}:
                content = archive.read(entry).decode("utf-8", errors="replace")[-50_000:]
                result.append(
                    Evidence(
                        id=eid,
                        title=entry.filename[-300:],
                        kind="log" if extension in {"log", "trace", "network"} else "document",
                        content=redact(content),
                        source="github-artifact://" + entry.filename,
                    ).model_dump()
                )
            elif extension == "png":
                content = archive.read(entry)
                if not content.startswith(b"\x89PNG\r\n\x1a\n"):
                    continue
                name = eid + ".png"
                store.artifact_path(case_id, name).write_bytes(content)
                result.append(
                    Evidence(
                        id=eid,
                        title=entry.filename[-300:],
                        kind="image",
                        content="Screenshot uploaded by the GitHub workflow.",
                        source="github-artifact://" + entry.filename,
                        sha=hashlib.sha256(content).hexdigest(),
                        artifact=name,
                    ).model_dump()
                )
            elif extension == "zip" and "trace" in entry.filename.lower():
                name = eid + ".zip"
                content = archive.read(entry)
                store.artifact_path(case_id, name).write_bytes(content)
                # Read one trace archive level; no recursive extraction.
                with zipfile.ZipFile(io.BytesIO(content)) as trace:
                    if (
                        sum(e.file_size for e in trace.infolist()) > max_bytes * 3
                        or len(trace.infolist()) > 1000
                    ):
                        raise ValueError("Trace expansion limit exceeded")
                    for child in trace.infolist():
                        if (
                            child.filename.endswith((".trace", ".network"))
                            and child.file_size <= max_bytes
                        ):
                            text = trace.read(child).decode("utf-8", errors="replace")[-40_000:]
                            result.append(
                                Evidence(
                                    id=f"{eid}-{len(result)}",
                                    title=child.filename[-300:],
                                    kind="log",
                                    content=redact(text),
                                    source="github-trace://" + child.filename,
                                    artifact=name,
                                ).model_dump()
                            )
                            if len(result) >= 12:
                                break
    return result


def npm_metadata(package, version, transport=None):
    if not re.fullmatch(r"(?:@[a-z0-9_.-]+/)?[a-z0-9_.-]+", package) or not re.fullmatch(
        r"[0-9A-Za-z.+-]{1,100}", version
    ):
        raise ValueError("Invalid npm package or version")
    with httpx.Client(timeout=15, follow_redirects=False, transport=transport) as client:
        response = client.get(
            f"https://registry.npmjs.org/{quote(package, safe='')}/{quote(version, safe='')}"
        )
    if response.status_code != 200:
        raise IntegrationError(f"npm returned HTTP {response.status_code}")
    data = response.json()
    return {
        key: data.get(key)
        for key in ("name", "version", "engines", "dependencies", "peerDependencies", "deprecated")
    }
