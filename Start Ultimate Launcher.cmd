@echo off
rem The launcher's name up to 0.8.0: shortcuts made then, and the test builds of then (their update of their files looks
rem for this one, and they get their Python ready with --check), go on with it. (By its name alone: "call" reads its
rem line twice, which would change a folder's name with a percent sign.)
setlocal
cd /d "%~dp0"
call ".\Start Golden Fist Launcher.cmd" %*
