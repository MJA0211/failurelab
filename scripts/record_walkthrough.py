"""Record a silent portfolio walkthrough using a fresh, owned baseline workspace."""

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def record(base, videos, destination):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            context = browser.new_context(
                viewport={"width": 1440, "height": 1000},
                record_video_dir=str(videos),
                record_video_size={"width": 1440, "height": 1000},
                reduced_motion="reduce",
            )
            context.route(
                "**/*",
                lambda route: (
                    route.continue_() if route.request.url.startswith(base + "/") else route.abort()
                ),
            )
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))

            def caption(text):
                page.evaluate(
                    """text => {
                        let el = document.querySelector('#recording-caption');
                        if (!el) {
                            el = document.createElement('div');
                            el.id = 'recording-caption';
                            el.style.cssText = 'position:fixed;bottom:16px;left:270px;right:24px;'
                                + 'z-index:9999;padding:16px 22px;background:#132a24;color:white;'
                                + 'border-radius:8px;font:18px system-ui;pointer-events:none';
                            document.body.appendChild(el);
                        }
                        el.textContent = text;
                    }""",
                    "Owned fixtures / deterministic baseline — " + text,
                )
                # Reading time for the recording; assertions handle application readiness.
                page.wait_for_timeout(4500)

            page.goto(base)
            expect(page.locator(".case-row")).to_have_count(4)
            caption("Four incidents, including a case with insufficient evidence.")
            page.get_by_role("button", name="Checkout click intercepted", exact=False).click()
            expect(
                page.get_by_role(
                    "heading", name="An overlay intercepts the target interaction", exact=True
                )
            ).to_be_visible()
            caption("A proposed cause is linked to retained evidence.")
            page.get_by_role("button", name="e-log", exact=False).click()
            expect(page.locator(".evidence-code")).to_contain_text("intercepts pointer events")
            caption("Inspect the retained source log and failure details.")
            page.get_by_role("button", name="Experiments (1)", exact=True).click()
            expect(page.locator(".terminal")).to_contain_text("baseline 1: FAIL")
            expect(page.locator(".terminal")).to_contain_text("intervention 1: PASS")
            caption("Real Chromium runs compare failing baselines with the intervention.")
            page.get_by_role("button", name="Review", exact=True).click()
            page.get_by_label("Review note").fill(
                "Compared the owned baseline and intervention. Support is limited to this fixture."
            )
            caption("A human records the review and the limits of the evidence.")
            page.get_by_role("button", name="Save review", exact=True).click()
            expect(page.get_by_role("dialog")).to_have_count(0)
            page.get_by_role("button", name="Investigations", exact=False).first.click()
            page.get_by_role("button", name="Runner exited before diagnostic", exact=False).click()
            expect(
                page.get_by_role("heading", name="Insufficient evidence to localize this failure")
            ).to_be_visible()
            caption(
                "Missing artifacts produce an inconclusive result, with no fabricated experiment."
            )
            assert not errors, errors
            video = page.video
            context.close()
            shutil.copyfile(video.path(), destination)
        finally:
            browser.close()


def main():
    if not (ROOT / "frontend/dist/index.html").is_file():
        raise RuntimeError("Build frontend with npm run build before recording")
    runtime = (ROOT / "var").resolve()
    runtime.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="walkthrough-", dir=runtime) as temp:
        workspace = Path(temp).resolve()
        if not workspace.is_relative_to(runtime):
            raise RuntimeError("Recording workspace is outside the local runtime directory")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        # No inherited application settings or local .env can select private data or live models.
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.upper().startswith("FAILURELAB_")
        }
        env.update(
            FAILURELAB_ENV_FILE="",
            FAILURELAB_DATA_DIR=str(workspace / "data"),
            FAILURELAB_HOST="127.0.0.1",
            FAILURELAB_PORT=str(port),
            FAILURELAB_MODEL_MODE="baseline",
            FAILURELAB_SEED_DEMO="true",
            FAILURELAB_WORKER_ENABLED="true",
        )
        base = f"http://127.0.0.1:{port}"
        destination = ROOT / "docs/walkthrough.webm"
        with (workspace / "server.log").open("w") as log:
            process = subprocess.Popen(
                [sys.executable, "-m", "failurelab.cli", "serve"],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            try:
                deadline = time.monotonic() + 120
                with httpx.Client(base_url=base, timeout=5, trust_env=False) as client:
                    while time.monotonic() < deadline:
                        if process.poll() is not None:
                            raise RuntimeError("Isolated demo server stopped before recording")
                        try:
                            response = client.get("/api/investigations")
                            cases = response.json() if response.status_code == 200 else []
                            if len(cases) == 4 and all(c["status"] == "completed" for c in cases):
                                if any(c["source"] != "demo" for c in cases):
                                    raise RuntimeError("Recording requires owned demo incidents")
                                break
                        except httpx.HTTPError:
                            pass
                        time.sleep(0.5)
                    else:
                        raise RuntimeError("Owned demo investigations did not complete")
                record(base, workspace / "video", destination)
                print(f"Recorded owned baseline walkthrough: {destination}")
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    main()
