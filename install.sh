#!/bin/bash
# Installation script for FFmpeg Video Processing Skill

set -e

echo "======================================"
echo "FFmpeg Video Processing Skill Setup"
echo "======================================"
echo ""

# Detect OS
OS="$(uname -s)"
case "$OS" in
    Linux*)     OS_TYPE="Linux";;
    Darwin*)    OS_TYPE="macOS";;
    MINGW*)     OS_TYPE="Windows";;
    MSYS_NT*)  OS_TYPE="Windows";;
    *)          OS_TYPE="Unknown";;
esac

echo "Detected OS: $OS_TYPE"
echo ""

# Check Python
echo "Checking Python installation..."
if command -v python3 &> /dev/null; then
    PYTHON="python3"
elif command -v python &> /dev/null; then
    PYTHON="python"
else
    echo "✗ Python not found. Please install Python 3.8+ first."
    exit 1
fi

PYTHON_VERSION=$($PYTHON --version | sed 's/Python //')
echo "✓ Found Python $PYTHON_VERSION"
echo ""

# Check Python version
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 8 ]); then
    echo "✗ Python 3.8+ is required (found $PYTHON_VERSION)"
    exit 1
fi

echo "✓ Python version compatible"
echo ""

# Check FFmpeg
echo "Checking FFmpeg installation..."
if command -v ffmpeg &> /dev/null; then
    FFMPEG_VERSION=$(ffmpeg -version 2>&1 | head -n 1 | cut -d' ' -f3)
    echo "✓ Found FFmpeg $FFMPEG_VERSION"
else
    echo "✗ FFmpeg not found in PATH"
    echo ""
    echo "Please install FFmpeg:"
    case "$OS_TYPE" in
        Linux)
            echo "  sudo apt install ffmpeg"
            echo "  or: sudo pacman -S ffmpeg"
            ;;
        macOS)
            echo "  brew install ffmpeg"
            ;;
        Windows)
            echo "  1. Download from https://ffmpeg.org/download.html"
            echo "  2. Extract to folder (e.g., C:\\ffmpeg)"
            echo "  3. Add C:\\ffmpeg\\bin to System PATH"
            ;;
    esac
    echo ""
    exit 1
fi

echo ""

# Install Python dependencies
echo "Installing Python dependencies..."
$PYTHON -m pip install --upgrade pip
$PYTHON -m pip install numpy tqdm

echo "✓ Dependencies installed"
echo ""

# Create symbolic link or copy to make command available
INSTALL_DIR="$HOME/.local/bin"
mkdir -p "$INSTALL_DIR"

echo "Installing ffmpeg-tool command..."
cp ffmpeg-skill/ffmpeg_tool.py "$INSTALL_DIR/ffmpeg-tool"
chmod +x "$INSTALL_DIR/ffmpeg-tool"

echo "✓ ffmpeg-tool installed to $INSTALL_DIR/ffmpeg-tool"
echo ""

# Update PATH if needed
if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
    echo "⚠ Adding $INSTALL_DIR to PATH..."
    if [ -n "$ZSH_VERSION" ]; then
        echo "export PATH=\"\$PATH:$INSTALL_DIR\"" >> ~/.zshrc
        echo "✓ Added to ~/.zshrc. Run: source ~/.zshrc"
    elif [ -n "$BASH_VERSION" ]; then
        echo "export PATH=\"\$PATH:$INSTALL_DIR\"" >> ~/.bashrc
        echo "✓ Added to ~/.bashrc. Run: source ~/.bashrc"
    fi
    export PATH="$PATH:$INSTALL_DIR"
else
    echo "✓ $INSTALL_DIR already in PATH"
fi

echo ""

# OpenCode setup
echo "======================================"
echo "OpenCode Skill Setup"
echo "======================================"
echo ""

SKILL_DIR=".opencode/skills/ffmpeg-video"
if [ -d "$SKILL_DIR" ]; then
    echo "✓ OpenCode skill already exists at $SKILL_DIR"
else
    echo "✗ OpenCode skill directory not found"
    echo "  The SKILL.md should be at: .opencode/skills/ffmpeg-video/SKILL.md"
fi

echo ""
echo "======================================"
echo "Installation Complete!"
echo "======================================"
echo ""
echo "To use FFmpeg Video Processing:"
echo ""
echo "1. Standalone CLI:"
echo "   ffmpeg-tool --help"
echo ""
echo "2. In Python:"
echo "   from ffmpeg_skill import FFmpegSkill"
echo "   ffmpeg = FFmpegSkill()"
echo ""
echo "3. In OpenCode:"
echo "   The skill will be automatically available via the 'skill' tool."
echo "   Just ask OpenCode to process videos using FFmpeg!"
echo ""
echo "4. Test installation:"
echo "   ffmpeg-tool info test.mp4  # (requires a test video file)"
echo ""
echo "Enjoy processing videos! 🎬"
