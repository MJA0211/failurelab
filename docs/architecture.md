# Architecture

## Workflow

An ingestion request creates an investigation and snapshots its evidence. The
transactional store deduplicates GitHub deliveries by repository, run, and attempt.
A worker claims a queued case with a compare-and-swap update. The lease renews every
20 seconds; an abandoned lease becomes eligible for recovery. Three infrastructure
attempts are allowed before explicit manual retry.

The LangGraph sequence is `collect → retrieve → diagnose → plan → execute → report`.
The workflow uses SQLite checkpoints locally and selects PostgreSQL checkpoints when
the database URL is PostgreSQL. A restarted worker reads the same investigation thread
and resumes from its last checkpoint. Events have unique stage keys. Owned experiment
results are atomically written and reused when a node replays.

If a failure occurs after an external operation but before the checkpoint commits,
recovery can replay that operation. External runners receive idempotency keys to
handle these replays. This is at-least-once execution with idempotent effects, not a
claim of universal exactly-once execution.

## Agents and retrieval

The diagnosis agent receives only this investigation's evidence, never a global
unfiltered corpus. GitHub code comes from the failing commit. BM25 and exact identifiers
provide the default ordering. Optional dense cosine retrieval contributes a second
ranking through reciprocal rank fusion; a cross-encoder reranks the candidates.
Models load lazily and are cached per process. Evidence IDs and content hashes remain
stable as ranking changes.

The experiment agent proposes an allowlisted intervention with bounded repetitions.
Pydantic validates hypotheses, citation IDs, experiment references, counts, and tool
names. A generated `supported` status is discarded before verification. Document
instructions are untrusted content; the model has no shell tool.

The baseline engine recognizes explicit failure signatures in logs. It uses a simple
approach, labeled in every report. Retrieval and screenshot adapters are implemented,
but the baseline does not interpret pixels. Chat mode can send a screenshot to a
vision-capable provider.

## Verification

Owned fixtures use static HTML and fixed application-owned interventions. Network
requests are blocked. Each condition receives a fresh browser context. Baseline and
intervention runs are interleaved, with identical viewport and browser version.
Screenshots and traces are captured for the first pair.

A mechanism is supported only when all baseline runs fail and all intervention runs
pass. An ineffective intervention with consistently failing runs contradicts the
specific tested intervention; it does not disprove every variant of the broad cause.
Mixed results, successful baselines, and repeat-baseline experiments are inconclusive.
Unavailable external execution never becomes a successful or failed experiment.

This controlled comparison is evidence of a mechanism under the recorded environment,
not proof of unique causality. Small sample counts do not establish flaky-test rates.

## Persistence and interfaces

SQLAlchemy stores investigations, append-only events, and reviews. JSON payloads keep
the initial model simple and portable. Artifact names are generated and constrained;
archive paths are never extracted. Evidence content is redacted before hashing and
storage. Hashes identify the retained redacted snapshot, not the upstream unredacted file.

The UI uses the same-origin API, polls live cases, and maintains a case ID in the URL.
It renders content as text, fetches authenticated image blobs, and exports versioned
reports. Reviews append an opinion without rewriting evidence or experimental outcomes.

## Deliberate operational scope

The application has one workspace and one trust domain. SQLite supports the local
single-worker deployment. PostgreSQL supports separate API and worker processes, but
all workers must share artifact storage. The provided application uses a filesystem
artifact store; a shared
mounted volume is required for distributed workers. Database and filesystem backup
must be coordinated. No unmeasured million-document or high-concurrency claim is made.
