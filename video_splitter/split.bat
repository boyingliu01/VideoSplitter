@echo off
rem Launcher script for video_splitter CLI
rem Usage: split.bat <video_file> [options]
rem    or: split.bat --help

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "PYTHONPATH=%SCRIPT_DIR%;%PYTHONPATH%"

python -m video_splitter.cli %*