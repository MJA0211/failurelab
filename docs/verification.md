# Implementation verification

For the security patch's checks, see [v0.1.1 verification](releases/v0.1.1.md).
The measurements below record the initial implementation.

Verified locally on September 11–12, 2026, on Windows with Python 3.11.5,
Node 22.20.0, uv 0.12.6, and Playwright Chromium 151.0.7922.34.

## Executed checks

| Check | Observed result |
|---|---|
| Full pytest suite | **68 passed** in 31.85 seconds |
| Desktop/mobile acceptance after final screenshot synchronization | **2 passed** |
| Python lint | Ruff passed across source, tests, and scripts |
| Python formatting | Ruff format check passed |
| Frontend types and production build | TypeScript and Vite passed |
| Frontend formatting | Prettier check passed |
| JavaScript dependency audit | npm audit reported **0 vulnerabilities** |
| Authored regression evaluation | 16/16 signature cases under each of two configurations |
| Real Chromium environment check | Passed |
| Live npm metadata lookup | @playwright/test 1.51.0 returned successfully |
| Live public GitHub workflow metadata | microsoft/playwright run 34662741300 returned successfully |
| Local deployed service | Four completed owned investigations, three supported mechanisms, one inconclusive case |

The frontend acceptance tests exercised search, case navigation, citation inspection,
experiment results, human review persistence, Markdown download, direct-link reload,
new-case creation, mobile navigation, and narrow-viewport overflow checks. They ran
against a real FastAPI server and worker, with actual browser experiments.

The browser suite checked all three correct interventions and an incorrect intervention.
Cache replay preserves result text exactly across Windows UTF-8 boundaries. Recovery tests
injected a failure after diagnosis and verified that the completed stage was not repeated.
Other tests covered model schema/citation validation, persistent call budgets across
failed retries, configuration provenance, signature verification, duplicate webhooks,
credential-free redirects, archive traversal/expansion limits, loopback host validation
against DNS rebinding, and external-runner contracts.

One upstream Starlette/AnyIO deprecation warning remains in the test client. It did
not affect test results. Coverage reported approximately **71%** of combined statement/
branch opportunities. Spawned UI server execution is not included in this coverage
measurement, and optional deployment adapters contain unexecuted branches. Coverage
is not represented as complete or as evidence of model quality.

## Small local load measurement

One server process; four owned cases; 120 GET requests across list, case-detail, and
metrics endpoints; eight concurrent client threads:

| Measure | Result |
|---|---:|
| HTTP 200 responses | 120 / 120 |
| Median response time | 23.12 ms |
| p95 response time | 83.96 ms |
| Observed throughput | 257.78 requests/second |

This is a local smoke measurement, not a production scale certification. It excludes
GitHub ingestion, model inference, browser execution, remote runners, and large databases.
Reproduce with `uv run python scripts/load_smoke.py` while the local server is running.

## External acceptance still requires its environment

| Path | Implemented and locally checked | External condition not exercised here |
|---|---|---|
| Chat/vision inference | HTTP request/schema/citation/budget contracts tested with controlled responses | Real provider credentials and model inference |
| Neural retrieval | Actual sentence-transformer and cross-encoder adapter | Optional model installation/download and quality benchmark |
| GitHub ingestion | Live public metadata; logs, artifacts, redirects, version pinning, and failures tested through controlled HTTP responses | Private repository credentials and retained production artifacts |
| Linux repository runner | Implemented checkout, manifest validation, test identity checks, and bounded subprocess execution; parser/manifest/client contracts tested | Disposable Linux VM and a reviewed target repository |
| PostgreSQL | Store/checkpointer adapter and configuration | Running PostgreSQL service |
| Docker | Dockerfile/Compose definition | Docker engine unavailable in this implementation environment |

The untested paths remain unverified; simulated success does not replace these checks.
The local default labels baseline mode and owned fixtures and refuses to execute
imported repository code.
No real-world model accuracy, user time savings, distributed throughput, or deployed
cloud-service claim is made.

Raw local outputs live under ignored `var/`: `test-results.xml`, `coverage.json`,
`evaluation.json`, `integration-smoke.json`, and `load-smoke.json`.
