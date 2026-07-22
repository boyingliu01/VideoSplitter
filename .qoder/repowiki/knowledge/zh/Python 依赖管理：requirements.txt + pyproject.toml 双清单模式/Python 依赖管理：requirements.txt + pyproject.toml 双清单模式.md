---
kind: dependency_management
name: Python 依赖管理：requirements.txt + pyproject.toml 双清单模式
slug: dependency_management
category: dependency_management
scope:
    - '**'
---

## 1. 使用的系统与工具
- **包管理器**：pip（通过 `pip install -r requirements.txt` 安装）
- **依赖声明文件**：根目录 `requirements.txt` 作为唯一权威来源；`pyproject.toml` 仅存放 pytest/coverage 配置，不声明运行时依赖
- **Node.js 元数据**：`package.json` 仅用于 OpenCode skill 描述与脚本入口，实际 Python 依赖仍由 `requirements.txt` 驱动
- **CI 集成**：GitHub Actions `.github/workflows/test.yml` 使用 `pip install -r requirements.txt` 安装依赖并运行测试
- **无锁文件**：仓库中不存在 `requirements.lock`、`poetry.lock`、`Pipfile.lock` 等锁定文件
- **无 vendoring**：未使用 `pipenv --venv`、`uv`、`pdm` 或 `vendor/` 目录策略
- **系统级依赖**：FFmpeg 需单独通过系统包管理器安装（`sudo apt-get install ffmpeg`），不在 pip 依赖范围内

## 2. 关键文件与位置
- `requirements.txt` — 全部 Python 运行时与开发依赖的单一声明点
- `pyproject.toml` — 仅包含 `[tool.pytest]` 与 `[tool.coverage]` 配置，不声明 project.dependencies
- `.github/workflows/test.yml` — CI 中安装依赖与执行测试的流程
- `ffmpeg-skill/AGENTS.md` — 说明该子模块为可复用库，被 `video_splitter/` 以源码形式引用（非 pip 包）
- `package.json` — 仅记录 Node 元信息，`scripts.install` 指向 `pip install -r requirements.txt`

## 3. 架构与约定
- **单源依赖**：所有 Python 依赖集中在 `requirements.txt`，按功能分区注释（Core / Optional / Development / video_splitter / Phase A GUI）
- **最低版本约束**：采用 `>=X.Y.Z` 宽松下限而非精确 pin，便于上游更新但可能引入兼容风险
- **分层依赖**：`faster-whisper`、`librosa`、`soundfile`、`openai` 归入 video_splitter 层；`PySide6`、`funasr`、`torch` 归入 GUI 阶段，体现分阶段能力演进
- **源码内嵌引用**：`ffmpeg-skill/` 与 `video_splitter/` 作为同仓库子包直接 import，不走 pip 分发，避免二次打包
- **外部二进制依赖显式化**：在 `requirements.txt` 顶部注释强调 FFmpeg 需系统安装，并在 CI 中显式 `apt-get install ffmpeg`

## 4. 开发者应遵循的规则
- **新增依赖**：统一添加到 `requirements.txt` 对应分区，并附带注释说明用途
- **版本策略**：优先使用 `>=` 指定最低兼容版本；如需严格锁定，应在本地虚拟环境生成 lock 文件但不提交到仓库
- **外部二进制**：若引入新的系统级依赖（如新的命令行工具），需在 `requirements.txt` 注释中说明，并同步更新 CI 安装步骤
- **不要修改 `package.json` 中的 Python 依赖**：它只是元数据，真实依赖来源是 `requirements.txt`
- **不要在代码中硬编码版本号**：所有版本控制集中在 `requirements.txt`，import 时只写包名
- **GUI 相关依赖**（PySide6、funasr、torch）体积较大，建议在文档中提示按需安装或使用可选依赖分组