# Evaluation methodology

## Executable verification

`uv run pytest` runs deterministic component/API tests, service contract tests,
checkpoint recovery, browser interventions, and UI acceptance. The browser suite
asserts both failure and success, preserves traces, tests a wrong intervention,
and checks report review/export on desktop and mobile. Checking that an unknown case
stays inconclusive matters as much as checking a positive diagnosis.

Coverage is a diagnostic measure, not evidence of model quality. Optional external
services require their own acceptance runs in the intended deployment environment.

## Authored regression set

`uv run failurelab evaluate` evaluates 16 authored cases under log-only and retrieval
configurations. The set covers overlay, selector, API contract, dependency, timing,
and unknown mechanisms. Negative cases include missing artifacts and instruction-like
text in a runbook. Results include Top-1/Top-3 labels, valid citation IDs, abstention,
case-level outputs, a dataset hash, and a Wilson interval.

The regression set was designed alongside the baseline, so a high score is expected
and cannot establish generalization. It is not a held-out benchmark; no percentage
from this set should be represented as production accuracy. Valid citation IDs do not
establish textual entailment. Cases are small and mechanisms overlap; confidence
intervals should not be interpreted as independent real-world sampling guarantees.

The current baseline uses logs to recognize known signatures, so retrieving supporting
context need not improve its classification. The benchmark reports that lack of
improvement; it must not fabricate a RAG uplift.

## Live model evaluation

Configure chat inference, then run `uv run failurelab evaluate --model`. This makes
real provider calls and overwrites the local dashboard result with the measured mode.
The result records dataset and model identifiers. Failure to satisfy the configurable
minimum accuracy returns a nonzero exit code. Provider errors do not trigger baseline
substitution. Calibrate a release gate using a development set before claiming a useful
model quality threshold.

## Building a defensible external benchmark

Collect license-compatible incidents with exact failing commits, lockfiles, tests,
retained traces, and reviewer-adjudicated causes. Reproduce them before inclusion.
Snapshot inputs without the future fixing commit or its explanatory issue comments.
Separate by repository and mechanism family, not randomly by near-duplicate log line.
Freeze the test manifest and record its hash before tuning prompts or thresholds.

Use at least two independent reviewers for ambiguous cases. Label multiple plausible
causes rather than forcing a single answer. Score evidence entailment manually on a
sample; use judges only after agreement calibration. Evaluate real and injected
incidents separately. Preserve exclusions and reasons in a dataset card.

For user impact, use a counterbalanced study with developers diagnosing comparable
incidents with and without the tool. Report sample size, median completion time,
correctness, and uncertainty. FailureLab currently makes no measured time-savings claim.
