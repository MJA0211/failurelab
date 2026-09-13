# FailureLab: testing an agent's CI diagnosis

FailureLab is a CI investigation workspace with two bounded agent stages and
executable validation. This case study covers the implementation and authored
development evidence recorded on September 12–13, 2026. The `v0.1.2` release gate is
`BLOCKED`; see the [readiness assessment](releases/v0.1.2-final-readiness.md).

## 1. Problem

A failed browser assertion describes an observable symptom. Finding the mechanism
requires connecting that symptom to logs, source, network behavior, and the failing
environment. FailureLab collects those inputs into one investigation, proposes an
explanation, and tests a bounded intervention before marking a finding supported.

## 2. Why existing CI failure handling is insufficient

Reading a log or rerunning a job can help an engineer investigate, but neither
establishes that a proposed change addresses the failure mechanism. A generated
explanation has the same limitation. FailureLab preserves the failing baseline and
compares it with a reviewed intervention under the same assertions. This project
does not measure existing tools or claim a comparative productivity improvement.

## 3. System architecture

FastAPI exposes ingestion, investigation, artifact, and review APIs to a React and
TypeScript workspace. A LangGraph worker runs collection, retrieval, diagnosis,
planning, execution, and reporting. SQLAlchemy stores cases and events; SQLite and
persistent checkpoints support the local default. PostgreSQL adapters are implemented,
but their deployment path remains unverified locally.

BM25 and exact identifiers order each investigation's evidence. Optional embeddings
and cross-encoder reranking are implemented; the reported live investigation used
lexical retrieval. A separate Linux runner executes an operator-reviewed repository
in a disposable VM. The [architecture](architecture.md) documents the boundaries.

## 4. Investigation workflow

An incident creates a retained evidence snapshot. The diagnosis agent proposes
causes with evidence IDs. The planning agent selects an allowlisted intervention
for an identified hypothesis. Application checks validate both outputs before the
runner executes interleaved baseline and intervention trials. The report computes
its status from experimental results and preserves missing evidence for review.

Chat mode makes actual provider calls at both agent stages. Baseline mode uses
explicit diagnostic signatures and needs no model key. A provider failure stops
chat execution; it does not silently switch modes.

## 5. Evidence model

Evidence has an investigation-local ID, source context, retained content, and hash.
GitHub collection pins the failing commit and bounds downloads and archive reads.
Redaction happens before hashing, so a hash identifies the retained redacted snapshot.
Agents can cite only retrieved IDs. Ground truth and reference repair outputs stay
outside the model input.

The acceptance harness freezes inputs before inference and records implementation
hashes, checkpoints, prompt/tool versions, usage, and artifact associations. Both
incomplete live runs remain in the [release measurement record](validation/release-gate-results.json).
Hash integrity establishes which bytes were retained; interpretation still needs review.

## 6. Intervention model

The model selects a typed action such as `restore_response`, with a rationale and
bounded repetitions. It cannot supply a shell command, disable assertions, or plan
an experiment for an unknown cause. Local actions operate only on owned fixtures.
Repository actions use an authenticated runner and an operator-reviewed manifest
that defines their effect. The model's plan cannot replace that review.

## 7. Deterministic validation

A finding is supported when all baseline trials fail and all intervention trials
pass under the recorded conditions. Mixed results, successful baselines, and
`repeat_baseline` remain inconclusive. Consistent failure after a real intervention
contradicts that tested intervention. Unavailable execution supplies no passing result.

These rules constrain the conclusion to the tested mechanism and environment.
Three trials do not establish a flaky-test rate or unique causality. The separate
16-case signature evaluation measures authored regression behavior; it is not a
held-out measure of LLM accuracy. See the [evaluation methodology](evaluation.md).

## 8. Replay/checkpoint design

Workers claim leased jobs and persist stage checkpoints. Recovery resumes work
while idempotency keys and stored results limit duplicate effects. This is
at-least-once execution with idempotent operations; the external runner's cache
does not survive destruction of its VM.

Completed replay checks investigation identity and report consistency before returning
the preserved result. Missing or corrupt checkpoints stop safely. Pending checkpoints
must match the recorded inference/retrieval configuration and tool-schema hash.
Three replays of the recorded invoice case produced zero new model calls and zero
new Actions jobs, with case data and artifact hashes unchanged.

## 9. Security model

Webhook HMAC validation and delivery deduplication protect ingestion. Repository
allowlists, canonical GitHub paths, bounded archives, and credential-free artifact
redirects constrain evidence acquisition. Runner authentication, reviewed manifests,
fixed argument lists, assertion identity checks, and artifact integrity checks
constrain execution and its returned evidence. Failed inference calls consume the
persistent budget. Provider error events omit raw response bodies and private headers.

The application has one workspace and one trust domain. Bearer authentication does
not provide per-user roles. A disposable Linux VM remains the boundary for repository
code; Docker alone is insufficient. The [security finding review](security-review.md)
records scanner investigations and regression coverage. Passing scans do not certify
arbitrary untrusted execution.

## 10. Unfamiliar incident investigation

A separate authored [invoice repository](https://github.com/MJA0211/failurelab-ci-validation)
displayed `$16,240.00` where its unchanged assertion expected `$162.40`. At commit
`92b61b0eb9a55a73886394979d66cc158f3a99e8`, the API serialized cents as `price`, while
the client interpreted that field as dollars. The ground truth and reviewed repair
controls were frozen before inference and excluded from its inputs.

FailureLab imported actual GitHub logs, source, trace/network evidence, and a
screenshot. Both live stages used `Qwen/Qwen3-235B-A22B-Instruct-2507:novita` through
Hugging Face. The final plan selected `restore_response`; the reviewed harness
converted prices at the response boundary. The
[Linux experiment](https://github.com/MJA0211/failurelab-ci-validation/actions/runs/34720056503)
recorded baseline 0/3 and intervention 3/3, producing `supported`.

Two earlier attempts chose `repeat_baseline` and correctly ended inconclusive for
those experiments. One also supplied an incorrect formatting explanation. Generic
tool descriptions were corrected before the successful third attempt. The original
outputs remain in the [incident report](unfamiliar-ci-validation.md), including the
final diagnosis's omitted quantity in its arithmetic summary. This is an unfamiliar
authored development case, not an independent benchmark. Retrieval returned all
eight evidence items, so it establishes no measured retrieval-filtering improvement.

## 11. Results

| Check | Recorded result |
|---|---|
| Full Python suite | 146 passed; 78% combined statement/branch coverage |
| Focused suites | 136 non-browser; 10 browser; 33 targeted agent/runner; 16 release-gate tests passed |
| Deterministic authored evaluation | 16/16 in each of two variants |
| Static and frontend checks | Ruff, Mypy across 14 source files, production build, and formatting passed |
| Security automation | Zero CodeQL findings in the checked PR analysis; zero npm and known Python dependency vulnerabilities |
| Invoice intervention | Baseline 0/3; intervention 3/3; deterministic `supported` |
| Completed-case replay | Three replays; zero new model calls or Actions jobs |
| Latest four-fixture live attempt | Six successful calls out of seven; three fixtures passed; unknown blocked by HTTP 402 |

The focused suites overlap the 146-test total. The latest live attempt recorded
8,723 input and 704 output tokens on successful calls; cost was unavailable. Its
report timers exclude initial evidence acquisition. These are development
measurements, not production accuracy, scale, or time-savings estimates. Exact
commands and provenance are in the [gate report](releases/v0.1.2-gate.md).

## 12. Release-gate discipline

Version metadata is prepared for `0.1.2`, but no corresponding tag or release exists.
PR #14 remains a draft. The latest live run stopped before the unknown diagnosis;
an earlier run stopped during API-contract planning. Both HTTP 402 failures remain
provider-availability failures, with no abstention or accuracy credit.

Green CI proves that those checks passed. A complete frozen live run, deployment
smoke evidence, and human review are still required before release authorization.
Keeping those conditions visible makes the result assessable by a reviewer.

## 13. Limitations

The evidence uses authored fixtures and a development incident. Independent model
quality, visual inference quality, optional neural retrieval quality, production
capacity, and developer time savings remain unmeasured. Docker/PostgreSQL deployment,
public GitHub webhook delivery, and a permanent private runner endpoint are not
verified locally. Provider availability is external, and human review is pending.

## 14. Lessons learned

The invoice attempts showed why category correctness is insufficient: an agent can
choose `api_contract` while describing the wrong mechanism. They also exposed the
cost of underspecified tools. A correct diagnosis followed by baseline repetition
cannot establish whether repairing the response contract changes the result.

The actual runner integration exposed artifact loss during temporary-checkout cleanup.
Retaining bounded, integrity-checked attachments made the experiment reviewable after
execution. Provider interruptions then made partial-input, checkpoint, and failure
provenance necessary for explaining exactly where acceptance stopped.

## 15. Future work

The immediate work is to complete the frozen live gate after provider payment
availability is restored, run the documented deployment smoke checks with real
infrastructure, and obtain human review. Independent incidents and a frozen held-out
evaluation would be needed for a broader diagnostic-quality claim. Optional retrieval
and deployment adapters need their own measured acceptance before their benefits can
be assessed. These are outstanding validation tasks, not implemented results.
