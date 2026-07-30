@echo off
setlocal
cd /d "%~dp0"
title Wayfinding Document Scanner

if not exist ".venv\Scripts\python.exe" goto :not_installed
if not exist "run_app.py" goto :missing_files
if not exist "src\document_scanner\app.py" goto :missing_files

".venv\Scripts\python.exe" "%~dp0run_app.py"
if errorlevel 1 goto :failed
exit /b 0

:not_installed
echo The scanner has not been set up yet.
echo.
echo Double-click setup_windows.bat first. After setup finishes,
echo double-click run_windows.bat again.
echo.
pause
exit /b 1

:missing_files
echo The application files are incomplete.
echo.
echo Download and extract the ENTIRE repository ZIP. The same folder must contain:
echo   run_windows.bat
echo   run_app.py
echo   requirements.txt
echo   src\document_scanner\app.py
echo.
echo Do not copy only the .bat files to another folder.
echo.
pause
exit /b 1

:failed
echo.
echo The scanner closed because of an error. The details are shown above.
echo.
echo If the error says a module is missing, double-click setup_windows.bat again.
echo.
pause
exit /b 1
