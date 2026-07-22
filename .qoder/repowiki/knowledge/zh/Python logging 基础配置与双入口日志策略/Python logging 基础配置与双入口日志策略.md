---
kind: logging_system
name: Python logging 基础配置与双入口日志策略
category: logging_system
scope:
    - '**'
source_files:
    - video_splitter/cli.py
    - gui/app.py
    - video_splitter/pipeline.py
    - video_splitter/extractor/engines.py
    - gui/workers/streaming_transcribe_worker.py
---

本项目使用 Python 标准库 `logging`，未引入第三方日志框架（如 loguru、structlog）。日志系统由两个独立入口分别初始化，遵循“每个进程只调用一次 basicConfig”的原则：

- CLI 入口 `video_splitter/cli.py`：在模块顶层调用 `logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")`，并获取根命名空间 logger `logger = logging.getLogger("video_splitter")`。
- GUI 入口 `gui/app.py`：在 `main()` 中调用 `logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")`，并通过 `logger = logging.getLogger(__name__)` 在各模块内获取子 logger。

**关键约定**
- 所有业务模块统一采用 `import logging; logger = logging.getLogger(__name__)` 模式，按包层级组织 logger 名称（如 `video_splitter.pipeline`、`gui.workers.streaming_transcribe_worker`）。
- 日志级别仅使用 `INFO / WARNING / ERROR`，未见 `DEBUG` 或 `CRITICAL` 的使用；CLI 与 GUI 默认级别均为 `INFO`。
- 输出格式为纯文本，包含时间戳、级别、可选的 logger name 和消息体，无结构化字段（JSON），也未配置 FileHandler/StreamHandler，默认输出到 stderr/stdout。
- 没有集中式日志配置模块，各入口各自负责 basicConfig，因此 CLI 与 GUI 的日志格式存在细微差异（GUI 多输出 `%(name)s:` 前缀）。

**开发者应遵循的规则**
1. 新增模块直接 `import logging; logger = logging.getLogger(__name__)`，不要再次调用 `basicConfig`。
2. 使用 `logger.info/warning/error` 记录业务事件，避免 `print` 混用（CLI 内部仍有少量 `print` 用于命令输出，但核心流程已迁移至 logger）。
3. 如需持久化日志文件，应在对应入口（cli.py 或 gui/app.py 的 main）添加 FileHandler，而非在业务模块内自行创建 Handler。