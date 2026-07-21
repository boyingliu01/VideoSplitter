---
kind: logging_system
name: 基于 Python 标准库 logging 的日志系统
category: logging_system
scope:
    - '**'
source_files:
    - video_splitter/cli.py
    - video_splitter/pipeline.py
    - gui/controllers/split_controller.py
    - video_splitter/review.py
---

## 概述
本项目使用 Python 标准库 `logging` 作为统一的日志框架，未引入第三方日志库（如 loguru、structlog）。所有模块通过 `logging.getLogger(__name__)` 获取独立 logger 实例，由 CLI 入口统一配置根 handler。

## 核心机制
- **全局配置**：在 `video_splitter/cli.py` 中调用 `logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")`，设置默认级别为 INFO，输出格式包含时间戳、级别和消息。
- **模块级 logger**：各模块通过 `logger = logging.getLogger(__name__)` 获取命名 logger，形成层次化结构（如 `video_splitter.pipeline`、`gui.controllers.split_controller`）。
- **输出目标**：仅使用 `basicConfig` 默认的 StreamHandler 输出到 stderr，未注册 FileHandler 或自定义 sink，日志直接打印到控制台。
- **日志级别**：代码中使用 `logger.info()` 记录流程进度（如步骤完成、文件保存），`logger.error()` 记录异常与失败，`logger.warning()` 用于数据损坏等警告场景，未见 DEBUG/CRITICAL 使用。

## 关键文件
- `video_splitter/cli.py` — 唯一进行 `basicConfig` 的地方，定义全局日志格式与级别
- `video_splitter/pipeline.py` — 主流水线，大量 info/error 日志记录阶段状态
- `gui/controllers/split_controller.py` — GUI 控制器，通过同名 logger 记录验证错误
- `video_splitter/review.py` — 转录审查模块，记录进度文件损坏等警告

## 约定与约束
1. 新增模块应使用 `logger = logging.getLogger(__name__)` 获取 logger，不要创建新的 basicConfig。
2. 日志级别遵循：info 记录业务进展，error 记录异常与失败，warning 记录可恢复的数据问题。
3. 由于未配置结构化字段，日志为纯文本行，不适合直接投递到集中式日志平台；如需结构化输出需扩展 handler。
4. GUI 与 CLI 共享同一根 logger，但 GUI 启动时不重新配置 basicConfig，依赖 CLI 侧的全局初始化。