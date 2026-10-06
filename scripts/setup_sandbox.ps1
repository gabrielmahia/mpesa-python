<#
  Sandbox check for Windows (PowerShell 5.1 or 7). No admin rights needed; installs only under  $HOME\mpesa-sandbox.
  Creates a private Python environment, installs pesa-cli, asks for your Daraja sandbox Consumer Key and Secret (kept in this window only,
  never written to disk), then runs: OAuth -> STK Push of KES 1 to Safaricom's public test phone -> status query.
  Run:  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_sandbox.ps1
  Guide: docs/SANDBOX_SETUP.md
#>
$ErrorActionPreference = "Stop"
$Base = Join-Path $HOME "mpesa-sandbox"
$Venv = Join-Path $Base "venv"
New-Item -ItemType Directory -Force -Path $Base | Out-Null

function Say($t) { Write-Host ""; Write-Host "== $t" -ForegroundColor Cyan }
function Read-Secret($prompt) {
    $s = Read-Host $prompt -AsSecureString
    $b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)
    try { return ([Runtime.InteropServices.Marshal]::PtrToStringBSTR($b)).Trim() }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b) }
}

try {
    Say "Step 1 of 6: looking for Python 3"
    $pyExe = $null; $pyArgs = @()
    foreach ($c in @(@("py", "-3"), @("python"))) {
        if (-not (Get-Command $c[0] -ErrorAction SilentlyContinue)) { continue }
        try {
            $a = @(); if ($c.Count -gt 1) { $a += $c[1] }
            $v = & $c[0] @a --version 2>&1
            if ("$v" -match "^Python 3\.\d+") { $pyExe = $c[0]; $pyArgs = $a; Write-Host "Found: $v"; break }
        } catch { }
    }
    if (-not $pyExe) {
        Write-Host "Python 3 was not found. Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then run this script again." -ForegroundColor Yellow
        return
    }

    Say "Step 2 of 6: creating a private Python environment in $Venv"
    & $pyExe @pyArgs -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw "Could not create the Python environment." }
    $VPy = Join-Path $Venv "Scripts\python.exe"

    Say "Step 3 of 6: installing pesa-cli (this can take a minute)"
    & $VPy -m pip install --quiet --upgrade pip pesa-cli
    if ($LASTEXITCODE -ne 0) { throw "pip could not install pesa-cli." }
    $Pesa = Join-Path $Venv "Scripts\pesa.exe"
    if (-not (Test-Path $Pesa)) { throw "pesa.exe was not created at $Pesa" }
    Write-Host "Installed: $Pesa"

    Say "Step 4 of 6: your Daraja credentials (stay in this window only; nothing is saved to disk)"
    $key = Read-Secret "Click the COPY icon next to Consumer Key in the portal, then paste here and press Enter (nothing will appear as you paste)"
    $sec = Read-Secret "Now the Consumer Secret: copy icon, paste here, press Enter"
    foreach ($p in @(@("Consumer Key", $key), @("Consumer Secret", $sec))) {
        if ($p[1] -match "[\*\s]" -or $p[1].Length -lt 20) {
            throw "$($p[0]) looks wrong (length $($p[1].Length)). Use the portal's copy icon, not selected text, which is masked."
        }
        Write-Host ("{0}: {1} characters received" -f $p[0], $p[1].Length)
    }
    $env:DARAJA_CONSUMER_KEY = $key
    $env:DARAJA_CONSUMER_SECRET = $sec
    $env:DARAJA_ENVIRONMENT = "sandbox"
    $env:PESA_CONFIG = Join-Path $Base "config.json"

    Say "Step 5 of 6: OAuth test ('pesa auth')"
    & $Pesa auth
    if ($LASTEXITCODE -ne 0) {
        Write-Host "OAuth failed. Copy the message above (hide any long token or key) and check docs/SANDBOX_SETUP.md, 'If something fails'." -ForegroundColor Yellow
        return
    }
    Write-Host "OAuth worked." -ForegroundColor Green

    Say "Step 6 of 6: STK Push of KES 1 to Safaricom's public test phone 254708374149"
    $go = Read-Host "Type YES to continue, or press Enter to stop here"
    if ($go -ne "YES") { Write-Host "Stopped after OAuth."; return }
    $raw = (Invoke-WebRequest -UseBasicParsing "https://raw.githubusercontent.com/gabrielmahia/mpesa-python/main/scripts/sandbox_canary.py").Content
    if ($raw -match 'SANDBOX_PASSKEY\s*=\s*"([0-9a-f]{64})"') { $env:DARAJA_PASSKEY = $Matches[1] }
    else { throw "Could not read the public sandbox passkey from the repository file." }
    $env:DARAJA_SHORTCODE = "174379"
    $cb = (Read-Host "Paste your webhook.site URL (it starts with https://)").Trim()
    if (-not $cb.StartsWith("https://")) { throw "The callback URL must start with https://" }
    $env:DARAJA_CALLBACK_URL = $cb
    & $Pesa stk push 254708374149 1 --ref TEST
    if ($LASTEXITCODE -ne 0) { Write-Host "STK Push failed. Check docs/SANDBOX_SETUP.md, 'If something fails'." -ForegroundColor Yellow; return }
    Write-Host ""
    Write-Host "Now look at your webhook.site tab: did a request arrive within about a minute?" -ForegroundColor Green
    $id = (Read-Host "Paste the Checkout ID that starts with ws_CO_ to query its status, or press Enter to skip").Trim()
    if ($id) {
        if (-not $id.StartsWith("ws_CO_")) { throw "That is not a Checkout ID. It must start with ws_CO_" }
        & $Pesa stk query $id
    }
}
finally {
    Remove-Item Env:DARAJA_CONSUMER_KEY, Env:DARAJA_CONSUMER_SECRET, Env:DARAJA_PASSKEY, Env:DARAJA_SHORTCODE, Env:DARAJA_CALLBACK_URL, Env:DARAJA_ENVIRONMENT, Env:PESA_CONFIG -ErrorAction SilentlyContinue
    Write-Host ""; Write-Host "Credentials cleared from this window." -ForegroundColor Cyan
}
