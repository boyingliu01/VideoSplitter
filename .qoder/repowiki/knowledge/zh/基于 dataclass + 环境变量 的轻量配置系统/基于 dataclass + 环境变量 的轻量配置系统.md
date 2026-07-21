---
kind: configuration_system
name: 基于 dataclass + 环境变量 的轻量配置系统
slug: configuration_system
category: configuration_system
scope:
    - '**'
---

## 1. 使用的系统与工具
- 核心：Python `dataclasses` 定义单一配置对象 `SplitConfig`，所有运行时参数集中管理。
- 加载方式：仅通过 `os.environ` 读取环境变量，无 `.env` 文件解析、无 YAML/JSON/TOML 配置文件加载逻辑。
- 项目级元配置：`pyproject.toml` 中存放 pytest、coverage 等开发期配置；`architecture.yaml` 用于 xp-gate 导入边界约束（非运行时配置）。
- 密钥与环境变量约定：`.gitignore` 显式排除 `.env`、`.env.local`，表明期望开发者自行维护本地环境文件，但代码层未实现自动加载。

## 2. 关键文件与包
- `video_splitter/config.py` — `SplitConfig` dataclass 定义及 `from_env()` 类方法，是唯一的运行时配置入口。
- `video_splitter/cli.py` — CLI 子命令统一调用 `SplitConfig.from_env()` 构建配置，再覆写部分命令行参数。
- `gui/workers/transcribe_worker.py` — GUI 侧默认构造 `SplitConfig()`（不读 env），由上层注入或保持默认值。
- `pyproject.toml` — pytest / coverage 等开发期配置。
- `architecture.yaml` — 模块导入边界约束，非运行时配置。
- `.gitignore` — 声明 `.env`、`.env.local` 为忽略文件。

## 3. 架构与设计约定
- **单例数据类**：`SplitConfig` 以 dataclass 形式暴露全部可调参数（Whisper 模型大小、设备、计算精度、章节时长上下界、LLM API 地址/Key/模型名/token 预算/重试次数、切割模式、关键帧容差、语言、命名模板、断点续跑开关、ASR 引擎名及引擎专属覆盖字典 `engine_config`）。
- **环境变量覆盖优先级**：
  - `OPENAI_API_BASE` → `llm_api_base`
  - `OPENAI_API_KEY` / `WHALECLOUD_API_KEY` → `llm_api_key`（后者优先）
  - `VIDEO_SPLITTER_DEVICE` → `device`
  - `VIDEO_SPLITTER_RESUME=1|true|yes` → `resume=True`
  - `VIDEO_SPLITTER_ENGINE` → `transcription_engine`
- **CLI 覆写顺序**：`from_env()` → 命令行参数覆写 → 传入 Pipeline/Engine。即：默认值 < 环境变量 < CLI 参数。
- **GUI 路径差异**：GUI 侧直接 `SplitConfig()` 使用内置默认值，不经过 `from_env()`，因此 GUI 运行不受环境变量影响（除非显式传参）。
- **测试策略**：单元测试普遍直接 `SplitConfig(...)` 构造并只覆盖必要字段，避免依赖真实环境变量。

## 4. 开发者应遵循的规则
1. **新增配置项**：在 `SplitConfig` dataclass 中添加字段并提供合理默认值；如需支持环境变量覆盖，在 `from_env()` 中增加对应 `os.environ.get` 分支。
2. **敏感信息**：API Key 等敏感值必须通过环境变量注入，不要硬编码到源码或提交到仓库（`.gitignore` 已约定）。
3. **CLI 与 GUI 行为一致性**：若某配置项对 GUI 也重要，应在 GUI 构造处显式传入或通过 `from_env()` 加载，避免 GUI 与 CLI 行为不一致。
4. **测试时避免真实 env**：用例中直接 `SplitConfig(field=value)` 构造，不要依赖外部环境变量，保证可重复性。
5. **引擎扩展**：新增 ASR 引擎时，在 `transcription_engine` 枚举范围内添加新值，并通过 `engine_config` dict 传递引擎专属参数，不在 `SplitConfig` 上散开字段。