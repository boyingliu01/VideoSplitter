---
kind: dependency_management
name: Python 依赖管理：requirements.txt + pyproject.toml 双轨制，无锁定文件与私有源
category: dependency_management
scope:
    - '**'
source_files:
    - requirements.txt
    - pyproject.toml
    - package.json
    - .opencode/package.json
    - install.sh
    - install.bat
    - .github/workflows/test.yml
---

## 1. 使用的系统与工具链
- **包清单**：根目录 `requirements.txt` 声明全部 Python 依赖（含可选/开发依赖），`pyproject.toml` 仅承载构建/测试/覆盖率配置，未定义 `[project.dependencies]`。
- **包管理器**：纯 pip 生态，未见 Poetry、Pipenv、uv、pip-tools 等现代锁文件方案；`.opencode/package.json` 使用 npm 安装 OpenCode 插件，与 Python 依赖解耦。
- **外部二进制**：FFmpeg 作为系统级依赖，由 `install.sh` / `install.bat` 检测 PATH，不通过 pip 安装。
- **CI 安装**：`.github/workflows/test.yml` 直接执行 `pip install -r requirements.txt`，无缓存或虚拟环境隔离脚本。

## 2. 关键文件与位置
- `requirements.txt` — 唯一 Python 依赖来源，按功能分组（core / optional / dev / video_splitter / GUI）。
- `pyproject.toml` — pytest、coverage、ruff 配置，`requires-python = ">=3.12"`，但 `requirements.txt` 注释写 `Python 3.8+`，存在版本不一致。
- `package.json` — 顶层元数据，`scripts.install` 调用 `pip install -r requirements.txt`，`dependencies.python` 仅做文档性约束。
- `.opencode/package.json` — 固定 `@opencode-ai/plugin: 1.15.13`，有对应 `package-lock.json`，与 Python 无关。
- `install.sh` / `install.bat` — 安装脚本只装 `numpy`、`tqdm`，并未安装 `requirements.txt` 中的其余依赖。
- `.github/workflows/test.yml` — CI 中 `pip install -r requirements.txt` 作为测试前置步骤。

## 3. 架构与约定
- **单清单策略**：所有 Python 第三方库集中在 `requirements.txt`，子包（ffmpeg-skill、video_splitter、gui）不再维护各自清单。
- **无锁定文件**：仓库未提交 `requirements.lock` / `poetry.lock` / `Pipfile.lock`，每次安装均从 PyPI 解析最新兼容版本，可重现性弱。
- **无私有源/VCS 依赖**：未发现 `--index-url`、`pip.conf`、`setup.cfg` 的 `find_links` 或 VCS URL，所有包均来自默认 PyPI。
- **可选依赖未拆分**：GUI（PySide6）、ASR（funasr/torch/openai）与核心逻辑混在同一清单，没有 `[project.optional-dependencies]` 或分文件（如 `requirements-dev.txt`）进行按需安装。
- **OpenCode 技能**：以 `.opencode/skills/...` 目录 + `SKILL.md` 形式注册，其 Node 插件通过 npm 独立管理，与 Python 依赖互不影响。

## 4. 开发者应遵循的规则
1. **新增依赖只改 `requirements.txt`**，并在相应分区添加注释说明用途；不要在子包内新建清单。
2. **保持 Python 版本一致**：同步更新 `pyproject.toml` 的 `requires-python` 与 `requirements.txt` 头部注释，避免冲突。
3. **引入锁定文件**：建议采用 `pip-tools`（`requirements.in` → `requirements.txt` + `requirements-dev.txt`）或 `uv`/Poetry，将 `*.lock` 纳入版本控制以保证可重现构建。
4. **区分运行/开发/可选依赖**：将 PySide6、torch、openai 等重型可选依赖拆到 `requirements-gui.txt` / `requirements-asr.txt`，并通过 `pip install -r requirements.txt[gui]` 方式安装。
5. **CI 复用本地安装流程**：在 GitHub Actions 中增加 pip cache 与可选依赖开关，减少构建时间并覆盖更多场景。
6. **外部二进制 FFmpeg 必须预装**：任何新环境（容器、CI、用户机器）需确保 `ffmpeg` 在 PATH 中，安装脚本仅检查不安装。