---
kind: build_system
name: Python 包构建与测试流水线
category: build_system
scope:
    - '**'
source_files:
    - pyproject.toml
    - requirements.txt
    - .github/workflows/test.yml
    - install.sh
    - install.bat
    - launch-gui.bat
    - video_splitter/split.bat
    - video_splitter/vsplit.bat
---

本项目采用轻量级 Python 工程结构，未使用 Makefile、Dockerfile 或复杂打包工具，而是以 pyproject.toml + requirements.txt + GitHub Actions 为核心构建体系。

## 1. 依赖与版本管理
- 运行时依赖：requirements.txt 声明 ffmpeg-skill、video_splitter、GUI（PySide6）、ASR（funasr/torch）等全部依赖；注释标注 FFmpeg 为系统外部依赖，需单独安装。
- 包元数据：pyproject.toml 定义项目名 video_splitter、最低 Python 3.12，并集中配置 pytest、coverage、ruff 行为。
- 无虚拟环境/锁定文件：仓库未包含 poetry.lock / pipenv.lock / uv.lock，依赖解析由 pip 直接完成。

## 2. 测试与覆盖率
- pytest 配置：pyproject.toml 中 tool.pytest.ini_options 指定双 testpath（tests/ 与 video_splitter/tests/），支持 slow、integration 标记，addopts 启用严格模式。
- 覆盖率：tool.coverage.run.source 覆盖 video_splitter、gui，fail_under = 80 强制质量门槛。
- CI 流水线：.github/workflows/test.yml 在 Ubuntu + Python 3.12 矩阵上运行，步骤包括：checkout → setup-python → apt install ffmpeg → pip install -r requirements.txt → pytest --cov → 上传 Codecov。

## 3. 安装与分发脚本
- 跨平台安装器：install.sh（Linux/macOS）与 install.bat（Windows）检测 Python >= 3.8、FFmpeg 是否可用，安装 numpy/tqdm，并将 ffmpeg_tool.py 拷贝到用户目录以便通过 ffmpeg-tool 命令调用。
- CLI 启动器：launch-gui.bat、video_splitter/split.bat、video_splitter/vsplit.bat 设置 PYTHONPATH 后以 python -m video_splitter.cli 方式启动，便于 Windows 双击运行。
- 无正式发布流程：未发现 setup.py、MANIFEST.in、build.sh、release.sh 或任何 PyPI 发布动作。

## 4. 架构约定
- 多入口共存：同一 CLI 模块通过多个 .bat 包装暴露不同命名（split.bat、vsplit.bat、ffmpeg-tool），体现技能包与应用双重身份。
- 外部依赖显式化：FFmpeg 作为系统二进制不在 pip 范围内，所有安装脚本均先校验其存在再继续。
- 测试与源码分离：顶层 tests/ 与子包内 video_splitter/tests/ 并行组织，分别覆盖 GUI 集成与核心逻辑。

## 5. 开发者应遵循的规则
- 新增依赖时同步更新 requirements.txt 与 CI 的 pip install 步骤。
- 新增测试用例需遵守 pyproject.toml 中的命名约定（test_*.py、Test* 类）。
- 若引入新的可执行入口，应在根目录提供对应 .bat 启动器并设置 PYTHONPATH。
- 覆盖率阈值 80% 由 CI 强制执行，提交前建议本地运行 pytest --cov 自检。