[CmdletBinding()]
param([switch]$Check)

$ErrorActionPreference = 'Stop'
$projectFolder = Split-Path -Parent $PSScriptRoot
$buildFolder = Join-Path $projectFolder 'build-windows-tools'
$playExecutable = Join-Path $buildFolder 'ttt2-play.exe'
$gameExecutable = Join-Path $buildFolder 'ttt2-ultimate.exe'
$launchLog = Join-Path $buildFolder 'launch.log'
$reader = $null

try {
    if (-not (Test-Path -LiteralPath $playExecutable -PathType Leaf)) { throw "Launcher missing: $playExecutable" }
    if (-not (Test-Path -LiteralPath $gameExecutable -PathType Leaf)) { throw "Game executable missing: $gameExecutable" }
    if ($Check) {
        & $playExecutable --check
        exit $LASTEXITCODE
    }
    $Host.UI.RawUI.WindowTitle = 'TTT2 Ultimate - starting'
    Write-Host 'Starting TTT2 Ultimate...' -ForegroundColor Cyan
    Write-Host 'Loading fighter packs can take a minute. Live output appears below.'
    Write-Host "Log: $launchLog"
    Write-Host 'This window closes when the game window opens.'
    Write-Host 'Closing this console will not stop a game that has already started.'
    Write-Host ''
    $existing = Get-Process -Name 'ttt2-ultimate' -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -eq $gameExecutable } | Select-Object -First 1
    if ($existing) {
        Write-Host 'TTT2 is already starting or running. Check its existing window.' -ForegroundColor Yellow
        Read-Host 'Press Enter to close this console'
        exit 0
    }
    $env:TTT2_UNLOCK_UNKNOWN = '1'
    # Temporary aggregated performance measurements; gameplay traces stay off.
    Remove-Item Env:TTT2_TRACE_ASSIST_FOLLOW -ErrorAction SilentlyContinue
    Remove-Item Env:TTT2_TRACE_CPU -ErrorAction SilentlyContinue
    $env:TTT2_PERF = '1'
    $launcher = Start-Process -FilePath $playExecutable -WorkingDirectory $buildFolder -WindowStyle Hidden -PassThru
    # -Wait waits for the entire descendant tree, including the game.
    # Wait only for the small launcher, then monitor/log the game separately.
    $launcher.WaitForExit()
    if ($launcher.ExitCode -ne 0) { throw "The game launcher exited with code $($launcher.ExitCode)." }
    $file = [IO.File]::Open($launchLog, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    $reader = New-Object IO.StreamReader($file)
    $clock = [Diagnostics.Stopwatch]::StartNew()
    $heartbeat = 0
    while ($true) {
        while ($null -ne ($line = $reader.ReadLine())) { Write-Host $line }
        $game = Get-Process -Name 'ttt2-ultimate' -ErrorAction SilentlyContinue |
            Where-Object { $_.Path -eq $gameExecutable } | Select-Object -First 1
        if (-not $game) { throw "The game stopped before opening its window. See the log above: $launchLog" }
        $game.Refresh()
        if ($game.MainWindowHandle -ne [IntPtr]::Zero) {
            Write-Host 'Game window ready.' -ForegroundColor Green
            break
        }
        if ($clock.Elapsed.TotalSeconds -ge $heartbeat + 10) {
            $heartbeat = [int]$clock.Elapsed.TotalSeconds
            Write-Host "Still loading... $heartbeat seconds elapsed." -ForegroundColor Cyan
        }
        Start-Sleep -Milliseconds 250
    }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    Read-Host 'Press Enter to close this console'
    exit 1
} finally {
    if ($null -ne $reader) { $reader.Dispose() }
}
