import io
import zipfile

import httpx
import pytest

from failurelab.fixtures import fixture
from failurelab.integrations import GitHub, IntegrationError, npm_metadata, read_archive


@pytest.mark.parametrize("operation", ["get", "download"])
@pytest.mark.parametrize(
    "path",
    [
        "https://attacker.example/secrets",
        "//attacker.example/secrets",
        "/repos/owner/../private",
        "/repos/owner/%2e%2e/private",
        "/repos/owner\\private",
        "/repos/owner/repo#fragment",
        "/repos/owner/repo?redirect=https://attacker.example",
    ],
)
def test_github_rejects_noncanonical_paths_before_sending_credentials(settings, operation, path):
    def forbidden(request):
        pytest.fail("Invalid API paths must be rejected before any HTTP request")

    github = GitHub(settings, httpx.MockTransport(forbidden))
    try:
        with pytest.raises(IntegrationError, match="API path"):
            getattr(github, operation)(path)
    finally:
        github.close()


@pytest.mark.parametrize("repository", ["owner/..", "./repo", "a" * 101 + "/repo", "a/b/c"])
def test_even_allowlisted_repositories_require_bounded_canonical_names(settings, repository):
    github = GitHub(settings.model_copy(update={"github_repositories": repository}))
    try:
        with pytest.raises(IntegrationError, match="not in"):
            github.allowed(repository)
    finally:
        github.close()


@pytest.mark.parametrize("operation", ["get", "download"])
def test_github_stops_reading_at_limit_and_closes_stream(settings, operation):
    class OversizedStream(httpx.SyncByteStream):
        closed = False

        def __iter__(self):
            yield b"x" * 2048
            raise AssertionError("Read beyond the ingestion limit")

        def close(self):
            self.closed = True

    stream = OversizedStream()
    bounded = settings.model_copy(update={"max_artifact_bytes": 1024})
    github = GitHub(bounded, httpx.MockTransport(lambda _: httpx.Response(200, stream=stream)))
    try:
        with pytest.raises(IntegrationError, match="limit"):
            getattr(github, operation)("/download")
        assert stream.closed
    finally:
        github.close()


def test_github_allowlist_and_exact_commit(settings):
    settings = settings.model_copy(update={"github_repositories": "owner/repo"})
    requests = []

    def handler(request):
        requests.append(str(request.url))
        return httpx.Response(
            200,
            json={
                "head_sha": "b" * 40,
                "name": "Playwright",
                "run_attempt": 2,
                "conclusion": "failure",
            },
        )

    client = GitHub(settings, httpx.MockTransport(handler))
    result = client.describe_run("OWNER/Repo", 12)
    assert result["repository"] == "owner/repo"
    assert result["commit_sha"] == "b" * 40
    assert result["run_attempt"] == 2
    assert requests == ["https://api.github.com/repos/owner/repo/actions/runs/12"]
    with pytest.raises(IntegrationError, match="not in"):
        client.describe_run("other/repo", 12)
    client.close()


def test_untrusted_redirect_rejected(settings):
    client = GitHub(
        settings,
        httpx.MockTransport(
            lambda request: httpx.Response(
                302, headers={"Location": "http://169.254.169.254/latest/meta-data"}
            )
        ),
    )
    with pytest.raises(IntegrationError, match="allowlist"):
        client.download("/repos/owner/repo/actions/jobs/1/logs")
    client.close()


def test_archive_paths_are_not_extracted(store):
    case_id, _ = store.create(fixture("unknown"))
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        z.writestr("../../secret.log", "timeout test failure")
    evidence = read_archive(stream.getvalue(), store, case_id, "1", 10000)
    assert evidence[0]["content"] == "timeout test failure"
    assert not (store.settings.data_dir / "secret.log").exists()


def test_zip_bomb_guard(store):
    case_id, _ = store.create(fixture("unknown"))
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("huge.log", "a" * 50000)
    with pytest.raises(ValueError, match="expansion"):
        read_archive(stream.getvalue(), store, case_id, "1", 1000)


def test_npm_fetches_pinned_version():
    def handler(request):
        assert str(request.url).endswith("/%40playwright%2Ftest/1.51.0")
        return httpx.Response(
            200,
            json={
                "name": "@playwright/test",
                "version": "1.51.0",
                "engines": {"node": ">=18"},
                "private_field": "omit",
            },
        )

    result = npm_metadata("@playwright/test", "1.51.0", httpx.MockTransport(handler))
    assert result["version"] == "1.51.0"
    assert "private_field" not in result
    with pytest.raises(ValueError):
        npm_metadata("../../private", "latest")
