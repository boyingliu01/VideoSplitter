---
kind: error_handling
name: 错误处理体系：FFmpegError 与 Pipeline 统一异常捕获
category: error_handling
scope:
    - '**'
source_files:
    - ffmpeg-skill/__init__.py
    - video_splitter/pipeline.py
    - ffmpeg-skill/ffmpeg_tool.py
    - ffmpeg-skill/examples.py
---

本仓库的错误处理采用「领域自定义异常 + 顶层 try/except 包裹」的轻量模式，集中在 ffmpeg-skill 层定义、video_splitter.pipeline 层统一捕获。

1. 系统/方法
- ffmpeg-skill 定义唯一领域异常 FFmpegError(Exception)，所有 FFmpeg/ffprobe 子进程调用失败（返回码非零、超时、JSON 解析失败、文件不存在）均包装为 FFmpegError 抛出，避免底层 subprocess.TimeoutExpired、FileNotFoundError、json.JSONDecodeError 泄漏到上层。
- video_splitter 核心流水线 Pipeline.run() 使用单一 try/except Exception as e: 块包裹全部步骤（precheck → transcribe → chapter → validate → cut），将任意异常转为结果字典中的 status: "error" + error: str(e)，再重新 raise，保证 CLI/GUI 能拿到结构化结果。
- GUI 层未发现专门的异常中间件或全局 handler，依赖 PySide6 主循环默认行为；ffmpeg_tool.py 的 CLI 入口用 except FFmpegError / FileNotFoundError / ValueError / KeyboardInterrupt / Exception 分层捕获并打印后退出。

2. 关键文件
- ffmpeg-skill/__init__.py：FFmpegError 定义及 _run_command/get_video_info 等方法的统一异常封装
- video_splitter/pipeline.py：Pipeline.run() 的顶层 try/except 统一捕获与结果结构
- ffmpeg-skill/ffmpeg_tool.py：CLI 入口的分层 except 分支
- ffmpeg-skill/examples.py：示例代码对 FFmpegError 的统一捕获用法

3. 架构与约定
- 异常边界清晰：ffmpeg-skill 是 I/O 边界，内部只抛 FFmpegError；video_splitter 业务层不定义新异常类型，直接透传或触发 RuntimeError（如 precheck 失败）。
- 错误传播路径：底层 subprocess 异常 → FFmpegError → 被 Pipeline.run() 捕获 → 写入 result["error"] → 向上抛出，由调用方决定展示策略。
- 无 panic/recover、无全局 middleware、无错误码枚举，属于 Python 标准异常 + 单例领域异常的朴素风格。

4. 开发者应遵循的规则
- 在 ffmpeg-skill 之上工作的代码只需捕获 FFmpegError，不要直接捕获 subprocess.* 或 FileNotFoundError。
- 新增视频处理步骤时，如需提前失败，优先抛 ValueError（参数校验）或 RuntimeError（运行时不可恢复），让 Pipeline.run() 统一记录。
- 不要在业务层吞掉异常；若需降级，应在捕获后记录日志并返回可恢复状态，而非静默忽略。