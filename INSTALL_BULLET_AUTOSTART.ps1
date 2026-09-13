param(
    [string]$TaskName = "BULLET Autonomous Startup",
    [int]$StartupDelaySeconds = 30
)

$ErrorActionPreference = "Stop"
$ScriptPath = $PSCommandPath
if (-not $ScriptPath) {
    $ScriptPath = $MyInvocation.MyCommand.Path
}
if (-not $ScriptPath) {
    throw "Unable to determine the installer script path."
}

$ProjectRoot = Split-Path -Parent $ScriptPath
$Launcher = Join-Path $ProjectRoot "START_BULLET.ps1"

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Relaunch-Elevated {
    param(
        [string]$InstallerPath,
        [string]$RequestedTaskName,
        [int]$RequestedStartupDelaySeconds
    )

    $quotedScript = $InstallerPath.Replace("'", "''")
    $quotedTaskName = $RequestedTaskName.Replace("'", "''")
    $args = "-NoProfile -ExecutionPolicy Bypass -File '$quotedScript' -TaskName '$quotedTaskName' -StartupDelaySeconds $RequestedStartupDelaySeconds"
    Start-Process powershell.exe -Verb RunAs -ArgumentList $args | Out-Null
}

Write-Host "============================================================"
Write-Host "BULLET P0 Auto-Startup Installer"
Write-Host "============================================================"
Write-Host "Project root : $ProjectRoot"
Write-Host "Task name    : $TaskName"
Write-Host "Startup delay: $StartupDelaySeconds seconds"

if (-not (Test-Path $Launcher)) {
    throw "START_BULLET.ps1 was not found at: $Launcher"
}

if (-not (Test-IsAdministrator)) {
    Write-Host "Administrator privileges are required to register the scheduled task."
    Write-Host "Requesting elevation..."
    Relaunch-Elevated -InstallerPath $ScriptPath -RequestedTaskName $TaskName -RequestedStartupDelaySeconds $StartupDelaySeconds
    exit 0
}

$currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
Write-Host "Windows user : $currentIdentity"

# Remove a previous copy so the installer is safe to rerun.
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Existing task found. Replacing it..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$escapedLauncher = $Launcher.Replace("'", "''")
$command = "& { Start-Sleep -Seconds $StartupDelaySeconds; & '$escapedLauncher' -Headless }"
$actionArgs = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command `"$command`""

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument $actionArgs `
    -WorkingDirectory $ProjectRoot

# MT5 is a desktop application, so run the task in the user's interactive logon session.
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentIdentity
$principal = New-ScheduledTaskPrincipal `
    -UserId $currentIdentity `
    -LogonType Interactive `
    -RunLevel Highest

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

$description = "P0 recovery: after Windows logon, waits $StartupDelaySeconds seconds and launches START_BULLET.ps1 -Headless. The launcher starts MT5 if needed and prevents duplicate BULLET instances."

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description $description | Out-Null

$task = Get-ScheduledTask -TaskName $TaskName
$info = Get-ScheduledTaskInfo -TaskName $TaskName

Write-Host ""
Write-Host "BULLET auto-start installed successfully."
Write-Host "Task state   : $($task.State)"
Write-Host "Last result  : $($info.LastTaskResult)"
Write-Host ""
Write-Host "The task will run when $currentIdentity logs into Windows."
Write-Host "For a manual test without rebooting, run:"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
Write-Host "To inspect it later:"
Write-Host "  Get-ScheduledTask -TaskName '$TaskName'"
Write-Host "  Get-ScheduledTaskInfo -TaskName '$TaskName'"
