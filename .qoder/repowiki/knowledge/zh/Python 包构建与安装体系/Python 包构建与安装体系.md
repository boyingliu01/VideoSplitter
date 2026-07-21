---
kind: build_system
name: Python 包构建与安装体系
slug: build_system
category: build_system
scope:
    - '**'
---

本项目采用轻量级 Python 包管理方案，未引入 Makefile、Dockerfile、tox、nox 等重型构建系统，而是围绕 pyproject.toml + requirements.txt + 平台安装脚本组织构建流程。

1. 依赖声明与包元数据
- pyproject.toml：定义项目名 video_splitter、版本 0.1.0、最低 Python 3.12；内嵌 pytest 配置（测试路径、标记 slow/integration）、coverage 源与阈值（50%）。
- requirements.txt：集中声明运行时与开发依赖，按功能分层（FFmpeg Skill 基础、video_splitter 核心、GUI 阶段 A），并明确标注 FFmpeg 需作为系统依赖单独安装。

2. 跨平台安装脚本
- install.sh（Linux/macOS/WSL）：检测 Python >=3.8 与 FFmpeg -> 升级 pip -> 安装 numpy/tqdm -> 将 ffmpeg-skill/ffmpeg_tool.py 复制到 $HOME/.local/bin/ffmpeg-tool 并追加 PATH（自动写入 .bashrc / .zshrc）。
- install.bat（Windows）：等价流程，将脚本拷贝到 %USERPROFILE%\AppData\Local\ffmpeg-skill\ffmpeg-tool.py，并提供生成 ffmpeg-tool.bat 的提示。
- 两者均要求 FFmpeg 已加入系统 PATH，否则直接退出。

3. CLI 启动器
- video_splitter/split.bat / vsplit.bat：Windows 下通过设置 PYTHONPATH 再调用 python -m video_splitter.cli，使非开发者也能以批处理方式运行分割命令。

4. CI 流水线（GitHub Actions）
- .github/workflows/test.yml：在 ubuntu-latest 上以 Python 3.12 矩阵运行；步骤包括 checkout -> setup-python -> apt install ffmpeg -> pip install -r requirements.txt -> 执行 pytest tests/ video_splitter/tests/ --cov -> 上传 coverage.xml 至 Codecov。
- 触发条件为 push/PR 到 master 分支。

5. 评测与基准脚本
- ffmpeg-video-workspace/grade_all.py、fix_grading.py、convert_webm.py：用于端到端评测 ffmpeg skill 的转换/裁剪/信息提取能力，输出 grading.json、timing.json 与 benchmark.md。
- _run_cert*.py：OpenCode 技能认证运行脚本，批量执行评测并汇总结果。

6. 设计决策与约束
- 无虚拟环境/打包分发约定：未使用 venv、poetry、hatch、setuptools，仅靠 requirements.txt 与安装脚本完成环境准备。
- 外部二进制依赖（FFmpeg）不随包分发，由安装脚本引导用户自行安装。
- 测试覆盖范围限定于 video_splitter 与 gui 两个子包，排除所有 tests/* 与 ffmpeg-skill/tests.py。
- 版本号硬编码在 pyproject.toml，未见自动化 bump 或发布流水线。