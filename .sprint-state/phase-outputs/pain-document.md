# Video Splitter — 培训视频智能拆分工具 (v2)

> **Delphi Round 1 修复版本** — 针对 Expert A/B/C 的 Critical Issues 和 Major Concerns 逐条修复

## Pain Point
公司技术社区有大量中文培训视频（几十分钟到数小时），不适合移动互联网传播。
需要：自动按主题拆分成 ≤15 分钟的短片段，并自动命名。

## 技术路线

### 核心思路：ASR 语音转文字 → LLM 语义分章 → FFmpeg 裁剪

纯视频信号分析（scene/silence detect）对静态讲座视频精度太低。
语音识别 + 大模型语义分析是唯一能准确识别"内容边界"的方案。

### 技术栈选择

| 组件 | 选择 | 理由 |
|------|------|------|
| 语音识别 | **faster-whisper** (large-v3 为主，支持 tiny~large) | 中文支持，VAD 滤波，CTranslate2 加速，纯本地；支持 `--model` 切换 |
| 分章引擎 | **DeepSeek/OpenAI 兼容 API** | 分析转录稿找自然主题边界 |
| 视频裁剪 | **FFmpeg**（直接 import ffmpeg-skill 的 FFmpegSkill 类） | 复用已验证的 error handling + progress callback |
| 语言 | **Python** | Whisper 生态最完善 |
| 交付 | **独立 CLI + 一键安装脚本** | MVP 定位为技术人员工具（运维/开发代为执行），Phase 2 加 Gradio Web UI |

### 与 ffmpeg-skill 的耦合方式

**明确选择：硬依赖**。video-splitter 直接 `from ffmpeg_skill import FFmpegSkill`。
- 复用 FFmpegSkill 的 error handling / progress callback / codec 预设
- cutter.py 不写 subprocess 调 ffmpeg 的代码——统一入口
- setup.py/pyproject.toml 中声明 `ffmpeg-skill` 为依赖
- 这意味着 video-splitter 和 ffmpeg-skill 在同一个仓库下协同开发

### 为什么不直接用 QiYongchuan/video-chapter-splitter
- Claude 专有 API → 需要支持 DeepSeek 等国产模型
- 无约束检查 → 不保证 ≤15min
- 无自动命名规则
- 无 LLM 容错/降级策略
- 无 transcript token 预算管理

## 系统架构

```
输入: training_video.mp4 (30分钟~3小时)
  │
  ├─ [Step 0: 预检] 音频质量检测 (librosa RMS/静音比例)
  │     - 静音比例 > 90% → 警告，跳过
  │     - 无声频 → fail-fast，提示用户
  │
  ├─ [Step 1: 音频提取] FFmpeg pipe → 16kHz mono，避免写磁盘
  │     超长视频 (>2h) 使用临时文件避免内存 OOM
  │
  ├─ [Step 2: 语音识别] faster-whisper → timestamped transcript
  │     模型: large-v3 默认, 支持 --model tiny/medium/large-v3
  │     输出: transcript.json [{text, start, end}, ...]
  │     ETA: 显示各阶段预估耗时 (模型加载/推理/预估进度)
  │     中间产物保存: {video_name}.transcript.json（支持 --resume 跳过）
  │
  ├─ [Step 3: 语义分章] LLM API + 容错机制
  │
  │   ┌─ 3a. Token 预算检查 ──────────────────────┐
  │   │   估算 transcript token 数                   │
  │   │   ≤60K tokens → 单次调用                     │
  │   │   >60K tokens → sliding-window chunking      │
  │   │      每窗口 ~15min transcript, overlap=2min  │
  │   │      窗口内独立 LLM 分章，合并时去重边界     │
  │   └─────────────────────────────────────────────┘
  │
  │   ┌─ 3b. LLM 调用 + 容错 ───────────────────────┐
  │   │   - Retry: exponential backoff (max 3 次)    │
  │   │   - JSON 修复: json-repair 库修正常见错误    │
  │   │   - Schema 验证: pydantic 校验 timecode 范围 │
  │   │   - 幻觉检测: start/end 不得超出视频时长     │
  │   │   - 降级: 全部失败 → 等分 15min 段 + 编号   │
  │   └─────────────────────────────────────────────┘
  │
  │     输出: {video_name}.chapters.json
  │           [{title: "01_系统架构概述", start: "00:00:00", end: "00:08:30"}, ...]
  │     中间产物保存，支持 --resume 跳过
  │
  ├─ [Step 4: 约束检查 + 对齐] validator
  │     - 每段 ≤15min（超长递归再细分：征用LLM或等分）
  │     - 每段 ≥1min（过短合并到相邻段）
  │     - 命名: {原文件名}_{序号}_{主题名}.mp4
  │     - 边界对齐: chapter边界 → 最近 transcript segment 边界
  │       避免在句子中间切
  │     - 文件名清理: 移除 `/:*?"<>|` 等非法字符
  │
  └─ [Step 5: 视频裁剪] FFmpegSkill.cut()
       切割模式: --cut-mode {fast, precise}
         fast (默认): stream copy, 自动搜索最近 keyframe
                     偏移 >0.5s 时 fallback 到 precise
         precise: re-encode, 帧精确
       输出: training_video_01_系统架构概述.mp4
             training_video_02_部署方案.mp4
             ...
```

## 项目结构

```
skill开发/
├── video-splitter/
│   ├── __init__.py
│   ├── cli.py                    # CLI 入口
│   ├── config.py                 # 配置管理 (模型路径/API key/约束参数)
│   ├── pipeline.py               # Pipeline 编排 (step 0→5)
│   ├── extractor/
│   │   ├── __init__.py
│   │   ├── audio.py              # FFmpeg pipe 提取 + 音频预检
│   │   └── transcribe.py         # Whisper 转录 + schema定义
│   ├── analyzer/
│   │   ├── __init__.py
│   │   ├── chapter.py            # LLM 分章 (含 token预算/chunking/retry)
│   │   └── validator.py          # 约束检查 + 边界对齐 + 命名
│   ├── splitter/
│   │   ├── __init__.py
│   │   └── cutter.py             # FFmpegSkill.cut() 封装
│   └── tests/
│       ├── test_audio.py
│       ├── test_transcribe.py
│       ├── test_chapter.py
│       ├── test_validator.py
│       ├── test_pipeline.py
│       └── fixtures/
├── requirements.txt              # faster-whisper, json-repair, pydantic, librosa, tqdm
├── pyproject.toml
├── install.bat / install.sh      # 一键安装 (Python + FFmpeg + model download + API key)
└── .env.example                  # DEEPSEEK_API_KEY / OPENAI_API_KEY / WHISPER_MODEL_SIZE
```

## CLI 设计

```bash
# 完整流程：预检 → 转录 → 分章 → 裁剪
python -m video_splitter split training_video.mp4 --max-duration 15

# 仅转录（跳过 LLM）
python -m video_splitter transcribe training_video.mp4

# 仅裁剪（使用已有 chapters.json）
python -m video_splitter cut training_video.mp4 --chapters chapters.json

# 断点续传（跳过已完成 step）
python -m video_splitter split video.mp4 --resume

# 预览 cost（不调 API）
python -m video_splitter split video.mp4 --dry-run

# 小模型快速模式
python -m video_splitter split video.mp4 --model medium

# 精确切割
python -m video_splitter split video.mp4 --cut-mode precise

# 依赖检查
python -m video_splitter check

# 批量（MVP 内包含基础批量：for-loop + 汇总报告）
python -m video_splitter batch ./videos/ --max-duration 15

# 配置
python -m video_splitter config --show       # 查看当前配置
python -m video_splitter config --set api_key sk-xxx
```

## LLM 分章 Prompt 设计

```
你是一位视频编辑专家。请分析以下中文培训视频转录稿，完成以下任务：

1. 识别视频中的主要话题和知识点
2. 找到每个话题的自然起止时间点（格式: HH:MM:SS 或 MM:SS）
3. 为每个话题生成简洁的中文标题（≤12个字，不含特殊字符）
4. 每段时长尽量控制在3-15分钟之间

必须严格按照以下JSON格式输出（不含任何其他文字）：
[
  {"title": "01_系统架构概述", "start": "00:00:00", "end": "00:08:30"},
  {"title": "02_部署方案", "start": "00:08:30", "end": "00:18:45"}
]

规则：
- 段落边界必须是自然话题转换点，不能强行在句子中间切断
- 序号从01开始递增
- 如果全文不足15分钟，可以只输出一个段落
- start 和 end 必须在 00:00:00 到 {video_duration} 之间
- 相邻段落的 end 应等于下一段的 start (无间隙无重叠)

转录稿 ({total_duration}，含时间戳)：
---
{transcript}
---
```

## 降级策略

| 故障点 | 降级方案 |
|--------|---------|
| LLM API 不可达 (3次重试后) | 按 15min 等分 + 编号命名 |
| LLM 返回非法 JSON (修复失败后) | 按 15min 等分 |
| faster-whisper 无法加载 | 提示用户安装/切换模型，退出 |
| FFmpeg 不可用 | fail-fast 退出 |
| 音频质量差 (无声/噪音) | 警告 + 跳过，不阻塞 |
| 切割点与 keyframe 偏移 >0.5s | 自动 fallback 到 re-encode |

## 模型部署策略

- **模型管理**: 下载到 ~/.cache/video-splitter/models/，由 faster-whisper 自动管理
- **首次使用**: `install.sh` 预下载 large-v3 (~2.9GB)，或 `video-splitter check` 触发下载
- **ETA**: 每个 step 显示进度（tqdm for FFmpeg, faster-whisper 内置进度回调）
- **GPU 检测**: 自动检测 CUDA/CUDNN，报告 CPU vs GPU 模式
- **CPU回退**: 无 GPU 时使用 int8 量化 + 多线程，显示预估耗时
- **性能预估**: `video-splitter check` 输出 benchmark (模型加载+ 30s样本推理时间)

## 中间产物 & 可恢复性

所有中间产物保存到与输入视频同目录：
```
training_video.mp4
training_video.transcript.json       # Step 2 输出
training_video.chapters.json         # Step 3 输出
training_video_segments/             # Step 5 输出目录
    ├── training_video_01_系统架构概述.mp4
    └── ...
```

`--resume` 参数检测中间产物是否存在，跳过已完成 step。
失败时保留已完成 step 产物，用户可手动修复中间文件后 `--resume`。

## 与需求二的关系

本工具只做拆分。需求二（双语字幕）通过以下方式衔接：
- Step 2 产出 `transcript.json`（含时间戳），可转 SRT 字幕（≤30行代码）
- 字幕文件传入需求二的程序做翻译+合成
- 两者通过文件系统松耦合

## 不做的事情

- ❌ 双语字幕生成（已有独立程序，但会输出 SRT 副产品）
- ❌ TTS 语音合成
- ❌ 视频特效/转场
- ❌ Web UI（Phase 2: Gradio）

## MVP 范围

1. ✅ 单个视频拆分（precheck → transcribe → analyze → split）
2. ✅ LLM 容错 (retry + json-repair + fallback 等分)
3. ✅ Transcript token 预算管理 + sliding-window chunking
4. ✅ 约束检查（≤15min，≥1min，边界对齐，命名规则）
5. ✅ 断点续传 (--resume)
6. ✅ 依赖检查 (video-splitter check)
7. ✅ 音频质量预检
8. ✅ 基本测试覆盖
9. ✅ 一键安装脚本
10. ✅ 基础批量 (for-loop + 汇总报告)
11. ❌ Web UI（Phase 2）
12. ❌ OpenCode skill 封装（Phase 2）
