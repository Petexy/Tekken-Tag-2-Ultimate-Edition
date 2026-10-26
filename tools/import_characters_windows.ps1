[CmdletBinding()]
param(
    [string]$GameDirectory = (Join-Path $env:USERPROFILE 'Games/TekkenTag2Ultimate'),
    [string]$OutDirectory = (Join-Path $env:USERPROFILE '.local/share/ttt2/characters'),
    [string[]]$Fighters,
    [string]$MsysRoot
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$previousPath = $env:Path
$previousLocation = Get-Location
try {
    Set-Location -LiteralPath $repoRoot
    if (!$MsysRoot) {
        $MsysRoot = Join-Path $env:LOCALAPPDATA 'ttt2-build/msys64'
        if (!(Test-Path -LiteralPath "$MsysRoot/usr/bin/bash.exe") -and (Test-Path -LiteralPath 'C:/msys64/usr/bin/bash.exe')) {
            $MsysRoot = 'C:/msys64'
        }
    }
    if (!(Test-Path -LiteralPath "$MsysRoot/usr/bin/bash.exe")) {
        throw 'Run tools/build_windows.ps1 first to install the Windows toolchain.'
    }
    if (!(Test-Path -LiteralPath "$GameDirectory/game/content/hdd/data000.ofs") -and
        !(Test-Path -LiteralPath "$GameDirectory/content/hdd/data000.ofs")) {
        throw 'GameDirectory must be the installed Tekken Tag 2 folder (run ttt2.exe --install first).'
    }
    $env:Path = "$MsysRoot/clang64/bin;$previousPath"
    $python = Join-Path $MsysRoot 'clang64/bin/python.exe'
    $needsPython = !(Test-Path -LiteralPath $python)
    if (!$needsPython) {
        & $python -c "import importlib.util, sys; sys.exit(0 if all(importlib.util.find_spec(m) is not None for m in ('numpy', 'PIL')) else 1)"
        $needsPython = $LASTEXITCODE -ne 0
    }
    if ($needsPython) {
        & "$MsysRoot/usr/bin/bash.exe" -lc 'pacman -Syu --noconfirm'
        & "$MsysRoot/usr/bin/bash.exe" -lc 'pacman -Syu --noconfirm'
        if ($LASTEXITCODE -ne 0) { throw 'Cannot finish the MSYS2 update.' }
        & "$MsysRoot/usr/bin/bash.exe" -lc 'pacman -S --needed --noconfirm mingw-w64-clang-x86_64-python mingw-w64-clang-x86_64-python-numpy mingw-w64-clang-x86_64-python-pillow'
        if ($LASTEXITCODE -ne 0) { throw 'Cannot install native Windows Python, numpy and Pillow.' }
    }
    $arguments = @('-u', 'tools/characters/import_character.py', '--game', $GameDirectory, '--out', $OutDirectory, '--progress')
    if ($Fighters) { $arguments += @($Fighters | ForEach-Object { $_ -split ',' }) } else { $arguments += '--all' }
    & $python @arguments
    if ($LASTEXITCODE -ne 0) { throw "Character import failed with exit code $LASTEXITCODE" }
} finally {
    $env:Path = $previousPath
    Set-Location -LiteralPath $previousLocation
}
