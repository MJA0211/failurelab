param([int]$Port = 8787)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    uv sync --frozen --extra dev
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
    uv run playwright install chromium
    if ($LASTEXITCODE -ne 0) { throw 'Chromium installation failed' }
    Push-Location -LiteralPath (Join-Path $projectRoot 'frontend')
    try {
        npm ci
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
    } finally { Pop-Location }
    uv run failurelab evaluate
    if ($LASTEXITCODE -ne 0) { throw 'Regression evaluation failed' }
    uv run failurelab serve --port $Port
} finally { Pop-Location }
