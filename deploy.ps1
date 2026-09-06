# Deploy the console to Vercel.
#
#   .\deploy.ps1 vcp_YOUR_TOKEN_HERE
#
# Get the token at https://vercel.com/account/tokens — Create Token, scope
# `dimknaf`, any expiry. It is the only step a person has to do: Vercel removed
# email login in February 2026 and OAuth needs a browser, so there is no way for
# an automated session to authenticate on its own.
#
# Everything after that is here.

param([Parameter(Mandatory = $true)][string]$Token)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$dist = Join-Path $repo "backend\test-simple-frontend\dist"

# The token goes in the environment, never on a command line — arguments are
# visible to every other process on the machine.
$env:VERCEL_TOKEN = $Token.Trim()

Write-Host "`n1. rebuilding the site" -ForegroundColor Cyan
Push-Location $repo
uv run python backend/test-simple-frontend/build_static.py `
  --batch 20260906-095528 --batch 20260905-191924
Pop-Location

Write-Host "`n2. checking the token" -ForegroundColor Cyan
$who = vercel whoami 2>&1
if ($LASTEXITCODE -ne 0) {
  Write-Host "   the token was rejected:" -ForegroundColor Red
  Write-Host "   $who"
  Write-Host "   make a new one at https://vercel.com/account/tokens"
  exit 1
}
Write-Host "   authenticated as $who" -ForegroundColor Green

# Deployed from inside dist/ rather than from the repository root. dist/ is the
# finished site and carries its own vercel.json, so nothing has to build on
# Vercel's machines and the rewrites are read from the directory being uploaded.
# The root vercel.json points `outputDirectory` at a nested path, which no
# Vercel documentation example uses — this route cannot hit that.
Write-Host "`n3. deploying $dist" -ForegroundColor Cyan
Push-Location $dist
$url = vercel deploy --prod --yes --archive=tgz 2>&1 | Select-Object -Last 1
Pop-Location

if ($LASTEXITCODE -ne 0) {
  Write-Host "`n   deploy failed:" -ForegroundColor Red
  Write-Host "   $url"
  exit 1
}

Write-Host "`n4. checking every path the console fetches" -ForegroundColor Cyan
$run = "20260906-095528-GBP_3252"
$paths = @(
  "/", "/api/health", "/api/runs", "/api/profiles", "/api/statements",
  "/api/examples", "/api/runs/$run", "/api/runs/$run/trace",
  "/api/runs/$run/rows", "/api/runs/$run/rows-extract",
  "/api/runs/$run/rows-resolve", "/api/runs/$run/file/summary.json"
)
$bad = 0
foreach ($p in $paths) {
  try {
    $code = (Invoke-WebRequest -Uri "$url$p" -Method Head -SkipHttpErrorCheck).StatusCode
  } catch { $code = "ERR" }
  $colour = if ($code -eq 200) { "Green" } else { "Red"; }
  if ($code -ne 200) { $bad++ }
  Write-Host ("   {0,-46} {1}" -f $p, $code) -ForegroundColor $colour
}

Write-Host ""
if ($bad -eq 0) {
  Write-Host "  LIVE  $url" -ForegroundColor Green
} else {
  Write-Host "  $url — but $bad path(s) did not return 200." -ForegroundColor Yellow
  Write-Host "  Most likely the three rewrites in dist/vercel.json. Send me the list."
}
Write-Host ""
