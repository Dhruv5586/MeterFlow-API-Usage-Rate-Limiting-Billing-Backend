@echo off
rem ===========================================================================
rem MeterFlow Windows Command-Line Shortcut
rem ===========================================================================
setlocal

rem Resolve Python from local virtual environment
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

rem Execute the MeterFlow CLI passing all terminal arguments
"%PYTHON_EXE%" "%~dp0cli.py" %*
