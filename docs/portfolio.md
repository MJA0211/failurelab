# Portfolio walkthrough

## Project entry

**FailureLab — CI investigation workspace**

[Source and setup](https://github.com/MJA0211/failurelab)

FailureLab investigates CI failures by retrieving evidence, proposing causes, and
running controlled browser experiments. I built the FastAPI/React application,
checkpointed LangGraph workflow, GitHub ingestion, model adapter, and evaluation
harness. The working local lab reproduces three failure mechanisms in Chromium and
retains the baseline/intervention traces behind each finding. Missing evidence produces
an inconclusive result. Live inference is configurable; the verified default uses
explicit deterministic signatures on owned fixtures.

## Resume-ready bullets

- Built a CI investigation workspace with FastAPI, React/TypeScript, and checkpointed
  LangGraph workflows; combined evidence retrieval, schema-validated model responses,
  human review, and deterministic experimental verdicts.
- Implemented interleaved Chromium baseline/intervention runs for three owned failure
  mechanisms, with fresh browser contexts, blocked network access, retained traces,
  and tests for incorrect interventions and missing evidence.
- Built automated API, recovery, security-boundary, and browser acceptance tests;
  configured Python 3.11/3.12 CI, production frontend builds, dependency audits,
  CodeQL analysis, Dependabot updates, and dependency review.

The bullets describe implemented engineering work. The model adapter and optional
neural retrieval are integration capabilities; they are not evidence of measured
model accuracy. Link the latest passing [quality run](https://github.com/MJA0211/failurelab/actions/workflows/ci.yml)
when including a test count.

## Evidence behind the claims

| Claim | Evidence | Scope |
|---|---|---|
| Browser verification executes real actions | `tests/test_workflow.py`, `tests/test_ui.py`, retained traces | Owned synthetic fixtures; three reproduced mechanisms |
| Workflows recover without repeating completed stages | Checkpoint replay and injected-failure tests | Tested local store/checkpointer configuration |
| The baseline recognizes the authored signatures | 16-case versioned regression set and executable evaluation gate | Authored alongside the baseline; not held-out accuracy |
| Local API reads were measured | [Initial verification report](verification.md): 120/120 successful reads, p95 83.96 ms at eight client threads | Historical local smoke measurement; excludes inference and runners |
| Deployment adapters exist | [Deployment guide](deployment.md) and contract tests | Live provider, PostgreSQL, Docker, and remote runner acceptance remain unverified |

There is no measured production diagnostic accuracy, production capacity, or developer
time-saving result. Establishing those claims requires, respectively, a frozen external
incident benchmark, workload-specific deployment measurements, and a controlled user
study. A passing test suite or an authored regression score does not supply that evidence.

## Five-minute demonstration

[Watch the recorded walkthrough](walkthrough.webm). This silent recording shows a
fresh local workspace with owned fixtures and deterministic baseline mode. Captions
describe the evidence, browser comparison, human review, and abstention steps. It does
not show live model inference or an imported production incident.

To regenerate it after building the frontend:

```sh
uv run python scripts/record_walkthrough.py
```

The recorder starts its own server on a random loopback port, ignores `.env` and
inherited application settings, seeds a temporary database, and blocks nonlocal browser
requests. It replaces `docs/walkthrough.webm` with the recording and removes its temporary
workspace. Review the recording before publishing it.

1. Open the dashboard. Show that owned synthetic data and baseline mode are labeled.
2. Open the overlay failure. Inspect the actual pre-intervention browser screenshot.
3. Click a citation and show the exact retained log, source location, and content hash.
4. Open Experiments. Show failing baselines and passing interventions, download a trace,
   and explain the limits of a small controlled comparison.
5. Open the missing-artifact incident. Show that no unsupported experiment is fabricated.
6. Record a human review and export the complete investigation record.
7. Open the evaluation bench. Explain why a signature regression score is not a
   production accuracy claim, and show the checkpoint/failure tests.

## Engineering discussion

Discuss historical context leakage, exact identifier retrieval, deterministic tool
contracts, unavailable evidence, idempotency across crashes, separate code execution,
provider failure behavior, human overrides, and model quality versus system correctness.

The project covers retrieval, agent tools, typed outputs, evals, observability,
deployment, and reliability, which appear in current applied AI role requirements.
Job descriptions consulted for this project include:
[Fluency AI Engineer](https://jobs.ashbyhq.com/fluency/9a83146e-e32d-4e0c-84b5-59996a58a821/),
[Build Harness & Evals](https://jobs.ashbyhq.com/build/cdf0c29b-157e-4b85-a767-e72211022c96/),
[Notion Agent Dev Velocity](https://jobs.ashbyhq.com/notion/c565d3b0-0dcf-4bcd-b29b-4168479ac78e/).
These job descriptions informed the project's relevance research; openings may change.

## Resume claims

Use measured engineering facts: implemented checkpointed LangGraph workflows,
versioned retrieval, credential-scoped GitHub ingestion, actual browser interventions,
schema-validated inference, and executable evaluation gates. Include the test count
from the final verification report, not a number copied from an earlier run.

Only claim model accuracy on a frozen held-out dataset after running it. Only claim
developer time savings after conducting the user study. Do not describe the authored
baseline regression accuracy as real-world diagnostic accuracy.
