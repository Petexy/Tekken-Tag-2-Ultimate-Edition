[CmdletBinding()]
param(
    [string]$MsysRoot,
    [string]$BuildDirectory = 'build-windows',
    [string]$Game,
    [string]$GeneratedDirectory = 'generated/ttt2-windows',
    [ValidateRange(1, 256)][int]$Jobs = [Math]::Min([Environment]::ProcessorCount, 8),
    [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$originalPath = $env:Path
$originalLocation = Get-Location

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Executable failed with exit code $LASTEXITCODE" }
}

function Resolve-ProjectPath {
    param([string]$Path)
    if ([IO.Path]::IsPathRooted($Path)) { return [IO.Path]::GetFullPath($Path) }
    return [IO.Path]::GetFullPath((Join-Path $repoRoot $Path))
}

function Copy-NativeDependencies {
    param([string]$Directory, [string]$Toolchain)
    $queue = New-Object 'System.Collections.Generic.Queue[string]'
    $seen = @{}
    Get-ChildItem -LiteralPath $Directory -Filter '*.exe' | ForEach-Object { $queue.Enqueue($_.FullName) }
    while ($queue.Count -gt 0) {
        $binary = $queue.Dequeue()
        foreach ($line in (& "$Toolchain/bin/llvm-objdump.exe" -p $binary)) {
            if ($line -match 'DLL Name:\s+(\S+)') {
                $dll = $Matches[1]
                if ($dll -like 'msys-*.dll') { throw "Unexpected MSYS runtime dependency: $dll" }
                if ($seen.ContainsKey($dll)) { continue }
                $seen[$dll] = $true
                $source = Join-Path "$Toolchain/bin" $dll
                if (Test-Path -LiteralPath $source) {
                    $destination = Join-Path $Directory $dll
                    Copy-Item -LiteralPath $source -Destination $destination -Force
                    $queue.Enqueue($destination)
                } elseif (!(Test-Path -LiteralPath (Join-Path "$env:WINDIR/System32" $dll)) -and $dll -notlike 'api-ms-*' -and $dll -notlike 'ext-ms-*') {
                    throw "Cannot locate runtime DLL $dll required by $binary"
                }
            }
        }
        if ($LASTEXITCODE -ne 0) { throw "Cannot inspect dependencies of $binary" }
    }
}

try {
    Set-Location -LiteralPath $repoRoot
    if (!$MsysRoot) {
        $localMsys = Join-Path $env:LOCALAPPDATA 'ttt2-build/msys64'
        if (Test-Path -LiteralPath "$localMsys/usr/bin/bash.exe") { $MsysRoot = $localMsys }
        elseif (Test-Path -LiteralPath 'C:/msys64/usr/bin/bash.exe') { $MsysRoot = 'C:/msys64' }
        else { $MsysRoot = $localMsys }
    }
    $MsysRoot = [IO.Path]::GetFullPath($MsysRoot)
    $bash = Join-Path $MsysRoot 'usr/bin/bash.exe'
    if (!(Test-Path -LiteralPath $bash)) {
        Write-Host 'Downloading an isolated MSYS2 toolchain (no administrator access required)...'
        $release = Invoke-RestMethod -Uri 'https://api.github.com/repos/msys2/msys2-installer/releases/latest'
        $asset = $release.assets | Where-Object { $_.name -match '^msys2-base-x86_64-.*\.sfx\.exe$' } | Select-Object -First 1
        if (!$asset -or $asset.digest -notmatch '^sha256:([a-fA-F0-9]{64})$') { throw 'No MSYS2 installer with a SHA256 digest was found' }
        $expected = $Matches[1]
        $downloadFolder = Join-Path $repoRoot 'build-tools'
        New-Item -ItemType Directory -Force -Path $downloadFolder | Out-Null
        $installer = Join-Path $downloadFolder 'msys2-base.sfx.exe'
        Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $installer -UseBasicParsing
        if ((Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash -ne $expected) { throw 'MSYS2 installer checksum mismatch' }
        $installParent = Split-Path -Parent $MsysRoot
        if ((Split-Path -Leaf $MsysRoot) -ne 'msys64') { throw 'A new MSYS2 installation must use a directory named msys64' }
        New-Item -ItemType Directory -Force -Path $installParent | Out-Null
        Invoke-Checked $installer @('-y', "-o$installParent")
        Invoke-Checked $bash @('-lc', 'true')
    }
    $toolchain = Join-Path $MsysRoot 'clang64'
    $env:Path = "$toolchain/bin;$MsysRoot/usr/bin;$originalPath"
    $required = @('clang++.exe', 'cmake.exe', 'ninja.exe', 'python.exe', 'SDL3.dll', 'libshaderc_shared.dll', 'libcrypto-3-x64.dll')
    $missing = @($required | Where-Object { !(Test-Path -LiteralPath "$toolchain/bin/$_") })
    if ($missing.Count -gt 0 -or !(Test-Path -LiteralPath "$MsysRoot/usr/bin/python3.exe")) {
        Write-Host 'Installing Clang, Ninja and native Windows libraries...'
        & $bash -lc 'pacman -Syu --noconfirm'
        # A core update can close its shell; a second invocation finishes the upgrade.
        Invoke-Checked $bash @('-lc', 'pacman -Syu --noconfirm')
        $packages = 'clang cmake ninja python python-numpy python-pillow sdl3 shaderc vulkan-loader vulkan-headers openssl zstd zlib'.Split(' ') |
            ForEach-Object { 'mingw-w64-clang-x86_64-' + $_ }
        Invoke-Checked $bash @('-lc', ('pacman -S --needed --noconfirm python git ' + ($packages -join ' ')))
    }
    Invoke-Checked $bash @('-c', '/usr/bin/python3 tools/setup_deps.py')
    $cmake = Join-Path $toolchain 'bin/cmake.exe'
    $buildRoot = Resolve-ProjectPath $BuildDirectory
    $testSetting = if ($SkipTests) { 'OFF' } else { 'ON' }
    $configure = @('-S', $repoRoot, '-B', $buildRoot, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
                   "-DCMAKE_C_COMPILER=$toolchain/bin/clang.exe", "-DCMAKE_CXX_COMPILER=$toolchain/bin/clang++.exe",
                   '-DTTT2_BUILD_LAUNCHER=OFF', "-DBUILD_TESTING=$testSetting",
                   "-DPython3_EXECUTABLE=$toolchain/bin/python.exe")
    Invoke-Checked $cmake $configure
    Invoke-Checked $cmake @('--build', $buildRoot, '--parallel', "$Jobs")
    if ($Game) {
        $gamePath = (Resolve-Path -LiteralPath $Game).Path
        if (Test-Path -LiteralPath $gamePath -PathType Leaf) {
            $analysis = Join-Path $repoRoot ('local/wua-windows/' + [guid]::NewGuid().ToString('N'))
            Invoke-Checked "$buildRoot/wua_extract.exe" @('extract-analysis', $gamePath, $analysis)
        } else { $analysis = $gamePath }
        $expectedRpx = 'fc0270465d384386f67804e48716e30bfbe85a5a1004e3a6bfe3ac75f9de5019'
        $rpx = Get-ChildItem -LiteralPath $analysis -Recurse -Filter 'Tekken.rpx' -File | Where-Object {
            (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash -eq $expectedRpx
        } | Select-Object -First 1
        if (!$rpx) { throw 'The European Tekken.rpx with update v16 was not found (SHA256 mismatch)' }
        $generatedRoot = Resolve-ProjectPath $GeneratedDirectory
        Invoke-Checked "$buildRoot/recomp/cafe-recomp.exe" @($rpx.FullName, $generatedRoot)
        Invoke-Checked $cmake @('-S', $repoRoot, '-B', $buildRoot, "-DTTT2_GENERATED_DIR=$generatedRoot",
                               "-DTTT2_INPUT_TEST_RPX=$($rpx.FullName)")
        Invoke-Checked $cmake @('--build', $buildRoot, '--parallel', "$Jobs")
    }
    if (!$SkipTests) {
        Invoke-Checked "$toolchain/bin/ctest.exe" @('--test-dir', $buildRoot, '--output-on-failure', '--timeout', '60')
    }

    $bin = Join-Path $buildRoot 'bin'
    New-Item -ItemType Directory -Force -Path $bin | Out-Null
    foreach ($relative in @('wua_extract.exe', 'recomp/cafe-recomp.exe', 'recomp/cafe-census.exe', 'recomp/cafe-semgen.exe', 'runtime/cafe-shader.exe', 'ttt2.exe')) {
        $source = Join-Path $buildRoot $relative
        if (Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination $bin -Force }
    }
    Copy-NativeDependencies $bin $toolchain
    @'
Native Windows x86-64 build of the Tekken Tag 2 recompiler tools.

wua_extract.exe   - list/extract your WUA archive
cafe-recomp.exe   - generate C++ from the supported European v16 Tekken.rpx
cafe-census.exe   - inspect an RPX
cafe-semgen.exe   - generate instruction test cases from an RPX
cafe-shader.exe   - inspect and translate Latte shaders

The tools contain no game assets. If ttt2.exe is present, it was generated
from the owner's European v16 game files and contains game-derived code.
Do not share that executable or the generated sources. The GTK launcher
is Linux-only; tools/import_characters_windows.ps1 imports fighters on Windows.
Windows gameplay and leverless movement have been confirmed by a player.
Automated host/runtime tests use synthetic data; the optional combat input
test also uses the owner's matching RPX and generated code locally.

Keep the included DLLs beside the executables.
'@ | Set-Content -LiteralPath (Join-Path $bin 'README-WINDOWS.txt') -Encoding utf8
    if ($Game -and (Test-Path -LiteralPath "$bin/ttt2.exe")) {
        $launch = @('@echo off', 'setlocal DisableDelayedExpansion', 'chcp 65001 >nul',
                    ('"%~dp0ttt2.exe" "' + $gamePath.Replace('%', '%%') + '"'),
                    'if errorlevel 1 pause', 'endlocal')
        [IO.File]::WriteAllLines((Join-Path $bin 'Play.cmd'), $launch, (New-Object System.Text.UTF8Encoding($false)))
    }
    Write-Host "Native Windows tools and their DLLs: $bin"
    if (!(Test-Path -LiteralPath "$bin/ttt2.exe")) {
        Write-Host 'The game executable needs your EU v16 game files. Re-run with -Game PATH_TO_WUA_OR_GAME_FOLDER.'
    }
} finally {
    $env:Path = $originalPath
    Set-Location -LiteralPath $originalLocation
}
