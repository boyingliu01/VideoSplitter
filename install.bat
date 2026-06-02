@echo off
REM Installation script for FFmpeg Video Processing Skill for Windows

echo ======================================
echo FFmpeg Video Processing Skill Setup
echo ======================================
echo.

REM Check Python
echo Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ✗ Python not found. Please install Python 3.8+ first.
    echo Download from: https://www.python.org/downloads/
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo ✓ Found Python %PYTHON_VERSION%
echo.

REM Check FFmpeg
echo Checking FFmpeg installation...
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo ✗ FFmpeg not found in PATH
    echo.
    echo Please install FFmpeg:
    echo   1. Download from https://ffmpeg.org/download.html
    echo   2. Extract to folder (e.g., C:\ffmpeg)
    echo   3. Add C:\ffmpeg\bin to System PATH
    echo   4. Restart this terminal
    echo.
    exit /b 1
)

for /f "tokens=3" %%i in ('ffmpeg -version 2^>^&1') do set FFMPEG_VERSION=%%i
echo ✓ Found FFmpeg %FFMPEG_VERSION%
echo.

REM Install Python dependencies
echo Installing Python dependencies...
python -m pip install --upgrade pip
python -m pip install numpy tqdm

echo ✓ Dependencies installed
echo.

REM Create installation directory
set INSTALL_DIR=%USERPROFILE%\AppData\Local\ffmpeg-skill
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

echo Installing ffmpeg-tool command...
copy /Y ffmpeg-skill\ffmpeg_tool.py "%INSTALL_DIR%\ffmpeg-tool.py"

echo.
echo ======================================
echo Installation Complete!
echo ======================================
echo.
echo To use FFmpeg Video Processing:
echo.
echo 1. Standalone CLI:
echo    python "%INSTALL_DIR%\ffmpeg-tool.py" --help
echo.
echo 2. In Python:
echo    from ffmpeg_skill import FFmpegSkill
echo    ffmpeg = FFmpegSkill()
echo.
echo 3. In OpenCode:
echo    The skill is available at .opencode\skills\ffmpeg-video\SKILL.md
echo    Just ask OpenCode to process videos using FFmpeg!
echo.
echo 4. Create batch file for easier access:
echo    @echo off > "%USERPROFILE%\AppData\Local\ffmpeg-tool.bat"
echo    python "%INSTALL_DIR%\ffmpeg-tool.py" %%* >> "%USERPROFILE%\AppData\Local\ffmpeg-tool.bat"
echo    ✓ Created batch file at %USERPROFILE%\AppData\Local\ffmpeg-tool.bat
echo    Now you can run: ffmpeg-tool --help
echo.
echo Enjoy processing videos!
