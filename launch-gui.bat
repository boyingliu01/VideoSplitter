@echo off
rem VideoSplitter GUI Launcher
rem One-click start for acceptance testing
set "SCRIPT_DIR=%~dp0"
set "PYTHONPATH=%SCRIPT_DIR%;%PYTHONPATH%"
python -c "from gui.app import main; main()"
