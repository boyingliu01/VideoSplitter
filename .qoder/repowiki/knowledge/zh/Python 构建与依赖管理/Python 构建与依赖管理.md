---
kind: build_system
name: Python 构建与依赖管理
category: build_system
scope:
    - '**'
source_files:
    - pyproject.toml
    - requirements.txt
    - .github/workflows/test.yml
    - install.sh
    - install.bat
    - video_splitter/split.bat
    - video_splitter/vsplit.bat
---

本项目采用纯 Python 生态的轻量级构建体系，未引入 Makefile、Docker 或打包工具（如 PyInstaller），核心围绕 pyproject.toml + requirements.txt + GitHub Actions 构成。

1. 包与依赖声明
- pyproject.toml：定义项目元信息（name=video_splitter、version=0.1.0、requires-python=>=3.12），并内嵌 pytest 配置（testpaths、markers、addopts）、coverage 源与阈值（fail_under=50）。
- requirements.txt：集中声明运行时与可选依赖，按功能分层注释（Core / Optional / Development / video_splitter / Phase A GUI），其中 PySide6、funasr、torch 等重型依赖仅在 GUI 阶段使用。
- package.json：仅作为 OpenCode Skill 的元数据包装，scripts 指向 pip/pytest，无 Node 构建产物。

2. 测试与覆盖率
- 测试入口统一通过 pytest，支持 -m slow、-m integration 标记过滤；CI 中额外安装 pytest-cov、pytest-mock，输出 XML 上报 Codecov。
- coverage 统计范围限定为 video_splitter 与 gui，排除所有 tests/*、test_*.py 及 ffmpeg-skill/tests.py。

3. CI 流水线（GitHub Actions）
- .github/workflows/test.yml：在 ubuntu-latest 上以 Python 3.12 矩阵运行；先 apt install ffmpeg 再 pip install -r requirements.txt，最后执行 pytest tests/ video_splitter/tests/ --cov ...。
- 触发条件为 push/PR 到 master，失败不阻断 Codecov 上传。

4. 安装脚本与 CLI 启动器
- install.sh / install.bat：跨平台检测 Python >=3.8 与 FFmpeg，安装 numpy/tqdm，并将 ffmpeg_tool.py 拷贝至用户目录以便直接调用；同时提示 OpenCode skill 路径。
- video_splitter/split.bat / video_splitter/vsplit.bat：Windows 下设置 PYTHONPATH 后通过 python -m video_splitter.cli 启动 CLI，便于非开发者一键运行。

5. 版本与发布
- 版本号硬编码于 VERSION 文件与 pyproject.toml，未见自动化 release 流程或打包分发步骤。

开发者约定
- 新增依赖应同步更新 requirements.txt 与 pyproject.toml（若影响 testpaths/markers）。
- 测试用例遵循 test_*.py 命名，slow/integration 用例需加对应 marker 以便按需跳过。
- Windows 用户优先使用 split.bat / vsplit.bat 启动 CLI，避免手动设置 PYTHONPATH。