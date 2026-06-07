param(
    [string]$ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [int]$Port = 8765,
    [switch]$NoTailscaleServe
)

$ErrorActionPreference = "Stop"

$python = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$runPy = Join-Path $ProjectDir "run.py"
$logDir = Join-Path $env:USERPROFILE ".job_bot"
if (!(Test-Path $python)) {
    throw "Python venv not found: $python"
}
if (!(Test-Path $runPy)) {
    throw "run.py not found: $runPy"
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Test-JobBotLocal {
    try {
        Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 3 | Out-Null
        return $true
    } catch {
        if ($_.Exception.Response) {
            return $true
        }
        return $false
    }
}

$localAlive = Test-JobBotLocal
if (-not $localAlive) {
    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $python
    $psi.Arguments = "`"$runPy`""
    $psi.WorkingDirectory = $ProjectDir
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    [System.Diagnostics.Process]::Start($psi) | Out-Null
    foreach ($i in 1..12) {
        Start-Sleep -Seconds 1
        $localAlive = Test-JobBotLocal
        if ($localAlive) { break }
    }
}

if (-not $NoTailscaleServe) {
    $tailscale = Join-Path $env:ProgramFiles "Tailscale\tailscale.exe"
    if (Test-Path $tailscale) {
        & $tailscale serve --yes --bg --tcp=$Port "127.0.0.1:$Port" | Out-Null
    }
}

$status = [ordered]@{
    project = $ProjectDir
    localUrl = "http://127.0.0.1:$Port"
    tailscaleUrl = "http://<TAILSCALE_IP>:$Port"
    portListening = [bool](Test-JobBotLocal)
}

[PSCustomObject]$status | ConvertTo-Json
