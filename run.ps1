# One command: install, test, then verify every statement.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv not found: https://docs.astral.sh/uv/"
}

uv sync --quiet
uv run pytest -q
Set-Location backend
uv run python -m app.cli verify @args
