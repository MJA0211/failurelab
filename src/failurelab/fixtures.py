"""Owned, explicitly synthetic incidents. These are not third-party production failures."""

from failurelab.schemas import Evidence, InvestigationInput

DETAILS = {
    "overlay": (
        "Checkout click intercepted by a new overlay",
        "checkout › completes an order",
        "TimeoutError: locator.click: Timeout 5000ms exceeded. #release-overlay intercepts pointer events.",
        "<button data-testid='checkout'>Place order</button><aside id='release-overlay'>Release notes</aside>",
        "+ #release-overlay { position: fixed; inset: 0; z-index: 100; }",
    ),
    "selector": (
        "Search test still targets a renamed selector",
        "catalog › search finds a product",
        "TimeoutError: waiting for locator('[data-testid=search-input]'); resolved to 0 elements.",
        "<input data-testid='catalog-search' aria-label='Search products'>",
        "- data-testid='search-input'\n+ data-testid='catalog-search'",
    ),
    "api_contract": (
        "Account view expects the previous response shape",
        "account › renders the customer name",
        "TypeError: Cannot read properties of undefined (reading 'name'). GET /api/user returned 200.",
        "<main><h1>Account</h1><p id='error'>Unable to render customer</p></main>",
        "- response: { user: { name: 'Ada' } }\n+ response: { data: { name: 'Ada' } }\n consumer: response.user.name",
    ),
    "unknown": (
        "Runner exited before diagnostic artifacts were uploaded",
        "smoke › application starts",
        "Worker exited with code 137. No browser trace or application logs were retained.",
        "DOM snapshot unavailable.",
        "No source diff was supplied.",
    ),
}


def fixture(scenario: str) -> dict:
    title, test, log, dom, diff = DETAILS[scenario]
    evidence = [
        Evidence(
            id="e-log",
            title="Failing test output",
            kind="log",
            content=log,
            source="owned-fixture://test-output",
        ),
        Evidence(
            id="e-dom",
            title="DOM at failure",
            kind="dom",
            content=dom,
            source="owned-fixture://dom",
        ),
        Evidence(
            id="e-diff",
            title="Change under investigation",
            kind="code",
            content=diff,
            source="owned-fixture://src/app.tsx",
        ),
        Evidence(
            id="e-runbook",
            title="Investigation runbook",
            kind="document",
            content="Compare baseline and intervention under the same environment. A click can be intercepted by a fixed overlay. A missing selector can indicate an identifier change. An API contract can change without an HTTP error. Do not conclude causality from a single passing rerun. Missing artifacts require abstention.",
            source="owned-fixture://runbook/v1",
        ),
    ]
    return InvestigationInput(
        title=title,
        repository="failurelab/storefront",
        commit_sha="a13f8c2e940ba175ad1841b2a76a5ffc56bb1234",
        test_name=test,
        evidence=evidence,
    ).model_dump()


def seed(store):
    for scenario in DETAILS:
        store.create(
            fixture(scenario), source="demo", scenario=scenario, dedupe_key=f"demo-v1:{scenario}"
        )
