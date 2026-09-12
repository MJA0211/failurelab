"""Only owned fixture HTML executes locally. Repository code requires a remote runner."""

import base64
import hashlib
import platform
import time

import httpx

from failurelab.schemas import ExperimentPlan, ExperimentResult, RunnerResponse

RUNNER_VERSION = "fixture-runner-v2"
# Both experimental conditions use the same bounded actionability budget.
ACTION_TIMEOUT_MS = 3000
HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
body{font:16px system-ui;margin:0;background:#f5f5f1;color:#162622}header{padding:25px 45px;border-bottom:1px solid #ddd;display:flex;justify-content:space-between}
main{max-width:850px;margin:65px auto}h1{font-size:42px;letter-spacing:-2px}button{background:#176b50;color:white;border:0;border-radius:8px;padding:16px 36px;font:inherit;cursor:pointer}
input{padding:14px;border:1px solid #ccd6ce;border-radius:6px}#release-overlay{position:fixed;inset:0;background:#102d2290;z-index:100;display:flex;align-items:center;justify-content:center}aside section{background:white;padding:40px;border-radius:16px;max-width:360px}.product{background:white;border:1px solid #e2e7e2;border-radius:12px;padding:32px;margin:24px 0}.tag{color:#567368;font-size:12px;letter-spacing:2px}#success{color:#176b50}</style></head><body>
<header><strong>FIELDWORK / SUPPLY</strong><span>Owned FailureLab test application</span></header><main><span class="tag">EVERYDAY ESSENTIALS</span><h1>A considered workspace.</h1><p>A small storefront built for repeatable browser experiments.</p><div class="product"><h2>Studio notebook</h2><p>Recycled paper. Lay-flat binding. $24.00</p><input data-testid="search-input" aria-label="Search products" placeholder="Search products"><p><button data-testid="checkout">Place order</button></p><p id="success"></p><p id="account"></p></div></main>
<script>window.response={user:{name:'Ada'}};window.renderAccount=()=>{try{document.querySelector('#account').textContent=window.response.user.name}catch(e){document.querySelector('#account').textContent='Unable to render customer'}};window.renderAccount();document.querySelector('button').onclick=()=>document.querySelector('#success').textContent='Order placed';</script></body></html>"""


def verdict(baseline_passes, intervention_passes, repetitions, intervention):
    if intervention == "repeat_baseline":
        return "inconclusive"
    if baseline_passes == 0 and intervention_passes == repetitions:
        return "supported"
    if baseline_passes == 0 and intervention_passes == 0:
        return "contradicted"
    return "inconclusive"


def setup_page(page, scenario):
    page.set_content(HTML)
    if scenario == "overlay":
        page.evaluate(
            """() => {let el=document.createElement('aside');el.id='release-overlay';el.innerHTML='<section><small>WHAT’S NEW</small><h2>A new collection is here.</h2><p>This announcement overlays the checkout button.</p></section>';document.body.appendChild(el)}"""
        )
    elif scenario == "selector":
        page.locator("input").evaluate("el => el.setAttribute('data-testid','catalog-search')")
    elif scenario == "api_contract":
        page.evaluate("() => { window.response={data:{name:'Ada'}}; window.renderAccount() }")


def apply_intervention(page, intervention):
    if intervention == "remove_overlay":
        page.evaluate("() => document.querySelector('#release-overlay')?.remove()")
    elif intervention == "restore_selector":
        page.locator("input").evaluate("el => el.setAttribute('data-testid','search-input')")
    elif intervention == "restore_response":
        page.evaluate("() => {window.response={user:{name:'Ada'}};window.renderAccount()}")


def check(page, scenario):
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    try:
        if scenario == "overlay":
            page.get_by_test_id("checkout").click(timeout=ACTION_TIMEOUT_MS)
            return page.locator("#success").inner_text() == "Order placed", "checkout interaction"
        if scenario == "selector":
            page.get_by_test_id("search-input").fill("notebook", timeout=ACTION_TIMEOUT_MS)
            return True, "search locator resolved"
        if scenario == "api_contract":
            return page.locator("#account").inner_text() == "Ada", "account response rendered"
    except PlaywrightTimeoutError as exc:
        return False, str(exc).split("Call log:")[0].strip()[:250]
    return False, "No supported fixture assertion"


def screenshot(store, case_id, scenario):
    if scenario not in {"overlay", "selector", "api_contract"}:
        return None
    from playwright.sync_api import sync_playwright

    path = store.artifact_path(case_id, "failure.png")
    if not path.exists():
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                page.route("**/*", lambda route: route.abort())
                setup_page(page, scenario)
                page.screenshot(path=str(path))
            finally:
                browser.close()
    return {
        "id": "e-screenshot",
        "title": "Browser at failure",
        "kind": "image",
        "content": "Screenshot captured from the owned reproduction application before any intervention.",
        "source": "owned-fixture://chromium",
        "sha": hashlib.sha256(path.read_bytes()).hexdigest(),
        "artifact": "failure.png",
    }


def run_fixture(store, case_id, scenario, plan: ExperimentPlan) -> ExperimentResult:
    from playwright.sync_api import sync_playwright

    identity = hashlib.sha256(
        (
            scenario + plan.model_dump_json() + HTML + RUNNER_VERSION + str(ACTION_TIMEOUT_MS)
        ).encode()
    ).hexdigest()[:10]
    name = f"{plan.hypothesis_id}-{plan.intervention}-{identity}"
    result_path = store.artifact_path(case_id, name + ".json")
    if result_path.exists():
        return ExperimentResult.model_validate_json(result_path.read_text(encoding="utf-8"))
    start = time.perf_counter()
    counts = {"baseline": 0, "intervention": 0}
    observations, artifacts = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        version = browser.version
        try:
            # Interleaved A/B runs, fresh browser contexts, identical viewport and network policy.
            for repetition in range(plan.repetitions):
                for condition in ("baseline", "intervention"):
                    context = browser.new_context(viewport={"width": 1280, "height": 800})
                    context.route("**/*", lambda route: route.abort())
                    if repetition == 0:
                        context.tracing.start(screenshots=True, snapshots=True, sources=True)
                    page = context.new_page()
                    setup_page(page, scenario)
                    if condition == "intervention":
                        apply_intervention(page, plan.intervention)
                    passed, observation = check(page, scenario)
                    counts[condition] += int(passed)
                    observations.append(
                        f"{condition} {repetition + 1}: {'PASS' if passed else 'FAIL'} — {observation}"
                    )
                    if repetition == 0:
                        png = f"{name}-{condition}.png"
                        trace = f"{name}-{condition}.zip"
                        page.screenshot(path=str(store.artifact_path(case_id, png)))
                        context.tracing.stop(path=str(store.artifact_path(case_id, trace)))
                        artifacts.extend([png, trace])
                    context.close()
        finally:
            browser.close()
    result = ExperimentResult(
        hypothesis_id=plan.hypothesis_id,
        intervention=plan.intervention,
        baseline_passes=counts["baseline"],
        intervention_passes=counts["intervention"],
        repetitions=plan.repetitions,
        verdict=verdict(
            counts["baseline"], counts["intervention"], plan.repetitions, plan.intervention
        ),
        duration_ms=int((time.perf_counter() - start) * 1000),
        observations=observations,
        artifacts=artifacts,
        environment={
            "runner": RUNNER_VERSION,
            "action_timeout_ms": str(ACTION_TIMEOUT_MS),
            "chromium": version,
            "platform": platform.platform(),
            "fixture_sha256": hashlib.sha256(HTML.encode()).hexdigest(),
            "network": "blocked",
            "scenario": scenario,
        },
    )
    temp = result_path.with_suffix(".tmp")
    temp.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    temp.replace(result_path)
    return result


def run_experiment(settings, store, case, plan):
    if case["source"] == "demo" and case["scenario"] in {"overlay", "selector", "api_contract"}:
        return run_fixture(store, case["id"], case["scenario"], plan)
    if settings.runner_url:
        with httpx.Client(timeout=600, follow_redirects=False) as client:
            with client.stream(
                "POST",
                settings.runner_url.rstrip("/") + "/experiments",
                headers={
                    "Authorization": "Bearer " + settings.runner_token.get_secret_value(),
                    "Idempotency-Key": f"{case['id']}:{plan.hypothesis_id}:{plan.intervention}",
                },
                json={
                    "repository": case["repository"],
                    "commit_sha": case["commit_sha"],
                    "test_name": case["test_name"],
                    "plan": plan.model_dump(),
                },
            ) as response:
                response.raise_for_status()
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > min(16_000_000, settings.max_artifact_bytes * 2):
                        raise RuntimeError("Runner response exceeded the transfer limit")
                    chunks.append(chunk)
        remote = RunnerResponse.model_validate_json(b"".join(chunks))
        result = ExperimentResult.model_validate(remote.model_dump(exclude={"artifact_payloads"}))
        if (
            result.hypothesis_id != plan.hypothesis_id
            or result.intervention != plan.intervention
            or result.repetitions != plan.repetitions
        ):
            raise RuntimeError("Runner response does not match the submitted experiment")
        if max(result.baseline_passes, result.intervention_passes) > result.repetitions:
            raise RuntimeError("Runner returned impossible pass counts")
        result.verdict = verdict(
            result.baseline_passes,
            result.intervention_passes,
            result.repetitions,
            result.intervention,
        )
        if (
            len(set(result.artifacts)) != len(result.artifacts)
            or set(result.artifacts) != {a.name for a in remote.artifact_payloads}
            or len(remote.artifact_payloads) != len(result.artifacts)
        ):
            raise RuntimeError("Runner artifact declarations do not match the payloads")
        retained, total = [], 0
        for artifact in remote.artifact_payloads:
            try:
                data = base64.b64decode(artifact.data_base64, validate=True)
            except ValueError as exc:
                raise RuntimeError("Runner artifact has invalid base64") from exc
            total += len(data)
            if total > settings.max_artifact_bytes:
                raise RuntimeError("Runner artifacts exceeded the retention limit")
            extension = artifact.name.rsplit(".", 1)[-1]
            magic = b"\x89PNG\r\n\x1a\n" if extension == "png" else b"PK\x03\x04"
            if hashlib.sha256(data).hexdigest() != artifact.sha256 or not data.startswith(magic):
                raise RuntimeError("Runner artifact content failed integrity validation")
            name = f"runner-{artifact.sha256}.{extension}"
            retained.append((name, data))
        for name, data in retained:
            path = store.artifact_path(case["id"], name)
            if path.exists() and path.read_bytes() != data:
                raise RuntimeError("Retained runner artifact differs from its content hash")
            if not path.exists():
                temporary = path.with_suffix(path.suffix + ".tmp")
                temporary.write_bytes(data)
                temporary.replace(path)
        result.artifacts = [name for name, _ in retained]
        result.environment["artifact_sha256"] = {
            name: hashlib.sha256(data).hexdigest() for name, data in retained
        }
        return result
    return ExperimentResult(
        hypothesis_id=plan.hypothesis_id,
        intervention=plan.intervention,
        baseline_passes=0,
        intervention_passes=0,
        repetitions=plan.repetitions,
        verdict="unavailable",
        duration_ms=0,
        observations=[
            "External repository code was not executed. Configure the isolated runner service to reproduce this repository."
        ],
        environment={"runner": "not-configured"},
    )
