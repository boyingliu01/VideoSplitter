@echo off
rem Video Splitter CLI Launcher
rem Usage: vsplit.bat <command> [args]
rem    or: vsplit.bat --help

set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%"
set "PYTHONPATH=%PROJECT_DIR%;%PYTHONPATH%"

python -m video_splitter.cli %*