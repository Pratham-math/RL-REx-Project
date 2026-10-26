$ErrorActionPreference = 'Stop'
$rexTarget = Join-Path (Get-Location) 'vendor/REx'
if (-not (Test-Path -LiteralPath $rexTarget)) {
    git clone https://github.com/haotang1995/REx.git $rexTarget
    if ($LASTEXITCODE -ne 0) { throw 'Upstream fetch failed' }
}
git -C $rexTarget checkout --detach 371e879da5b1fff0d32a695ad37dcac50f74721b
if ($LASTEXITCODE -ne 0) { throw 'Upstream pin failed; preserve any existing modifications' }
git -C $rexTarget rev-parse HEAD
Get-FileHash -Algorithm SHA256 (Join-Path $rexTarget 'LICENSE')
