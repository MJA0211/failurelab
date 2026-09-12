"""Real browser acceptance tests against the production frontend and real API/worker."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def live_server(tmp_path_factory):
    if not (ROOT / "frontend/dist/index.html").exists():
        pytest.fail("Build frontend with npm run build before browser acceptance tests")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    data = tmp_path_factory.mktemp("ui-workspace")
    env = {
        **os.environ,
        "FAILURELAB_ENV_FILE": "",
        "FAILURELAB_DATA_DIR": str(data),
        "FAILURELAB_PORT": str(port),
        "FAILURELAB_MODEL_MODE": "baseline",
        "FAILURELAB_API_TOKEN": "",
        "FAILURELAB_SEED_DEMO": "true",
        "FAILURELAB_WORKER_ENABLED": "true",
    }
    log = (data / "server.log").open("w")
    process = subprocess.Popen(
        [sys.executable, "-m", "failurelab.cli", "serve"],
        cwd=ROOT,
        env=env,
        stdout=log,
        stderr=log,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
            if process.poll() is not None:
                pytest.fail((data / "server.log").read_text())
            try:
                response = httpx.get(base + "/api/investigations")
                if (
                    response.status_code == 200
                    and len(response.json()) == 4
                    and all(c["status"] == "completed" for c in response.json())
                ):
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        else:
            pytest.fail("Demo workflows did not complete:\n" + (data / "server.log").read_text())
        yield base
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        log.close()


@pytest.mark.browser
def test_dashboard_evidence_experiments_review_export(live_server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1512, "height": 1100})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(live_server)
        expect(page.get_by_role("heading", name="Evidence over guesswork.")).to_be_visible()
        expect(page.locator(".case-row")).to_have_count(4)
        page.get_by_label("Search investigations").fill("overlay")
        expect(page.locator(".case-row")).to_have_count(1)
        page.get_by_label("Search investigations").fill("")
        output = ROOT / "docs/screenshots"
        output.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(output / "dashboard.png"), full_page=True)
        page.get_by_role("button", name="Checkout click intercepted", exact=False).click()
        expect(
            page.get_by_role(
                "heading", name="An overlay intercepts the target interaction", exact=True
            )
        ).to_be_visible()
        page.get_by_role("button", name="e-log", exact=False).click()
        expect(page.locator(".evidence-code")).to_contain_text("intercepts pointer events")
        page.get_by_role("button", name="Experiments (1)", exact=True).click()
        expect(page.locator(".terminal")).to_contain_text("baseline 1: FAIL")
        expect(page.locator(".terminal")).to_contain_text("intervention 1: PASS")
        page.screenshot(path=str(output / "experiment.png"), full_page=True)
        page.get_by_role("button", name="Review", exact=True).click()
        page.get_by_label("Review note").fill(
            "Verified the baseline and intervention traces. Supported within this fixture."
        )
        page.get_by_role("button", name="Save review", exact=True).click()
        expect(page.get_by_role("dialog")).to_have_count(0)
        page.get_by_role("button", name="Overview", exact=True).click()
        expect(page.locator(".review-history")).to_contain_text("Verified the baseline")
        with page.expect_download() as info:
            page.get_by_role("button", name="Export", exact=True).click()
        assert info.value.suggested_filename.endswith(".md")
        page.reload()
        expect(
            page.get_by_role("heading", name="Checkout click intercepted", exact=False)
        ).to_be_visible()
        assert errors == []
        browser.close()


@pytest.mark.browser
def test_untrusted_deep_link_cannot_choose_an_api_path(live_server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page()
            requests = []
            page.on("request", lambda request: requests.append(request.url))
            for value in ("../../config", "inv-deadbeef0000/../../metrics", "//attacker.example"):
                requests.clear()
                page.goto(live_server + "/?case=" + quote(value, safe=""))
                expect(page.locator(".case-row")).to_have_count(4)
                api_paths = [url.removeprefix(live_server) for url in requests if "/api/" in url]
                assert set(api_paths) <= {"/api/investigations", "/api/config"}, api_paths
                assert all(url.startswith(live_server + "/") for url in requests), requests
        finally:
            browser.close()


@pytest.mark.browser
def test_new_investigation_and_mobile_navigation(live_server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True)
        page.goto(live_server)
        expect(page.get_by_role("heading", name="Evidence over guesswork.")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.get_by_role("button", name="New investigation", exact=True).click()
        page.get_by_role("radio", name="Critical artifacts are missing", exact=False).check()
        page.get_by_role("button", name="Start investigation", exact=True).click()
        expect(
            page.get_by_role("heading", name="Insufficient evidence to localize this failure")
        ).to_be_visible(timeout=20000)
        page.get_by_role("button", name="Toggle navigation").click()
        page.get_by_role("button", name="Evaluation bench", exact=False).click()
        expect(page.get_by_role("heading", name="The evaluation bench.")).to_be_visible()
        page.get_by_role("button", name="Toggle navigation").click()
        page.get_by_role("button", name="Integrations", exact=True).click()
        expect(page.get_by_role("heading", name="Connect the evidence.")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.get_by_role("button", name="Toggle navigation").click()
        page.get_by_role("button", name="Investigations", exact=False).first.click()
        expect(page.locator(".sidebar")).to_have_css("transform", "matrix(1, 0, 0, 1, -236, 0)")
        page.screenshot(path=str(ROOT / "docs/screenshots/mobile.png"), full_page=True)
        browser.close()
