<#
  StemTube one-shot patcher (Windows) — enabling auto-updates.

  Installs the in-app updater into an EXISTING StemTube Desktop install, so it
  can patch itself from then on. Nothing to rebuild, nothing to re-download:
  after this runs once, every future fix arrives through the update manifest.

  Why this exists: the Windows installers published so far predate the updater
  (backend shipped 2026-07, updater written 2026-08), so an installed app has
  no way to receive fixes. This drops the missing pieces in.

  Run it with:
      powershell -ExecutionPolicy Bypass -File patcher-windows.ps1

  Safe to re-run: it refreshes the updater and leaves everything else alone.
#>

$ErrorActionPreference = 'Stop'

function Say  ($m) { Write-Host $m -ForegroundColor Green }
function Warn ($m) { Write-Host $m -ForegroundColor Yellow }
function Fail ($m) { Write-Host $m -ForegroundColor Red; exit 1 }

Say "StemTube one-shot patcher (Windows) - enabling auto-updates"

# ── locate the backend ─────────────────────────────────────────────────────
# The Tauri installer puts the app under %LOCALAPPDATA% and names the backend
# folder per edition. Check every known layout rather than guessing one.
$candidates = @(
    "$env:LOCALAPPDATA\StemTube Desktop\stemtube-backend-standard",
    "$env:LOCALAPPDATA\StemTube Desktop\stemtube-backend",
    "$env:LOCALAPPDATA\StemTube Desktop App\stemtube-backend",
    "$env:LOCALAPPDATA\StemTube Desktop Friend\stemtube-backend-friend"
)

$backends = @()
foreach ($c in $candidates) {
    if (Test-Path -LiteralPath (Join-Path $c 'app.py')) { $backends += $c }
}

if ($backends.Count -eq 0) {
    Fail @"
No StemTube install found.

Looked in:
$($candidates -join "`n")

Install StemTube first, launch it once so it downloads its engine, then run
this patcher again.
"@
}

Say "Found $($backends.Count) install(s)."

$UpdaterUrl = 'https://raw.githubusercontent.com/benasterisk/stemtube-desktop-app/main/core/updater.py'

foreach ($backend in $backends) {
    Write-Host ""
    Say "-> $backend"

    # ── 1. the updater module ──────────────────────────────────────────────
    $coreDir = Join-Path $backend 'core'
    if (-not (Test-Path -LiteralPath $coreDir)) { Warn "   no core\ folder - skipped"; continue }

    $updaterPath = Join-Path $coreDir 'updater.py'
    try {
        # Always refresh: a stale updater is the thing we are fixing.
        Invoke-WebRequest -Uri $UpdaterUrl -OutFile $updaterPath -UseBasicParsing -TimeoutSec 60
        Say "   updater installed"
    } catch {
        Warn "   could not download updater.py ($($_.Exception.Message)) - skipped"
        continue
    }

    # ── 2. the hook in app.py ──────────────────────────────────────────────
    # app.py must call the updater before the server starts. The env sentinel
    # makes it a no-op when the launcher already ran it.
    $appPy = Join-Path $backend 'app.py'
    $content = [System.IO.File]::ReadAllText($appPy)

    if ($content -match 'check_and_apply') {
        Say "   hook already present"
    } else {
        $hook = @"
# In-app auto-updater: guarded fallback when app.py is started directly.
# The env sentinel keeps this a no-op when the launcher already ran it.
try:
    if os.environ.get('_STEMTUBE_UPDATE_DONE') != '1':
        from core.updater import check_and_apply as _stemtube_check_updates
        _stemtube_check_updates()
except Exception:
    pass


"@
        # Anchor on the first top-level def, so the hook runs after imports
        # (it needs `os`) but before anything starts serving.
        $idx = $content.IndexOf("`ndef ")
        if ($idx -lt 0) { Warn "   could not find an insertion point - hook skipped"; continue }

        $patched = $content.Substring(0, $idx + 1) + $hook + $content.Substring($idx + 1)

        # Keep a one-time backup of the original app.py.
        $bak = "$appPy.orig"
        if (-not (Test-Path -LiteralPath $bak)) { Copy-Item -LiteralPath $appPy -Destination $bak }

        # UTF-8 without BOM: a BOM before the first statement breaks Python.
        [System.IO.File]::WriteAllText($appPy, $patched, [System.Text.UTF8Encoding]::new($false))
        Say "   hook installed (original saved as app.py.orig)"
    }
}

Write-Host ""
Say "Auto-updates enabled."
Write-Host "   StemTube will check for updates on start and patch itself."
Write-Host "   Launch it as usual."
