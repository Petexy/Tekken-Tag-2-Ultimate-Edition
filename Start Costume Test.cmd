@echo off
setlocal
cd /d "%~dp0"
set "costumePython=%LOCALAPPDATA%\TTT2Ultimate\launcher\local\windows-tools\python-runtime\python\pythonw.exe"
if exist "%costumePython%" (
  start "Paul Costume Test" "%costumePython%" "launcher\windows\main.py" --build-dir "build-windows-tools"
  exit /b 0
)
call "Start Ultimate Launcher.cmd"
