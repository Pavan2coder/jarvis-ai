@echo off
setlocal

cd /d "%~dp0"
title J.A.R.V.I.S

echo Starting J.A.R.V.I.S...
echo.

if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "%~dp0jarvis.py"
) else (
    py -3 "%~dp0jarvis.py"
    if errorlevel 9009 (
        python "%~dp0jarvis.py"
    )
)

set "EXITCODE=%ERRORLEVEL%"
echo.
echo J.A.R.V.I.S stopped with exit code %EXITCODE%.
pause
exit /b %EXITCODE%
