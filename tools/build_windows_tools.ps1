param(
    [Parameter(Mandatory=$true)][string]$ToolsRoot
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$compiler = Join-Path $ToolsRoot 'llvm-mingw-20261020-ucrt-x86_64/bin'
$cmake = Join-Path $ToolsRoot 'python/cmake/data/bin/cmake.exe'
$ninja = Join-Path $ToolsRoot 'python/bin/ninja.exe'
$env:PATH = "$compiler;" + $env:PATH
& $cmake -S $root -B "$root/build-windows-tools" -G Ninja -DTTT2_TOOLS_ONLY=ON -DTTT2_WINDOWS_RUNTIME=OFF -DCMAKE_BUILD_TYPE=Release "-DCMAKE_MAKE_PROGRAM=$ninja" "-DCMAKE_C_COMPILER=$compiler/clang.exe" "-DCMAKE_CXX_COMPILER=$compiler/clang++.exe"
if ($LASTEXITCODE -ne 0) { throw 'Configure failed' }
& $cmake --build "$root/build-windows-tools" --target cafe-recomp cafe-census cafe-semgen wua_extract windows_memory_smoke windows_host_smoke windows_vfs_smoke windows_runtime_core windows_installer_driver windows_checks ttt2-play ttt2-launcher -j 8
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
# The launcher is build-windows-tools/launcher/ttt2-launcher.exe: the one of releases up to 0.8.0 that an older Set Up
# Game left at the folder's top would still open the old way, so it goes.
Remove-Item -LiteralPath "$root/build-windows-tools/ttt2-launcher.exe" -Force -ErrorAction SilentlyContinue
& (Join-Path (Split-Path $cmake) 'ctest.exe') --test-dir "$root/build-windows-tools" --output-on-failure -LE launcher
if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
