---
kind: configuration_system
name: 基于环境变量与 dataclass 的轻量配置系统
category: configuration_system
scope:
    - '**'
source_files:
    - video_splitter/config.py
    - video_splitter/cli.py
    - gui/controllers/split_controller.py
---

## 1. 采用的方案
- 使用 Python `dataclass` 定义单一配置对象 `SplitConfig`，集中管理 Whisper/LLM/切割策略/命名模板等运行时参数。
- 通过 `os.environ` 读取环境变量覆盖默认值，**不依赖任何外部配置文件（无 .yaml/.toml/.env 文件加载逻辑）**。
- CLI 入口在解析 `argparse` 后对 `SplitConfig` 实例进行二次覆盖，形成「默认值 → 环境变量 → CLI 参数」三层叠加。
- GUI 侧通过构造函数注入 `SplitConfig`，未传入时同样回退到 `SplitConfig.from_env()`。

## 2. 核心文件与包
- `video_splitter/config.py` — 唯一配置定义与加载入口，提供 `SplitConfig.from_env()`。
- `video_splitter/cli.py` — CLI 子命令统一调用 `from_env()` 并覆写部分字段。
- `gui/controllers/split_controller.py`、`gui/workers/*.py` — GUI 组件通过构造参数或 `from_env()` 消费配置。
- `architecture.yaml` — 仅用于 xp-gate 的模块导入约束，不属于运行时配置。
- `pyproject.toml` — 仅含 pytest/coverage 工具配置，与运行期应用配置无关。

## 3. 架构与约定
- **单例式数据类**：所有模块共享同一个 `SplitConfig` 结构体，避免分散的字典/常量散落各处。
- **分层覆盖顺序**：
  1) dataclass 字段默认值；
  2) 环境变量（`OPENAI_API_BASE`、`OPENAI_API_KEY`、`WHALECLOUD_API_KEY`、`VIDEO_SPLITTER_DEVICE`、`VIDEO_SPLITTER_RESUME`、`VIDEO_SPLITTER_ENGINE`）；
  3) CLI `--model` / `--cut-mode` / `--max-duration` / `--resume` 等参数。
- **引擎可插拔**：`transcription_engine` 字段 + `engine_config` 字典支持切换 ASR 后端（当前默认 `funasr`），由 `extractor.engines.create_engine` 根据该字段动态创建。
- **GUI 注入模式**：控制器/worker 接受可选 `config: Optional[SplitConfig]`，测试时可注入 mock，生产环境走 `from_env()`。
- **无持久化配置存储**：没有将配置写入磁盘的机制，每次启动都从环境变量重建。

## 4. 开发者应遵循的规则
- 新增配置项应在 `SplitConfig` dataclass 中声明默认值，并在 `from_env()` 中添加对应 `os.environ.get(...)` 覆盖逻辑。
- 敏感信息（API Key 等）一律通过环境变量注入，不要硬编码或放入代码仓库。
- 需要按环境区分的行为优先用环境变量控制，而非新增配置文件类型。
- 在 GUI 组件中如需自定义行为，通过构造器显式传入 `SplitConfig` 实例，便于单元测试替换。
- CLI 参数覆盖仅在 `cmd_*` 函数内对已构建的 `SplitConfig` 实例做赋值，不要在 `from_env()` 里处理 argparse 结果。