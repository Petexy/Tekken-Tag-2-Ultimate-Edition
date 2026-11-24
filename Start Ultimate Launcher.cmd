@echo off
setlocal
cd /d "%~dp0"
title Ultimate Launcher - First start
if not exist "local" mkdir "local"
rem (The "@step" lines: the native launcher shows them while it runs this hidden with --check.)
>>"local\windows-bootstrap.log" echo @step check Checking the launcher's tools
set "runtime=local\windows-tools\python-runtime"
set "archive=local\windows-downloads\python-runtime.tar.gz"
if exist "%runtime%\python\python.exe" goto ready
:getruntime
echo Getting Ultimate Launcher ready. This only downloads missing tools.
if not exist "local\windows-downloads" mkdir "local\windows-downloads"
if not exist "%runtime%" mkdir "%runtime%"
if exist "%archive%" goto verify
>>"local\windows-bootstrap.log" echo @step download Downloading Python for the launcher
if "%~1"=="--check" goto downloadquiet
curl.exe -L --fail --retry 3 --show-error -o "%archive%.part" "https://github.com/astral-sh/python-build-standalone/releases/download/20261026/cpython-3.13.18+20261026-x86_64-pc-windows-msvc-install_only.tar.gz"
goto downloaded
:downloadquiet
curl.exe -L --fail --retry 3 --show-error --progress-bar -o "%archive%.part" "https://github.com/astral-sh/python-build-standalone/releases/download/20261026/cpython-3.13.18+20261026-x86_64-pc-windows-msvc-install_only.tar.gz" 2>>"local\windows-bootstrap.log"
:downloaded
if errorlevel 1 goto failed
move /y "%archive%.part" "%archive%" >nul
:verify
>>"local\windows-bootstrap.log" echo @step verify Checking the download
certutil.exe -hashfile "%archive%" SHA256 > "local\windows-python-hash.txt"
if errorlevel 1 goto failed
findstr.exe /i /x "ebe90cc1dce2dd2d7afa1f0aa9b6c269c7c0174aeabdc6a801381602b7283424" "local\windows-python-hash.txt" >nul
if errorlevel 1 goto badhash
>>"local\windows-bootstrap.log" echo @step unpack Unpacking Python
tar.exe -xzf "%archive%" -C "%runtime%"
if errorlevel 1 goto failed
:ready
set "PYTHONNOUSERSITE=1"
set "PYTHONUTF8=1"
"%runtime%\python\python.exe" -c "import tkinter,ssl;print('Launcher runtime ready')" >> "local\windows-bootstrap.log" 2>&1
if errorlevel 1 (
 if defined repaired goto failed
 set "repaired=1"
 goto getruntime
)
>>"local\windows-bootstrap.log" echo @step ready The launcher's Python is ready
if "%~1"=="--check" exit /b 0
start "Ultimate Launcher" "%runtime%\python\pythonw.exe" "launcher\windows\main.py" --build-dir "build-windows-tools"
exit /b 0
:badhash
move /y "%archive%" "%archive%.bad" >nul
echo A damaged runtime download was kept aside. Start the launcher again to retry.
:failed
>>"local\windows-bootstrap.log" echo Setup could not finish: no Python for the launcher.
echo Setup could not finish. Check your internet connection and local\windows-bootstrap.log.
echo Extract the project ZIP into a writable folder before starting the launcher.
if "%~1"=="--check" exit /b 1
pause
exit /b 1
