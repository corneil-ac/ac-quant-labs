param(
    [switch]$Headless,
    [int]$Mt5WaitSeconds = 60
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogsDir = Join-Path $ProjectRoot "logs"
$DataDir = Join-Path $ProjectRoot "data"
$MainPy = Join-Path $ProjectRoot "main.py"
$StartupLog = Join-Path $LogsDir ("startup_{0}.log" -f (Get-Date -Format "yyyyMMdd"))

New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null

function Write-StartupLog {
    param([string]$Message, [string]$Level = "INFO")
    $line = "{0} [{1}] {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Level, $Message
    Write-Host $line
    Add-Content -Path $StartupLog -Value $line
}

function Find-Mt5Executable {
    $running = Get-CimInstance Win32_Process -Filter "Name='terminal64.exe'" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($running -and $running.ExecutablePath -and (Test-Path $running.ExecutablePath)) {
        return $running.ExecutablePath
    }

    $candidates = @(
        (Join-Path $env:ProgramFiles "MetaTrader 5\terminal64.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "MetaTrader 5\terminal64.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\MetaTrader 5\terminal64.exe")
    ) | Where-Object { $_ -and (Test-Path $_) }

    if ($candidates.Count -gt 0) {
        return $candidates[0]
    }

    $roots = @($env:ProgramFiles, ${env:ProgramFiles(x86)}, (Join-Path $env:LOCALAPPDATA "Programs")) |
        Where-Object { $_ -and (Test-Path $_) }

    foreach ($root in $roots) {
        $found = Get-ChildItem -Path $root -Filter "terminal64.exe" -File -Recurse -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($found) {
            return $found.FullName
        }
    }

    return $null
}

function Test-PythonCommand {
    param([string]$Command, [string[]]$PrefixArgs = @())
    try {
        $output = & $Command @PrefixArgs --version 2>&1
        if ($LASTEXITCODE -eq 0 -and ($output -join " ") -match "Python\s+\d") {
            return $true
        }
    } catch {}
    return $false
}

function Resolve-Python {
    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return @{ File = $venvPython; Prefix = @(); Label = ".venv" }
    }

    $venvPython2 = Join-Path $ProjectRoot "venv\Scripts\python.exe"
    if (Test-Path $venvPython2) {
        return @{ File = $venvPython2; Prefix = @(); Label = "venv" }
    }

    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py -and (Test-PythonCommand -Command $py.Source -PrefixArgs @("-3"))) {
        return @{ File = $py.Source; Prefix = @("-3"); Label = "py -3" }
    }

    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($python -and (Test-PythonCommand -Command $python.Source)) {
        return @{ File = $python.Source; Prefix = @(); Label = "python" }
    }

    return $null
}

function Get-BulletProcess {
    $escapedMain = [regex]::Escape($MainPy)
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            ($_.Name -match "^python(w)?\.exe$" -or $_.Name -eq "py.exe") -and
            $_.CommandLine -and
            ($_.CommandLine -match $escapedMain -or $_.CommandLine -match "(^|\s)main\.py(\s|$)")
        } |
        Select-Object -First 1
}

Write-StartupLog "============================================================"
Write-StartupLog "BULLET P0 startup sequence initiated."
Write-StartupLog "Project root: $ProjectRoot"

if (-not (Test-Path $MainPy)) {
    Write-StartupLog "main.py not found at $MainPy" "ERROR"
    exit 10
}

# 1) Make sure MetaTrader 5 is running.
$mt5 = Get-Process terminal64 -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $mt5) {
    $mt5Exe = Find-Mt5Executable
    if (-not $mt5Exe) {
        Write-StartupLog "Could not locate terminal64.exe. Start MT5 manually once, then rerun this script." "ERROR"
        exit 20
    }

    Write-StartupLog "MT5 is not running. Starting: $mt5Exe"
    Start-Process -FilePath $mt5Exe | Out-Null
} else {
    Write-StartupLog "MT5 is already running (PID $($mt5.Id))."
}

# 2) Wait for the terminal process to become available.
$deadline = (Get-Date).AddSeconds($Mt5WaitSeconds)
do {
    $mt5 = Get-Process terminal64 -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($mt5) { break }
    Start-Sleep -Seconds 2
} while ((Get-Date) -lt $deadline)

if (-not $mt5) {
    Write-StartupLog "MT5 did not start within $Mt5WaitSeconds seconds." "ERROR"
    exit 21
}

Write-StartupLog "MT5 process detected (PID $($mt5.Id)). Waiting 8 seconds for terminal initialization."
Start-Sleep -Seconds 8

# 3) Prevent duplicate BULLET instances.
$existingBullet = Get-BulletProcess
if ($existingBullet) {
    Write-StartupLog "BULLET is already running (PID $($existingBullet.ProcessId)). No duplicate instance will be started." "WARN"
    exit 0
}

# 4) Resolve a real Python interpreter, avoiding the Microsoft Store alias trap.
$python = Resolve-Python
if (-not $python) {
    Write-StartupLog "No usable Python installation was found (.venv, venv, py -3, or python)." "ERROR"
    exit 30
}

Write-StartupLog "Python resolved via: $($python.Label)"

# 5) Start BULLET.
$bulletOut = Join-Path $LogsDir "bullet_stdout.log"
$bulletErr = Join-Path $LogsDir "bullet_stderr.log"
$args = @($python.Prefix) + @($MainPy)

if ($Headless) {
    Write-StartupLog "Starting BULLET in headless recovery mode."
    $proc = Start-Process -FilePath $python.File `
        -ArgumentList $args `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput $bulletOut `
        -RedirectStandardError $bulletErr `
        -WindowStyle Hidden `
        -PassThru
} else {
    Write-StartupLog "Starting BULLET in a visible PowerShell window."

    $quotedProject = $ProjectRoot.Replace("'", "''")
    $quotedPython = $python.File.Replace("'", "''")
    $prefixText = ($python.Prefix | ForEach-Object { "'" + $_.Replace("'", "''") + "'" }) -join " "
    $quotedMain = $MainPy.Replace("'", "''")

    $command = "Set-Location '$quotedProject'; & '$quotedPython'"
    if ($prefixText) { $command += " $prefixText" }
    $command += " '$quotedMain'"

    $proc = Start-Process powershell.exe `
        -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $command) `
        -WorkingDirectory $ProjectRoot `
        -PassThru
}

Start-Sleep -Seconds 5

if ($proc.HasExited) {
    Write-StartupLog "BULLET process exited during startup with code $($proc.ExitCode). Check $bulletErr and normal BULLET logs." "ERROR"
    exit 40
}

Write-StartupLog "BULLET startup process launched successfully (PID $($proc.Id))."
Write-StartupLog "Startup sequence complete."
exit 0
