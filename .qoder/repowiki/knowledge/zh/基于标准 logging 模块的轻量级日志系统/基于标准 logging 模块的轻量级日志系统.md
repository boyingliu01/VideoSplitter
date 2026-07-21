---
kind: logging_system
name: 基于标准 logging 模块的轻量级日志系统
slug: logging_system
category: logging_system
scope:
    - '**'
---

## 系统概述

本项目采用 Python 标准库 `logging` 模块作为唯一日志框架，未引入第三方日志库（如 loguru、structlog 等）。日志配置集中在 CLI 入口文件，各业务模块通过 `logging.getLogger(__name__)` 获取独立 logger 实例。

## 核心架构与约定

### 1. 全局初始化位置
- **集中配置**：`video_splitter/cli.py` 在模块加载时调用 `logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")`，统一设置日志级别为 INFO，输出格式包含时间戳、级别和消息。
- **根 logger**：CLI 中显式创建名为 `"video_splitter"` 的命名 logger，用于 CLI 层自身的错误记录（如批量处理失败）。

### 2. 模块级 Logger 模式
- 所有业务模块遵循 `logger = logging.getLogger(__name__)` 惯例，获得以模块路径命名的子 logger：
  - `video_splitter.pipeline` → Pipeline 执行状态、步骤完成、错误信息
  - `video_splitter.review` → 进度文件损坏警告、SRT 生成失败警告
- 日志使用结构化字符串模板，关键上下文通过 f-string 嵌入消息体。

### 3. 日志级别使用规范
- **INFO**：业务流程推进（预检查、转录、章节检测、验证、切割完成）、资源路径输出
- **WARNING**：可恢复异常（进度文件损坏被重命名为 `.corrupted`、依赖缺失但非致命）
- **ERROR**：不可恢复错误（Pipeline 整体失败、批量任务单条失败）
- **DEBUG/CRITICAL**：当前代码库中未见使用

### 4. 输出目标
- 默认仅输出到控制台（stderr），无文件 sink、无轮转策略、无异步写入。
- CLI 命令的交互式输出（如 `cmd_check`、`cmd_review`）直接使用 `print()`，不属于结构化日志范畴。

## 设计决策与约束

| 方面 | 现状 | 说明 |
|------|------|------|
| 框架选择 | 标准库 `logging` | 零依赖，适合工具型项目 |
| 结构化字段 | 无 | 日志为纯文本，无 JSON 序列化 |
| 日志路由 | 无 | 所有模块共享同一 basicConfig |
| 外部集成 | 无 | 未接入 ELK、Sentry、CloudWatch 等后端 |
| 性能考量 | 同步阻塞 | 长耗时操作（转录、切割）期间日志可能延迟显示 |

## 开发者应遵循的规则

1. **始终使用模块级 logger**：在文件顶部定义 `logger = logging.getLogger(__name__)`，禁止直接调用 `logging.info()` 等函数式 API。
2. **合理选择日志级别**：流程节点用 INFO，预期内异常用 WARNING，崩溃性错误用 ERROR。
3. **避免在热路径频繁打日志**：转录、分片循环等高频场景慎用日志，以免 I/O 成为瓶颈。
4. **敏感信息脱敏**：API Key、用户数据不应出现在日志消息中（当前代码已遵守此约定）。
5. **CLI 交互输出与日志分离**：面向用户的提示用 `print()`，面向运维诊断的用 `logger`。