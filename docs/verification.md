# Implementation verification

## Unfamiliar CI validation: September 12, 2026

The [single-incident record](unfamiliar-ci-validation.md) documents actual GitHub
ingestion, live agent calls, and repository execution in a disposable hosted Linux VM.
The final suite passed 130 tests with 77% coverage. The incident reached a supported
result after tool-contract correction; earlier inconclusive attempts remain recorded.
The updated four-fixture live check is incomplete.

## Live provider update: September 12, 2026

Both agent stages completed real provider calls on four owned fixtures, with three
supported browser interventions and one missing-evidence abstention after a prompt
correction. The application suite passed 122 tests. The subsequent larger live
evaluation stopped on HTTP 402; it has no completed score. See the
[live verification record](live-agent-verification.md) for the model, measured results,
initial failure, and reproduction commands. The sections below retain earlier results.

## Portfolio update: September 12, 2026

The boundary-hardening update passed **121 local tests** in 74.82 seconds on Windows
with Python 3.11.5. This includes 28 new cases covering canonical GitHub paths,
bounded repository names, CLI option injection, browser deep-link manipulation, and
execution-boundary checks when callers bypass request-model validation. The suite also
checks Git's actual parsing of an option-shaped repository operand after `--`.
The frontend production build, Ruff lint/format, Prettier, pip-audit, and npm audit
passed; neither dependency audit reported known vulnerabilities in its checked scope.
The authored baseline evaluation again matched all 16 cases in each configuration.

These are system verification results. Live model quality, production capacity, and
developer time savings remain unmeasured. Hosted results are available in the
[quality workflow history](https://github.com/MJA0211/failurelab/actions/workflows/ci.yml).
CodeQL alerts require separate review from the scan's completion status.
The [finding review](security-review.md) records the fixes and command-boundary analysis.

The [recorded walkthrough](walkthrough.webm) was generated from a fresh owned-fixture
workspace with baseline mode, then visually reviewed. It is 27.56 seconds, 1440 × 1000,
and contains no audio. The recording script completed its UI assertions without page
errors and removed its temporary server/database workspace.

## Historical implementation measurements

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
| Chat/vision inference | Text diagnosis and planning exercised with real provider calls; see [live verification](live-agent-verification.md) | Vision inference, other models/providers, and held-out model quality |
| Neural retrieval | Actual sentence-transformer and cross-encoder adapter | Optional model installation/download and quality benchmark |
| GitHub ingestion | Actual failed public workflow, job logs, source, and browser artifacts imported and investigated; bounded downloads, redirects, and failure handling also have contract tests | Private repositories and GitHub-delivered webhooks to a public endpoint |
| Linux repository runner | Actual reviewed repository checkout, unchanged browser assertions, HTTP authentication/replay, and artifact return in a disposable GitHub-hosted Linux VM; see [validation](unfamiliar-ci-validation.md) | Permanent private endpoint, strict public egress isolation, and arbitrary untrusted-repository deployment |
| PostgreSQL | Store/checkpointer adapter and configuration | Running PostgreSQL service |
| Docker | Dockerfile/Compose definition | Docker engine unavailable in this implementation environment |

The untested paths remain unverified; simulated success does not replace these checks.
The local default labels baseline mode and owned fixtures and refuses to execute
imported repository code.
No real-world model accuracy, user time savings, distributed throughput, or deployed
cloud-service claim is made.

Raw local outputs live under ignored `var/`: `test-results.xml`, `coverage.json`,
`evaluation.json`, `integration-smoke.json`, and `load-smoke.json`.
