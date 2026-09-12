# Deployment and operations

## Local

The default service binds to 127.0.0.1:8787 and uses SQLite WAL. `scripts/start.ps1`
or `scripts/start.sh` installs locked dependencies, builds the UI, evaluates the
baseline, and serves the application. The foreground server stops with Ctrl+C.
The UI and API share an origin. For frontend development run `npm run dev` in
frontend/; Vite proxies API traffic to port 8787.

## Container

Set a random FAILURELAB_API_TOKEN in `.env`, then run `docker compose up --build`.
The multi-stage image builds the frontend, installs the pinned Python environment
and Chromium, and runs as UID 10001. Compose maps only the loopback port and persists
`/app/var`. A non-loopback application bind refuses to start without an API token.
The browser asks for the token and keeps it in sessionStorage for that tab session.

Docker is not installed in the implementation environment, so the container definition
has not been executed here. Verify the image health check, mounted-volume permissions,
Chromium startup, and the full test suite in your container host before release.

The application container is for orchestration and owned fixtures. It is not a sandbox
for arbitrary repositories. The repository runner needs a separate disposable Linux VM.

## Separate workers and PostgreSQL

Install `uv sync --extra dev --extra postgres`. Configure:

```dotenv
FAILURELAB_DATABASE_URL=postgresql+psycopg://user:password@host/failurelab
FAILURELAB_WORKER_ENABLED=false
FAILURELAB_DATA_DIR=/shared/failurelab
```

Start `failurelab serve` for the API and `failurelab worker` for workers using the
same database and shared artifact directory. LangGraph selects PostgreSQL checkpoints.
Database tables/checkpoint schemas initialize on startup; use a controlled initialization
job and restrict production runtime database privileges after schema creation.

Start with one worker; benchmark before adding more. API ingestion, model inference,
and remote execution have separate latency/resource profiles. The SQL job claim uses
a conditional update, while the queue scans eligible jobs in creation order. Monitor
claim contention, connection counts, disk IO, queue age, and failed attempts. SQLite
is intended for one machine and one worker; do not share its files over network storage.

PostgreSQL and distributed deployment have not been exercised locally. Test those
adapters with a disposable database in the deployment environment.

## Backups and retention

Stop writes and workers for a consistent initial backup. Back up the database,
checkpoints, and artifact directory as a set. SQLite WAL files require a proper
SQLite backup or a cleanly stopped database; copying only failurelab.db while live
is insufficient. For PostgreSQL use coordinated database dumps/snapshots and artifact
snapshots. Encrypt backups and restrict access because logs/screenshots may contain
private repository data. Restore into an isolated workspace and inspect one complete
case, one image, one trace, and its event history before accepting the backup.

No automatic deletion runs. Establish a retention policy appropriate to repository
permissions and team needs; exported reports must follow the same policy.

## Failure recovery

- **Provider failure:** case becomes failed with a sanitized error. Fix configuration
  and use Retry from checkpoint. No baseline substitution occurs.
- **Worker crash:** the lease expires, a worker reclaims the case, and LangGraph resumes.
  Completed owned experiment results and stage events are reused. A heartbeat prevents
  healthy long-running experiments from losing their lease.
- **Expired artifact:** collection records the missing upstream evidence; the model
  must work with the bounded retained inputs and may abstain.
- **Browser missing:** run `uv run playwright install chromium`, then retry.
- **UI unavailable:** run `npm ci && npm run build` in frontend/, then restart the server.
- **External execution unavailable:** findings remain unverified; configure the remote
  runner and select Run again. A new investigation preserves the previous report and
  records its parent ID. Changed model/retrieval configuration also requires Run again
  so old checkpoints cannot be relabeled with a new inference configuration.

`/healthz` checks the application process. `/api/metrics` reports actual investigation
counts and model calls. Monitor dependency availability separately; liveness alone
does not establish provider, database, or external runner readiness.
