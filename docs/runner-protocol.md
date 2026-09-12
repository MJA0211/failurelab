# Isolated repository runner

The local API server never runs imported code. The implemented repository runner is
`failurelab.runner_service:create_runner_app`, deployed separately in a **disposable
Linux VM**. Repository code is arbitrary code: the VM, restricted network, resource
limits, and destruction policy are the isolation boundary. Do not run the service on
your laptop or in the API container.

## Setup

Provision a Linux VM with Python, the FailureLab environment, Node 22, Git, and the
Playwright browser dependencies. Use no cloud instance role, no mounted credentials,
no host mounts, and deny metadata endpoints and access to private networks. Permit
only required GitHub/npm download endpoints during preparation and local application
traffic during execution. A repository that needs external services requires an
explicit separately reviewed network policy and deterministic test data.

Define a `.failurelab/runner.json` in the target repository using the example below.
Review its behavior and compute the SHA-256 of its exact bytes. Set these **runner-side**
variables; the token must contain at least 24 random characters:

```sh
export FAILURELAB_RUNNER_TOKEN='<random shared secret>'
export FAILURELAB_RUNNER_MANIFESTS='{"owner/repo":"<reviewed manifest SHA-256>"}'
uv run uvicorn failurelab.runner_service:create_runner_app --factory --host 0.0.0.0 --port 9090
```

Expose the service only through a private authenticated TLS endpoint reachable by
the orchestrator. Configure FAILURELAB_RUNNER_URL and FAILURELAB_RUNNER_TOKEN on
the orchestrator. Destroy/recreate the VM between untrusted repositories; a service
lock serializes jobs but is not a substitute for VM lifecycle isolation.

## Repository contract

```json
{
  "version": 1,
  "interventions": {
    "remove_overlay": { "env": { "FAILURELAB_DISABLE_OVERLAY": "1" } },
    "restore_selector": { "env": { "FAILURELAB_RESTORE_SELECTOR": "1" } },
    "restore_response": { "env": { "FAILURELAB_RESTORE_RESPONSE": "1" } }
  }
}
```

The repository's reviewed reproduction harness must implement these toggles at the
application boundary, preserving assertions. Include a package-lock.json and
@playwright/test. Playwright configuration must use a deterministic local webServer,
reset test data between runs, avoid retries, and support the selected test-name grep.
The runner verifies that the selected assertion identities remain identical and
rejects missing, skipped, retried, or expected-failing tests.

This is a bounded reproduction harness contract. It does not automatically invent
valid interventions for arbitrary projects or claim universal bug reproduction.

## HTTP contract

`POST /experiments`, `Authorization: Bearer <token>`, `Idempotency-Key: <case:plan>`.

```json
{
  "repository": "owner/repo",
  "commit_sha": "0123456789abcdef0123456789abcdef01234567",
  "test_name": "checkout completes",
  "plan": {
    "hypothesis_id": "h1",
    "intervention": "remove_overlay",
    "rationale": "Test whether the overlay blocks the intended interaction",
    "repetitions": 3
  }
}
```

The runner fetches exactly that commit, verifies the manifest digest, installs locked
dependencies with lifecycle scripts disabled, and invokes the installed Playwright
CLI without a shell. Child processes do not receive runner credentials. Timeouts kill
the whole process group, including surviving web servers. Each condition uses fresh
Playwright processes; the repository harness must reset any disk/database state.

Responses use the ExperimentResult schema in `/openapi.json`: pass counts, repetitions,
observations, duration, and environment hashes. The orchestrator validates counts and
recomputes verdicts. HTTP 401 rejects authentication, 403 rejects unreviewed repositories,
429 indicates a busy runner, and 422 indicates a failed reproduction contract.

Result caching uses the idempotency key plus request digest. The cache lives inside
the runner VM unless an isolated result store is provisioned. No repository code is
permitted to access shared orchestrator artifacts or credentials.

Protocol/parser/manifest tests run locally. An actual Linux VM repository execution
has not been performed in the Windows implementation environment.
