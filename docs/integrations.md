# Integrations

## GitHub

Set server environment variables:

```dotenv
FAILURELAB_GITHUB_REPOSITORIES=your-org/your-app
FAILURELAB_GITHUB_TOKEN=<fine-grained token>
FAILURELAB_WEBHOOK_SECRET=<random webhook secret>
```

Use the minimum repository read permissions needed for Actions, metadata, and contents.
Public endpoints may work without a token; artifact downloads commonly require access.
Never use a token with administration permissions just to investigate CI failures.

Open New investigation → GitHub Actions and supply the numeric workflow run ID.
Supply the optional exact Playwright test title when requesting remote reproduction;
otherwise the workflow name is retained as the investigation label. Webhook-created
cases use the workflow name; create a manual snapshot with the exact test title before
requesting a targeted repository reproduction.
FailureLab collects metadata first. The worker then collects failed jobs for that run
attempt, commit patches at the exact SHA, and available artifacts. Missing/expired
artifacts produce warnings; FailureLab does not invent the missing evidence. Retained
text is bounded and redacted. Ingestion includes the first 12 changed file patches,
four failed job logs, and three bounded artifact archives. These limits may omit
relevant evidence and must be considered during review. Truncation preserves the tail
of logs.

Webhook URL: `https://your-host/api/webhooks/github`; event: **Workflow runs**;
content type: JSON; secret: the configured value. Failed or timed-out completed runs
are queued. HMAC-SHA256 is validated over the raw body before ingestion. Duplicate
deliveries return the same case ID. The API returns before the investigation executes.

Enable Playwright tracing/screenshots and upload artifacts as shown under `examples/`.
Downloads honor size/expansion limits; nested trace archives are read only one level
deep. Storage redirects use a credential-free client and a GitHub storage host allowlist.

## npm

The integrations screen requests `GET https://registry.npmjs.org/<package>/<version>`
and displays a bounded selection of fields. Supply the exact installed version from
the lockfile, not an assumed latest version. This is an analyst tool; it does not
automatically rewrite dependency versions or claim to resolve incompatibilities.

## Model provider

The adapter calls `<MODEL_BASE_URL>/chat/completions` with JSON-schema instructions,
temperature zero, bounded output tokens, and an optional PNG. It requires a provider
that supports chat-completion JSON responses. Credentials remain server-side.
Non-200 responses and invalid model outputs fail the investigation explicitly.

For a tested text-model configuration and an opt-in check of both agent stages plus
browser execution, see [live agent verification](live-agent-verification.md). HTTP 402
requires resolving provider billing or credit before another live call can succeed.

Set input/output prices per million tokens to estimate model cost. Cost stays unknown
when pricing is missing and excludes hosting, retrieval, and browser execution.
The provider reports token counts. Durable events and report usage provide local
LLMOps observability without requiring another external service.

## Optional hybrid retrieval

Install `uv sync --extra dev --extra ml`, set RETRIEVAL_MODE=hybrid, and restart.
The first call downloads the configured sentence-transformer and cross-encoder.
Models can be pre-cached with Hugging Face's normal cache environment variables.
Model load failures are explicit; there is no hidden lexical fallback.
