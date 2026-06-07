param(
    [string]$ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$TaskName = "JobBot Dashboard",
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"

$startScript = Join-Path $ProjectDir "scripts\start_jobbot_windows.ps1"
if (!(Test-Path $startScript)) {
    throw "Startup script not found: $startScript"
}

$taskArgs = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$startScript`"",
    "-ProjectDir", "`"$ProjectDir`"",
    "-Port", $Port
) -join " "

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $taskArgs
$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 12)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Starts JobBot dashboard and Tailscale Serve for tailnet-only remote access." `
    -Force | Out-Null

Write-Output "Installed scheduled task: $TaskName"
Write-Output "To run now: Start-ScheduledTask -TaskName `"$TaskName`""
Write-Output "To remove: Unregister-ScheduledTask -TaskName `"$TaskName`" -Confirm:`$false"
