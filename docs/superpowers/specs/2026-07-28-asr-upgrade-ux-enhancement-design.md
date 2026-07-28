# ASR 引擎升级 + 用户体验增强 — 设计规格

**日期**: 2026-07-28  
**状态**: 已批准（Delphi review v2 → v3 最终修订）  
**审核**: Delphi review — Architecture/Tech/Feasibility 三位专家，两轮评审，最终 APPROVED  
**关联**: 替换 Paraformer → Fun-ASR-Nano / SenseVoice, LLM 后处理, UX 改进

---

## 1. 问题背景

### 1.1 当前问题

| 问题 | 影响 |
|------|------|
| Paraformer 无 VAD，按固定 30s 切 chunk | 跨 chunk 断句错误：一句话被切成两半 |
| Paraformer 无 VAD，不感知自然停顿 | 段落内部断句错误：长停顿未断，短停顿反而断开 |
| 语气词（啊、嗯、呃）被保留在识别结果中 | 人工审核需逐句手动删除，工作量巨大 |
| 右侧字幕单条显示，无法看到全貌 | 审核效率低，无法感知进度 |
| 热词仅在 Worker 创建时快照，加载后不生效 | 已修复（上一轮），但 Paraformer 热词精度有限 |
| 无断点续传 | 大视频分段审核，中断后只能从头开始 |

### 1.2 FunASR 模型对比

| 模型 | CER (zh) | 热词 | VAD | 标点 | GPU 显存 | CPU 速度 | 真实场景表现 | 备注 |
|------|----------|------|-----|------|----------|----------|-------------|------|
| **Paraformer-Large** (当前) | 10.18% | ✅ `hotword` | ❌ 需外挂 | ❌ 需 `ct-punc` | ~900MB | 15x 实时 | 基准 | 非自回归 |
| **Fun-ASR-Nano** (GPU 首选) | 8.06% | ✅ `hotwords` | ✅ `fsmn-vad` | ✅ 内置 | ~4GB | 3.6x 实时 | ⭐ 最佳：LLM 架构对噪音/方言/专业术语鲁棒 | 旗舰 LLM-ASR |
| **SenseVoiceSmall** (CPU 降级) | 7.81% | ❌ 不支持 | ✅ `fsmn-vad` | ✅ 内置 | ~250MB | 17x 实时 | 通用 benchmark CER 最低，但非 LLM 架构 | 非自回归，CPU 王者 |

> **CER 说明**: SenseVoice (7.81%) 在 184 文件中文 benchmark 上 CER 略低于 Fun-ASR-Nano (8.06%)，但 FunASR 官方确认 Fun-ASR-Nano 的 LLM 架构在真实复杂音频（噪声、方言、专业术语、上下文依赖）上更鲁棒。行业实测集中 Fun-ASR-Nano 全面优于 Paraformer。本项目场景含专业术语（质量管理体系标准），因此 GPU 路径仍然优先 Fun-ASR-Nano。
>
> Fun-ASR-Nano = SenseVoice encoder + Qwen3-0.6B decoder, ~800M 参数

---

## 2. 设计目标

1. **最大化 ASR 准确率**：GPU 优先 Fun-ASR-Nano（CER 8.06%），CPU 降级 SenseVoice（7.81%）
2. **VAD 自然断句**：消除跨段落/内部断句错误
3. **热词全程可用**：GPU 路径解码级热词，CPU 路径 LLM 后处理文本级校正
4. **LLM 全文后处理**：自动去语气词、修正断句、热词校正（CPU 降级时）
5. **字幕整体显示 + 播放同步高亮**：审核效率核心 UX 改进
6. **断点续传**：大视频分段审核不丢进度
7. **GPU/CPU 自动切换**：无需用户手动选择

---

## 3. 架构设计

### 3.1 模块总览

```
┌────────────────────────────────────────────────────────────┐
│                        GUI (app.py)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │ VideoPlayer  │  │ SubtitlePanel│  │ SplitPanel      │  │
│  │ (同步信号)   │  │ (整体显示+高亮│  │                 │  │
│  └──────┬───────┘  └──────┬───────┘  └─────────────────┘  │
│         │ position_changed │                               │
│         ▼                  ▼                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              ReviewController                        │   │
│  │  - 断点续传 (load/resume/clear progress)             │   │
│  │  - 时间→行号 映射 (_sync_segment_to_position 增强)   │   │
│  └──────────────────────┬──────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼──────────────────────────────┐   │
│  │           StreamingTranscribeWorker                   │   │
│  │  - 引擎选择: GPU(Fun-ASR-Nano) / CPU(SenseVoice)     │   │
│  │  - VAD 断句 (fsmn-vad)                               │   │
│  │  - 热词传递 (set_hotword @Slot)                      │   │
│  └──────────────────────┬──────────────────────────────┘   │
└─────────────────────────┼──────────────────────────────────┘
                          │
┌─────────────────────────▼──────────────────────────────────┐
│                  extractor/engines.py                       │
│  ┌─────────────────────┐  ┌────────────────────────────┐   │
│  │ FunASRNanoEngine    │  │ SenseVoiceEngine           │   │
│  │ (GPU, CUDA)         │  │ (CPU, 纯非自回归)          │   │
│  │ + fsmn-vad          │  │ + fsmn-vad                │   │
│  │ + hotwords          │  │ - hotword (不支持)         │   │
│  └─────────┬───────────┘  └────────────┬───────────────┘   │
│            │                            │                    │
│            └──────────┬─────────────────┘                    │
│                       ▼                                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │            postprocess.py (新增)                     │   │
│  │  - LLM 全文润色 (去语气词/修正断句)                   │   │
│  │  - 热词文本校正 (CPU 路径, postprocess_hotwords)     │   │
│  │  - 原文→润色后 时间戳映射 (序列对齐)                  │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 引擎选择流程

```
torch.cuda.is_available()?
  ├─ YES → FunASR-Nano (GPU)
  │         AutoModel(model="FunAudioLLM/Fun-ASR-Nano-2512",
  │                   trust_remote_code=True, remote_code="./model.py",
  │                   vad_model="fsmn-vad", vad_kwargs={"max_single_segment_time": 60000},
  │                   device="cuda:0", hub="hf")
  │         generate(input=[audio_path], cache={}, batch_size=1,
  │                  hotwords=["质量红线", "QIWC", ...], language="中文", itn=True)
  │         输出格式: res[0]["text"] (带标点的全文) + res[0]["timestamp"] (token 级时间戳)
  │
  └─ NO  → SenseVoiceSmall (CPU)
            AutoModel(model="iic/SenseVoiceSmall",
                      vad_model="fsmn-vad", vad_kwargs={"max_single_segment_time": 60000},
                      device="cpu")
            generate(input=audio_path, cache={}, language="auto", use_itn=True,
                     batch_size_s=60, merge_vad=True, merge_length_s=15)
            输出格式: res[0]["text"] (带 emotion/event 标签, 需 postprocess)
                    + res[0]["sentence_info"] (VAD 分段 + 时间戳)
```

### 3.3 VAD 配置（两个引擎共用）

```python
vad_model="fsmn-vad"
vad_kwargs={"max_single_segment_time": 60000}  # 最大段落 60 秒
```

VAD 自动检测语音静音边界，将长语音切分为自然句子。

**输出格式差异**:
- Fun-ASR-Nano: `res[0]["text"]` 为全文（无 `sentence_info`），需从 `res[0]["timestamp"]` 重建 segment 边界。`timestamp` 为 `[[start_ms, end_ms], ...]` 格式，与每个字符/词对应，按标点符号断句。
- SenseVoice: `res[0]["text"]` 包含 `<|zh|><|Speech|>` 等标签，需 `rich_transcription_postprocess()` 清洗。VAD 分段信息在 `res[0]["sentence_info"]` 中（`[{text, start, end}, ...]`，时间单位 ms）。
- 新增 `_extract_segments_from_timestamps()` 处理 Fun-ASR-Nano 的时间戳格式。

---

## 4. 模块详细设计

### 4.1 模块 1：ASR 引擎双模替换

**文件**: `video_splitter/extractor/engines.py`

**变更**：
1. 新增 `GPU_AVAILABLE = torch.cuda.is_available()`
2. 新增 `_FUNASR_NANO_MODEL = "FunAudioLLM/Fun-ASR-Nano-2512"` (GPU)
3. 新增 `_SENSEVOICE_MODEL = "iic/SenseVoiceSmall"` (CPU)
4. `FunASREngine.__init__`: 根据 `GPU_AVAILABLE` 选择模型，初始化 `AutoModel` + VAD
5. 移除旧的 chunk 相关逻辑（`read_wav_chunks`, `_split_audio_chunks`, `_extract_segments`, `_merge_segments`）— VAD 自动处理
6. `transcribe()`: 调用 `model.generate()` 获取 `sentence_info`，直接转换为 segments
7. 保留 `hotword` 参数接口 — GPU 路径传给 `generate(hotwords=[...])`，CPU 路径记录供 LLM 后处理使用

**移除的代码**：
- `FUNASR_CHUNK_SECONDS` 常量
- `read_wav_chunks()` 函数
- `_transcribe_chunk()` 方法
- `_extract_segments()` 复杂逻辑（替换为简单的格式转换函数）
- `FUNASR_MODEL_FALLBACKS` fallback 机制
- `PUNCTUATION_MODEL` 和 `punc_model` 相关逻辑（SenseVoice / Fun-ASR-Nano 自带标点）
- 单例 `_cached_funasr_model` → 改为 dict `_cached_models: dict[str, Any]`（按模型名缓存，避免 GPU→CPU 回退时的模型冲突）

**新增的代码**：
- `_extract_segments_from_sentence_info()`: SenseVoice 路径 — 将 `sentence_info` 转为统一 segment 格式。防御性访问：`res[0].get("sentence_info") or []`
- `_extract_segments_from_timestamps()`: Fun-ASR-Nano 路径 — 将 `timestamp`（`[[start_ms, end_ms], ...]`）按标点断句转为 segments。复用或适配现有的 `_extract_segments()` token→segment 逻辑（engines.py:372-481）
- GPU/CPU 路径分支（`_init_gpu_model` / `_init_cpu_model`）

### 4.1a StreamingTranscribeWorker 适配（关键依赖）

**文件**: `gui/workers/streaming_transcribe_worker.py`

**当前问题**: 该文件直接使用 `FunASREngine._extract_segments()`, `FUNASR_CHUNK_SECONDS` 按 30s 固定块切片 PCM，然后逐块调用 `model.generate()`。这与 VAD 驱动的引擎架构完全冲突。

**变更**:
1. **架构策略：fast-batch 模式**。现有 chunk-based streaming（PCM 逐块送入→逐块 emit segment）与 VAD 驱动的模型架构冲突。VAD 模型内部的断句依赖全文音频上下文，分批送入会破坏跨 chunk 的 VAD 一致性。**选择 fast-batch**：先完全提取音频，再一次送入 VAD 模型，模型内部 VAD 自动分段，结果按 segment 批次 emit。
2. 移除 PCM 切片循环（`read_wav_chunks` → 逐块 transcribe）
3. `model.generate(input=wav_path)` → 返回 `sentence_info`（SenseVoice）或 `timestamp`（Fun-ASR-Nano）
4. 将完整结果按 segment 批次 emit 到 GUI（非逐块流式，但仍保持逐段显示的视觉体验）
5. 移除 `_deduplicate_segments()` 和 `_merge_short_segments()` — VAD 自带的 merge 逻辑已处理
6. `request_priority()` 的优先级 seek 功能**移除**（不再有 chunk 队列）。用户可以在全部 subtitle segment 加载完成后通过点击列表行跳转。
7. 进度回调改变：从 "Recognizing segment N/T" 改为 "Extracting audio… → Transcribing… → Processing results…" 三阶段
8. 健康检查 `_HealthCheckWorker` 同步更新以使用新引擎选择逻辑

**OOM 回退**: 对于极长视频（>2h），采用窗口式 VAD：按 10 分钟窗口切片 PCM → 每个窗口 `model.generate(input=chunk_wav_i)` → VAD 在窗口内分段 → 拼接时加时间偏移。窗口间留 1s 重叠避免边界断句错误。

### 4.2 模块 2：LLM 全文后处理

**文件**: `video_splitter/extractor/postprocess.py` (新增)

**接口**:
```python
def postprocess_transcript(
    segments: list[dict],
    llm_config: dict,           # OpenAI-compatible config {api_key, base_url, model}
    hotwords: str | None = None,  # CPU 路径：文本级热词校正
    language: str = "zh",
) -> list[dict]:
    """LLM 全文后处理：去语气词、修正断句、可选热词校正。返回润色后的 segments。"""
```

**流程**:
1. 将 segments 拼接为全文（附带段落标记 `[SEG_N]`，N 从 0 开始）
2. 构造 LLM prompt（见下方）
3. LLM 返回带 `[SEG_N]` 标记的润色文本
4. 用序列对齐算法将润色后文本映射回原时间戳（见下方详情）
5. CPU 路径：LLM prompt 中加入热词列表要求校正（见 prompt 模板 Step 5）

**LLM Prompt 模板**:
```
请对以下语音识别结果进行润色：
1. 删除所有语气词和口头禅（如：啊、嗯、呃、哦、那个、就是说、然后、就是）
2. 修正明显的断句错误，将不完整的分句合并到相邻句子
3. 保持原文语义不变，不要添加原文没有的内容
4. 保持段落边界标记 [SEG_N] 的格式和顺序不变；如确需将两个相邻的不完整 [SEG_N] 合并，
   合并后保留较早的 [SEG_N]，删除较晚的标记。
{如有热词：
5. 以下专业术语必须正确识别，如果原文有音近错误请修正：
   {hotwords}}
直接输出润色后的文本，不要加任何解释。

原文：
[SEG_0] 今天啊我们呃来讨论一下嗯这个项目的那个实施方案也就是说……
[SEG_1] 首先呢我们要明确呃质量管理体系的几个关键那个节点……
```

**LLM 后处理时序**: 在 StreamingTranscribeWorker 的 `transcription_complete` 信号发出后执行。此时原始（未后处理）segments 已在 GUI 中显示。后处理运行在独立的 `PostprocessWorker(QObject)` + `QThread` 中，完成后通过信号替换 segments。Worker 线程生命周期：`MainWindow` 持有 `self._postprocess_thread`；`_on_open_video()` 和 `closeEvent()` 时先 cancel 后 join(timeout=5s) 确保线程安全终止。估计延迟：30 分钟视频 ~2000 segments → LLM 输入 ~15K tokens → 输出 ~10K tokens → 约 5–15 秒。

**序列对齐算法**（详见 §4.2a）:

**LLM 输出解析与验证**:
- 用正则 `\[SEG_(\d+)\]` 提取段落标记
- 如果标记数量与输入不匹配 (±0 容忍)、标记编号不连续、或标记格式异常 → 使用原始文本作为 fallback
- 如果任一 seg 中 LLM 输出的字符数超过原文 1.5x → 该 seg 回退到原文
- 新增 `VIDEO_SPLITTER_POSTPROCESS_TIMEOUT` 环境变量（默认 120 秒）

### 4.2a 序列对齐算法（详细规格）

**目标**: 将 LLM 润色后的文本（已去语气词/修正断句）映射回原 segment 的时间戳。

**算法**: 使用 `difflib.SequenceMatcher`（`autojunk=False`）在字符级做段落内对齐。

**步骤**:
1. 对每个 `[SEG_N]` 段落，提取 LLM 输出文本 `polished` 和原文 `original`
2. `matcher = SequenceMatcher(None, original, polished, autojunk=False)`
3. 遍历 `matcher.get_opcodes()`:
   - `equal`: 保留的字符 → 继承对应原文字符的时间戳
   - `replace`: 将原文字符的时间窗口按比例分配给润色后字符
   - `delete`: 将该字符的时间窗口均分给相邻保留字符（加权）
   - `insert`: 新字符 → 从相邻保留字符的时间窗口中均分（不能凭空创建时间戳）

**回退策略**:
- 如果 `len(polished) > 1.5 * len(original)`（LLM 过度扩展），该 seg 回退到原文
- 如果 `len(polished) < 0.3 * len(original)`（LLM 过度删除），该 seg 回退到原文
- 回退时 emit `postprocessing_warning` 信号，GUI 显示 "⚠️ 段 N 回退到原文"
- 整体 segment 数量变化 >20%（合并/拆分过多）→ 全部回退并告警

**合并/拆分段落处理**:
- LLM 合并了两个 `[SEG_N]` 和 `[SEG_N+1]` → 将合并段的 start 设为 `seg[N].start`，end 设为 `seg[N+1].end`
- LLM 拆分了一个 `[SEG_N]` 为两段 → 按字符比例均分原始 segment 的时间窗口

**配置**:
- LLM 配置从 `SplitConfig` 扩展现有 `llm_api_key`/`llm_base_url`/`llm_model` 字段
- 新增 `VIDEO_SPLITTER_POSTPROCESS_ENABLED` 环境变量（默认开启）
- 新增 `VIDEO_SPLITTER_POSTPROCESS_HOTWORD_THRESHOLD` (默认 0.85)

### 4.3 模块 3：字幕整体显示 + 播放同步高亮

**文件**: `gui/widgets/subtitle_panel.py` (重建字幕列表区域)

**新 UI 结构**:
```
┌──────────────────────────────┐
│ 开始语音识别                  │
├──────────────────────────────┤
│ Segment 5/101  [00:02:30.000] │
├──────────────────────────────┤
│ ┌ 字幕列表 (可滚动) ───────┐ │
│ │ [00:00.0] 今天我们来...  │ │ ← 正常行
│ │ [00:05.2] 讨论一下质量... │ │
│ │ [00:10.8] 管理体系的...   │ │ ← 高亮行 (金色背景)
│ │ [00:15.1] 关键节点包括... │ │ ← 自动滚动到此处
│ │ ...                      │ │
│ └──────────────────────────┘ │
├──────────────────────────────┤
│ 原文: 管理体系的...          │
│ 修正: [编辑框]               │
├──────────────────────────────┤
│ ◀上一段 下一段▶ 保存并继续▶ │
│ 跳到... 保存                  │
└──────────────────────────────┘
```

**核心逻辑**:

1. **整体列表**：用 `QListView` + `QStandardItemModel` 替代 `QListWidget`（后者在 500+ item 时 `setBackground` 逐 item 触发 repaint 性能差）。
   每行显示 `[mm:ss] 文本`，自定义 `QStyledItemDelegate` 在 `paint()` 中绘制高亮背景（免去 per-item `setBackground` 的 `dataChanged` 开销）。

2. **播放同步高亮** (`_sync_highlight`):
   - 监听 `position_changed` 信号 → 用 **二分查找**（`bisect.bisect_right` 在 segment starts 数组上）定位当前 segment 行号
   - 高亮由 delegate 的 `paint()` 在绘制时判断（`index.row() == current_highlight_row` → 金色背景 `#FFF3CD`）
   - **节流**: 高亮更新限制为 ~4fps（每 250ms），用 `QTimer` 合并连续 position 更新，避免 Windows Media Foundation 的 ~100ms 更新频率触发过频重绘
   - `scrollTo(index, QAbstractItemView.ScrollHint.PositionAtTop)` 自动滚动（比 `PositionAtCenter` 更轻量）
   - 不 emit 新信号 — `_sync_highlight` 是内部方法，只更新列表视觉状态。编辑区更新由现有 `ReviewController.segment_changed` 信号处理。

3. **点击跳转**：点击列表行 → `segment_activated.emit(start_seconds)` → `video_player.seek_to(start_seconds * 1000)`

4. **编辑模式**：**暂不实现双击原地编辑（inline QTextEdit overlay）**，降低初期复杂度。
   保留现有单行编辑区（原文 + 修正 + 保存按钮）的交互模式。列表高亮行同步显示在下方编辑区。
   双击预留为未来扩展点。

5. **快捷键导航**：`Ctrl+Shift+↑/↓` 移动列表焦点行（等价于 `prev()` / `next()` 但只移动焦点不触发编辑）

6. **原有编辑区保留**：列表高亮的行同步显示在下方原文+修正编辑区，保持现有审核流程兼容。

### 4.4 模块 4：按钮快捷键标注

**文件**: `gui/widgets/subtitle_panel.py`, `gui/widgets/video_player.py`

在按钮文字/ tooltip 中标注快捷键：

| 按钮 | 当前文字 | 修改后文字/tooltip |
|------|---------|-------------------|
| 播放/暂停 | `▶` / `⏸` | tooltip: "播放/暂停 (Space / Ctrl+Shift+P)" |
| 上一段 | `◀ 上一段` | `◀ 上一段 (Ctrl+Shift+←)` |
| 下一段 | `下一段 ▶` | `下一段 ▶ (Ctrl+Shift+→)` |
| 保存并继续 | `保存并继续 ▶` | `保存并继续 (Ctrl+Enter)` |
| 保存 | `保存` | `保存 (Ctrl+S)` |

### 4.5 模块 5：断点续传

**文件**: `gui/controllers/review_controller.py`, `gui/app.py`

**流程**:

1. **复用现有进度系统**: 进度文件就是现有的 `{video_path}.review_progress.json`（`video_splitter/review.py:_PROGRESS_SUFFIX`）。不创建新的进度文件。

2. **保存进度**（已有机制 — 无需改动）:
   - 每次 `save_correction()`, `next()`, `prev()`, `jump_to()` 调用后自动保存到 `.review_progress.json`
   - 格式: `{"current_index": N, "total": M, "modified_indices": [...], "version": 2}`

3. **恢复进度** (新增):
   - `MainWindow._on_open_video()` / `_on_open_transcript()` 后检查 `.review_progress.json`
   - 若存在且 `current_index > 0`，弹窗:
     > 检测到上次审核进度（第 X / 101 段），是否继续？
     > [继续] [从头开始]
   - 继续 → `controller.jump_to(current_index)`
   - 从头 → 删除 `.review_progress.json`，从第 0 段开始

4. **清除进度** (新增):
   - 审核完成（`next()` 返回 `None`）→ 自动删除 `.review_progress.json`
   - 这样做避免下次打开时误判

5. **格式兼容**: 添加 `"version": 2` 字段。旧格式（无 version 字段）仍可加载。

---

## 5. 数据流

### 5.1 完整识别 + 后处理流程

```
Video File
    │
    ▼
[AudioExtractor] → temp.wav (16kHz mono)
    │
    ▼
[ASR Engine] (GPU: FunASR-Nano / CPU: SenseVoice)
    │  + VAD (fsmn-vad) 自动断句
    ▼
sentence_info: [{start, end, text}, ...]
    │
    ▼
[LLM Postprocess] (全文一次性)
    │  - 去语气词
    │  - 修正断句错误
    │  - 热词文本校正 (CPU 路径)
    ▼
Cleaned segments: [{start, end, text}, ...]
    │
    ▼
[ReviewController] → GUI 字幕面板
```

### 5.2 字幕同步流程

```
VideoPlayer.position_changed(ms)
    │
    ▼
MainWindow._sync_segment_to_position(secs)
    │  (二分查找 segment index, 250ms QTimer 节流)
    │
    ▼
SubtitlePanel._sync_highlight(segment_index)
    │  - delegate.highlight_row = segment_index  (paint() 时绘制金色背景)
    │  - list_view.scrollTo(index, PositionAtTop)
    │
    ▼
SubtitlePanel.set_segment(index, total, text, start, end)
    │  (现有的 ReviewController.segment_changed → 更新下方编辑区)
```

---

## 6. 测试策略

| 测试层 | 测试内容 |
|--------|---------|
| 单元测试 | `postprocess.py` LLM prompt 格式与模板填充 |
| 单元测试 | `postprocess.py` 序列对齐算法：正常、过度扩展（>1.5x fallback）、过度删除（<0.3x fallback） |
| 单元测试 | `postprocess.py` LLM 输出解析：正常、标记丢失、标记编号不连续、标记数量不匹配 → 全部 fallback |
| 单元测试 | `engines.py` GPU 路径 `timestamps` → segments 转换 |
| 单元测试 | `engines.py` CPU 路径 `sentence_info` → segments 转换 |
| 单元测试 | `engines.py` VAD 返回 0 segments 的边界情况 |
| 单元测试 | `engines.py` GPU OOM → CPU fallback 的异常处理路径 |
| 集成测试 | CPU 路径完整 pipeline（SenseVoice + LLM postprocess） |
| GUI 测试 | `SubtitlePanel` QListView 渲染 500+ items、`QStyledItemDelegate` 高亮绘制 |
| GUI 测试 | `SubtitlePanel` 高亮同步节流（250ms QTimer） |
| GUI 测试 | `ReviewController` 断点续传 save/load/clear/version 兼容 |
| GUI 测试 | `PostprocessWorker` 线程 + signal 替换 segments |
| 手动验收 | 用实际 `测试数据/质量红线讲解.mp4` 对比旧 Paraformer 效果 |
| 手动验收 | Ctrl+Shift+P 播放/暂停, Ctrl+Shift+←/→ 导航, Ctrl+S 保存 |

---

## 7. 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| Fun-ASR-Nano 首次加载需下载 ~2GB 模型 + Qwen3-0.6B 子模型 | 加载进度回调 (已有 ModelLoaderWorker)；提示用户耐心等待 |
| LLM 输出标记 `[SEG_N]` 格式漂移（空格、大小写、重新编号） | 正则宽松解析 + 验证标记数量 = 输入数量；异常时全部回退到原文 |
| LLM 后处理可能引入语义漂移或幻觉内容 | Prompt 强调"保持原文语义不变"；提供关闭选项（环境变量）；字符数 >1.5x or <0.3x 自动回退 |
| 序列对齐在极端差异时映射不准（合并/拆分段落） | 段落级独立对齐 + 回退阈值（>20% seg 数变化 → 全部回退）；回退时 GUI 显示 ⚠️ 警告 |
| VAD 在嘈杂音频/长静音上效果波动 | `max_single_segment_time` 上限保护；允许用户通过环境变量调整 VAD 参数 |
| GPU 驱动/CUDA 版本不兼容 | `try/except` 优雅降级；降级前 `clear_funasr_model_cache()` 清理 GPU 模型缓存；健康检查时报告详情 |
| LLM 后处理 UI 阻塞（30-90s 延迟） | 运行在独立 `PostprocessWorker(QThread)`；原始 segments 先展示，后处理完成后再替换 |
| QListView 500+ items 性能 | Model/View 架构 + delegate 绘制高亮（免 per-item mutation）+ 二分查找 O(log N) + 250ms 节流 |
| VAD 返回 0 segments（纯静音视频） | 用户友好报错："No speech detected"；不崩溃 |
| FunASR 版本升级（1.3.14→1.3.29+）可能破坏现有代码 | 升级前运行完整测试套件；在 requirements.txt 中 pin 目标版本

---

## 8. 实施顺序

| 阶段 | 模块 | 估算工作量 | 理由 |
|------|------|-----------|------|
| 1 | 模块 1: ASR 引擎双模 | 核心 | 依赖项：模块 2 的 LLM 后处理需等模块 1 的 segment 格式稳定 |
| 2 | 模块 2: LLM 全文后处理 | 核心 | 依赖模块 1 的输出格式 |
| 3 | 模块 3: 字幕整体显示+同步高亮 | 大 | 独立 UI 模块，可与 1/2 并行但建议等 segment 格式确定后 |
| 4 | 模块 4: 快捷键标注 | 小 | 独立，随时可做 |
| 5 | 模块 5: 断点续传 | 小 | 独立，随时可做 |

> 模块 4 和 5 可在阶段 1-3 之间穿插实施。

---

## 9. 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `VIDEO_SPLITTER_ASR_DEVICE` | `auto` | `cuda` / `cpu` / `auto`（自动检测） |
| `VIDEO_SPLITTER_VAD_MAX_SEGMENT` | `60000` | VAD 最大段落长度 (ms) |
| `VIDEO_SPLITTER_FUNASR_HUB` | `hf` | ModelScope `ms` / HuggingFace `hf` |
| `VIDEO_SPLITTER_POSTPROCESS_ENABLED` | `1` | 是否启用 LLM 后处理 |
| `VIDEO_SPLITTER_POSTPROCESS_TIMEOUT` | `120` | LLM 后处理超时 (秒) |
| `VIDEO_SPLITTER_POSTPROCESS_MODEL` | (fallback 到 `llm_model`) | 专用后处理 LLM 模型 |
| `VIDEO_SPLITTER_POSTPROCESS_API_KEY` | (fallback 到 `llm_api_key`) | 专用后处理 API key |
| `VIDEO_SPLITTER_POSTPROCESS_API_BASE` | (fallback 到 `llm_api_base`) | 专用后处理 API endpoint |

---

## 10. 向后兼容性

- **旧格式 transcript**: 旧版 Paraformer chunk 产出的 `.transcript.json` 可以正常打开。segment 边界与新 VAD 引擎不同，但审核流程不变。
- **Transcript 元数据**: 新增 `"asr_engine": "funasr-nano-vad"` 或 `"asr_engine": "sensevoice-vad"` 字段到 transcript JSON。若缺少此字段（旧格式），不强制重新识别，但在 status bar 提示 "Legacy transcript — consider re-transcribing for VAD-based segmentation"。
- **进度文件**: 旧 `.review_progress.json`（无 `version` 字段）可正常加载，兼容读取。
- **CLI 路径**: 本阶段**不覆盖 CLI 路径**（`video_splitter/cli.py` 的 `cmd_transcribe` 仍用 whisper）。CLI 升级为后续阶段的可选优化。

## 11. 非目标 (Non-Goals)

- CLI pipeline (`pipeline.py`) 的引擎升级 — 本阶段仅覆盖 GUI 路径
- TTY review 路径 (`video_splitter/review.py`) — 本阶段不覆盖，segment 格式变化对其影响待评估
- 实时流式 LLM 后处理 — 采用一次性全文后处理
- 多语言支持 — 仅中文
- 说话人分离（`spk_model`）— 后续阶段可加 CAM++
- `request_priority` 优先级 seek — fast-batch 模式无 chunk 队列，此功能移除

## 12. 实施前置条件

1. **升级 FunASR**: `pip install -U "funasr>=1.3.29,<1.5"` 并在升级后运行完整测试套件，确认旧 Paraformer pipeline 无回归
2. **预下载模型**: 
   ```bash
   python -c "from funasr import AutoModel; AutoModel(model='iic/SenseVoiceSmall', vad_model='fsmn-vad', device='cpu')"
   ```
   这会下载 SenseVoice（~250MB）和 fsmn-vad（~0.4MB）。GPU 路径的 Fun-ASR-Nano（~2GB 含 Qwen3-0.6B）在 GPU 机器上按需下载。
3. **CUDA 验证**: 在有 4090 的机器上验证 `torch.cuda.is_available()` 和 Fun-ASR-Nano 加载。GPU 路径代码在 CPU 开发机上通过 mock engine 进行单元测试；整体验证依赖 GPU 机器上的定期手动 smoke test。

## 13. 测试迁移计划

| 受影响的现有测试 | 处理方式 |
|-----------------|---------|
| `tests/test_workers.py` — `TestStreamingTranscribeWorker` | 重写以 mock VAD-enabled engine（不再 mock chunk-based FunASREngine） |
| `tests/test_e2e_review.py` — subtitle panel 断言 | 更新以适应 `QListView` 替代 `QListWidget` 后的 API 变化 |
| `tests/test_gui_integration.py` — streaming flow | 更新 signal 连接以匹配新 worker 的 emit 模式 |
| `tests/test_e2e_real_data.py` — 使用 Paraformer 的测试 | 更新为 SenseVoice VAD 路径（CPU 环境）或 skip（GPU 环境） |
| `video_splitter/tests/test_engines.py` — engine 实例化 | 为新的 GPU/CPU 双路径添加测试 |
| 其他测试 | 无需变更（mock 在 engine 边界，不感知内部实现变化） |
