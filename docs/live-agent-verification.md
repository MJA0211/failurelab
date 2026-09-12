# Live agent verification

On September 12, 2026, FailureLab completed four fresh owned-fixture investigations
using `Qwen/Qwen3-235B-A22B-Instruct-2507:novita` through Hugging Face's chat router.
Both diagnosis and experiment planning made real provider calls. Vision was disabled;
retrieval used BM25 and exact identifiers. Browser execution used local Chromium.

## Observed results

With prompt version `failurelab-agents-v2`, the run recorded eight successful model
calls, 10,903 input tokens, and 885 output tokens reported by the provider.

| Owned fixture | Baseline passes | Intervention passes | Result |
|---|---:|---:|---|
| Overlay | 0/3 | 3/3 | Supported; `remove_overlay` |
| Renamed selector | 0/3 | 3/3 | Supported; `restore_selector` |
| API response mismatch | 0/3 | 3/3 | Supported; `restore_response` |
| Missing artifacts | No experiment | No experiment | Unknown cause; inconclusive; missing evidence reported |

Each positive case retained baseline/intervention PNGs and Playwright traces, with
SHA-256 hashes recorded in the local acceptance report. The successful run is stored
under ignored `var/live-acceptance/f4e6bc4371654b8d976da7e29ac85e81/`. Provider credentials,
runtime databases, and raw traces are not published.

## Failure found during acceptance

The first run, with `failurelab-agents-v1`, passed the three reproducible cases but
failed the missing-artifact check. The model used general runbook examples to propose
specific causes and planned an unsupported intervention. The runner returned
`unavailable`, and the final verdict remained inconclusive.

Version 2 distinguishes incident observations from general runbook advice and asks
for one unknown hypothesis when observations do not support a specific cause. The
planner now rejects experiments targeting an unknown cause. A contract test covers
that rejection and permits an empty experiment list. The revised prompt passed all
four cases on the next fresh run. This is a development check used to improve the
prompt, not an independent test of generalization.

A subsequent run of the published acceptance script and the 16-case live evaluation
were interrupted by HTTP 402 Payment Required. No baseline substitution occurred.
There is no completed live evaluation score from that attempt. The published script
includes additional reporting and a missing-evidence assertion; a complete successful
run of that final script still requires provider credit.

The application test suite passed **122 tests** in 74.15 seconds. The frontend
production build passed, and npm audit reported zero vulnerabilities.

## Reproduce

Configure `.env` locally with a funded provider token:

```dotenv
FAILURELAB_MODEL_MODE=chat
FAILURELAB_MODEL_BASE_URL=https://router.huggingface.co/v1
FAILURELAB_MODEL_NAME=Qwen/Qwen3-235B-A22B-Instruct-2507:novita
FAILURELAB_MODEL_API_KEY=<your provider token>
FAILURELAB_MODEL_VISION=false
```

After installing the project and Playwright Chromium, run:

```sh
uv run python scripts/verify_live_agents.py
```

This opt-in check makes at most eight model calls, creates a new local SQLite
workspace under `var/live-acceptance/`, and stops at the first failed case. It does
not use completed checkpoints from earlier runs. Its report checks both model stages,
diagnosis, experimental outcomes, retained artifacts, and abstention. Keep the output
from failed attempts as well as successful ones.

The separate authored diagnosis evaluation makes up to 32 provider calls:

```sh
uv run failurelab evaluate --model --min-accuracy 0.8
```

Model availability and account credit affect whether these commands can run. See
[Hugging Face billing](https://huggingface.co/docs/inference-providers/pricing).

These results establish live integration on owned synthetic fixtures. They do not
establish held-out diagnostic accuracy, visual inference quality, production capacity,
or developer time savings. PostgreSQL, Docker, and remote repository runner acceptance
remain separate unverified deployment paths.
