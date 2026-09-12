#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
uv sync --frozen --extra dev
uv run playwright install --with-deps chromium
(cd frontend && npm ci && npm run build)
uv run failurelab evaluate
exec uv run failurelab serve
