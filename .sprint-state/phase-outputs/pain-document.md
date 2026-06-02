# Video Splitter — 培训视频智能拆分工具

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
| 语音识别 | **faster-whisper** (large-v3) | 支持中文，VAD 滤波加速，纯本地运行 |
| 分章引擎 | **DeepSeek/OpenAI API** | 分析转录稿找自然主题边界 |
| 视频裁剪 | **FFmpeg** | 已经被 ffmpeg-skill 封装 |
| 语言 | **Python** | Whisper 生态最完善 |
| 交付 | **独立 CLI 工具** | 可被 skill 包装，也可独立使用 |

### 为什么不直接用 QiYongchuan/video-chapter-splitter

该项目虽然有参考价值，但：
- Claude 专有 API（我们需要支持 DeepSeek 等国产模型）
- 无约束检查（不保证每段 ≤15 分钟）
- 无自动命名规则
- 缺少批量处理能力
更合理的是基于其思路，自己实现一个完整工具。

## 系统架构

```
输入: training_video.mp4 (30分钟)
  │
  ├─ [Step 1: 音频提取] FFmpeg → 16kHz mono WAV
  │
  ├─ [Step 2: 语音识别] faster-whisper large-v3 → 带时间戳的转录稿
  │     输出: transcript.json [{text, start, end}, ...]
  │
  ├─ [Step 3: 语义分章] LLM API 分析全文
  │     输入: 完整标题行 + 转录稿
  │     Prompt: "这是一段中文培训视频的转录稿，请分析内容结构，
  │              找出3-7个自然的主题分界点。每个分界点对应一个
  │              独立的知识点。每段时长控制在3-15分钟。"
  │     输出: [{title: "01_系统架构概述", start: "00:00:00", end: "00:08:30"}, ...]
  │
  ├─ [Step 4: 约束检查] 确保:
  │     - 每段 ≤ 15分钟（超长段递归细分）
  │     - 每段 ≥ 1分钟（合并过短段）
  │     - 命名规则: 原始文件名_序号_主题名.mp4
  │
  └─ [Step 5: 视频裁剪] FFmpeg 按时间戳裁剪
        输出: training_video_01_系统架构概述.mp4 (8:30)
              training_video_02_部署方案.mp4 (10:15)
              training_video_03_性能优化.mp4 (12:00)
```

## 项目结构

```
skill开发/
├── video-splitter/              # 新工具
│   ├── __init__.py
│   ├── cli.py                   # 命令行入口
│   ├── config.py                # 配置管理
│   ├── extractor/
│   │   ├── __init__.py
│   │   ├── audio.py             # FFmpeg 音频提取
│   │   └── transcribe.py       # Whisper 转录 + 合并场景检测
│   ├── analyzer/
│   │   ├── __init__.py
│   │   ├── chapter.py           # LLM 分章
│   │   └── validator.py         # 约束检查 + 命名
│   ├── splitter/
│   │   ├── __init__.py
│   │   └── cutter.py            # FFmpeg 裁剪
│   └── tests/
│       ├── test_audio.py
│       ├── test_transcribe.py
│       ├── test_chapter.py
│       ├── test_validator.py
│       └── fixtures/            # 测试用短视频
├── requirements.txt             # 添加 faster-whisper, pysubs2
├── pyproject.toml               # 新增
└── ...
```

## CLI 设计

```bash
# 完整流程：转录 → 分章 → 裁剪
python -m video_splitter split training_video.mp4 --max-duration 15

# 仅转录（跳过 LLM 分章）
python -m video_splitter transcribe training_video.mp4

# 仅裁剪（使用已有 JSON 分章结果）
python -m video_splitter cut training_video.mp4 --chapters chapters.json

# 批量处理
python -m video_splitter batch ./videos/ --max-duration 15

# 配置模型
python -m video_splitter config --model deepseek-chat --api-key sk-xxx
```

## LLM 分章 Prompt 设计

```
你是一位视频编辑专家。请分析以下中文培训视频转录稿，完成以下任务：

1. 识别视频中的主要话题和知识点
2. 找到每个话题的自然起止时间点
3. 为每个话题生成简洁的中文标题（≤12个字）
4. 每段时长尽量控制在3-15分钟之间

输出JSON格式（不要markdown包裹）：
[{"title": "01_系统架构概述", "start": "00:00:00", "end": "00:08:30"}, ...]

规则：
- 段落边界必须是自然话题转换点，不能强行在句子中间切断
- 序号从01开始递增
- 时间戳格式为 HH:MM:SS 或 MM:SS
- 如果全文不足15分钟，可以只输出一个段落

转录稿：
---
{transcript}
---
```

## 与需求二的关系

本工具只做拆分。需求二（双语字幕）的已有程序通过以下方式衔接：
- `clip --format srt` 输出 SRT 字幕文件
- 字幕文件可传入需求二的程序做翻译+合成
- 两者通过文件系统松耦合

## 不做的事情

- ❌ 双语字幕生成（已有独立程序）
- ❌ TTS 语音合成
- ❌ 视频特效/转场
- ❌ Web UI（第一版纯 CLI）
- ❌ GPU 加速的实时处理（用 faster-whisper 本地运行已足够）

## MVP 范围

1. ✅ 单个视频拆分（transcribe → analyze → split）
2. ✅ 约束检查（≤15min，≥1min，命名规则）
3. ✅ LLM 分章（支持 DeepSeek 和 OpenAI 兼容 API）
4. ✅ CLI 工具
5. ✅ 基本测试覆盖
6. ❌ 批量处理（Phase 2）
7. ❌ 增量处理/缓存（Phase 2）
8. ❌ OpenCode skill 封装（Phase 2）
