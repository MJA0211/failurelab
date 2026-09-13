# FailureLab portfolio summary

## What is FailureLab?

A CI investigation workspace with two bounded agent stages for diagnosis and
intervention planning. The model proposes a mechanism; the application controls
evidence, execution, deterministic validation, provenance, and replay.

## What problem does it solve?

It connects a failed assertion to retained logs, source, and browser evidence, then
tests whether a reviewed intervention changes the result under the same assertions.
The report distinguishes proposed explanations from experiment-supported findings.

## What did I build?

A FastAPI/React workspace, a checkpointed LangGraph workflow, investigation-scoped
retrieval, schema-validated provider adapters, and bounded browser experiments.
The system includes authenticated GitHub ingestion, a separate reviewed Linux runner,
artifact retention, human review records, evaluation tooling, and CI security checks.
The [case study](portfolio-case-study.md) explains the implementation decisions.

## What evidence proves it works?

The [release report](releases/v0.1.2-gate.md) records:

- 146 passing tests and 78% combined statement/branch coverage.
- 16/16 deterministic authored cases in both variants.
- 33 targeted agent/runner tests, 16 release-gate tests, and 10 browser tests passing;
  these overlap the full suite.
- Zero CodeQL findings in the checked PR analysis, zero npm audit vulnerabilities,
  and zero known Python dependency vulnerabilities.
- Three completed-case replays producing zero new model calls and zero new Actions
  jobs, with the recorded case and hashes preserved.

These are authored/development validation results, not an independent benchmark.
They do not measure production accuracy, throughput, or developer time savings.

## What was the unfamiliar incident?

A separate authored invoice repository returned cents that its client treated as
dollars: `$16,240.00` appeared instead of `$162.40`. Live agents investigated actual
GitHub evidence and selected `restore_response`. A real Linux experiment produced
baseline 0/3 and intervention 3/3 with unchanged assertions and a deterministic
`supported` verdict. See the [original investigation](unfamiliar-ci-validation.md).

## What happened during validation?

Two early invoice attempts were inconclusive. A generic tool-description correction
preceded the successful third attempt; all outputs remain recorded. In the latest
four-fixture live acceptance, 6/7 provider calls succeeded. Overlay, selector, and API
contract passed; HTTP 402 stopped the unknown case before diagnosis. The earlier
incomplete acceptance is also preserved. Failed requests count as provider failures,
not incorrect diagnoses or successful abstentions.

## What remains incomplete?

The `v0.1.2` live release gate is `BLOCKED` by HTTP 402/payment availability. Local
Docker/PostgreSQL deployment smoke testing is not verified, and human review is
pending. There is no independent benchmark. No `v0.1.2` tag or release has been created.

## Why is the blocker not being hidden?

A reviewer needs to distinguish completed experiments from incomplete acceptance.
Six successful requests do not complete the four-fixture gate. The
[readiness assessment](releases/v0.1.2-final-readiness.md) retains the outstanding
requirements so the project can be discussed accurately before release.

## What engineering skills does this demonstrate?

Agent orchestration, retrieval and evidence contracts, API integration, controlled
experiments, evaluation design, durable job processing, replay safety, security
boundaries, observability, regression testing, and release engineering. Each claim
has an implementation or recorded check that a reviewer can inspect.
