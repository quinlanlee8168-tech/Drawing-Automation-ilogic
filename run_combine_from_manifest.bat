@echo off
setlocal

set SCRIPT_DIR=%~dp0
set PY_CMD=

where python >nul 2>nul
if %errorlevel%==0 (
  set PY_CMD=python
) else (
  where py >nul 2>nul
  if %errorlevel%==0 (
    set PY_CMD=py -3
  )
)

if "%PY_CMD%"=="" (
  echo Python was not found in PATH.
  echo Install Python from https://www.python.org/downloads/windows/
  echo and make sure "Add python.exe to PATH" is enabled.
  echo.
  pause
  exit /b 1
)

%PY_CMD% "%SCRIPT_DIR%combine_from_manifest.py"

if errorlevel 1 (
  echo.
  echo Merge failed. Review the error above.
  echo If this is a missing package error, run:
  echo   %PY_CMD% -m pip install pypdf
  pause
  exit /b 1
)

echo.
echo Merge finished.
pause
