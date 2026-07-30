@echo off
setlocal
cd /d "%~dp0"
title Wayfinding Document Scanner - First-time setup

echo ============================================================
echo   Wayfinding Document Scanner - First-time setup
echo ============================================================
echo.
echo This window will create a private Python environment and install
echo the libraries required by the scanner.
echo.

if not exist "requirements.txt" goto :missing_files
if not exist "run_app.py" goto :missing_files
if not exist "src\document_scanner\app.py" goto :missing_files

set "PYTHON_CMD="
where py >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=py -3.12"

if not defined PYTHON_CMD (
    where python >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD goto :python_missing

%PYTHON_CMD% --version >nul 2>nul
if errorlevel 1 (
    set "PYTHON_CMD=py -3"
    %PYTHON_CMD% --version >nul 2>nul
    if errorlevel 1 goto :python_missing
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creating the application environment...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 goto :failed
) else (
    echo [1/3] The application environment already exists.
)

echo [2/3] Updating the installer...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :failed

echo [3/3] Installing the PDF scanner libraries...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failed

echo Verifying the application files...
".venv\Scripts\python.exe" -c "import sys; sys.path.insert(0, r'%CD%\src'); from document_scanner.config import load_keyword_groups; load_keyword_groups()"
if errorlevel 1 goto :failed

echo.
echo ============================================================
echo   Setup completed successfully.
echo ============================================================
echo.
echo Next time, double-click run_windows.bat to open the scanner.
echo.
pause
exit /b 0

:missing_files
echo.
echo The application files are incomplete.
echo.
echo Download and extract the ENTIRE repository ZIP. Do not copy only
echo setup_windows.bat or run_windows.bat to another folder.
echo.
pause
exit /b 1

:python_missing
echo.
echo Python 3.12 was not found.
echo.
echo 1. Open https://www.python.org/downloads/windows/
echo 2. Install Python 3.12.
echo 3. Check "Add python.exe to PATH" in the installer.
echo 4. Double-click setup_windows.bat again.
echo.
pause
exit /b 1

:failed
echo.
echo ============================================================
echo   Setup did not finish.
echo ============================================================
echo.
echo Check your internet connection and read the error shown above.
echo Then double-click setup_windows.bat to try again.
echo.
pause
exit /b 1
