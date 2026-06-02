# Delphi Round 1 → Round 2 修复报告

## Critical Issues 修复

### 1. LLM 容错/降级策略 (Expert A, B, C)
- **修复**: Step 3 增加多层容错：
  - exponential backoff retry (max 3次)
  - json-repair 库修复非法 JSON
  - pydantic schema 验证 timecode + duration
  - 幻觉检测（start/end 不得超出视频时长）
  - 全部失败 → 等分 15min 段 + 编号命名 fallback

### 2. Transcript token 预算 & 分块策略 (Expert A, B, C)
- **修复**: Step 3 增加 sliding-window chunking：
  - ≤60K tokens → 单次 LLM 调用
  - >60K → 按 ~15min transcript 分窗口，overlap=2min，独立分章后去重合并

### 3. ffmpeg-skill 耦合方式 (Expert A)
- **修复**: 明确选择硬依赖——从 ffmpeg-skill import FFmpegSkill，不复写 subprocess 调 ffmpeg

### 4. 超大视频 OOM (Expert B)
- **修复**: Step 1 使用 FFmpeg pipe（避免写磁盘 WAV），超长视频 >2h 回退到临时文件

### 5. 音频质量预检 (Expert B)
- **修复**: 新增 Step 0——librosa RMS 检测静音比例，静音>90% 警告，无声频 fail-fast

### 6. FFmpeg keyframe 对齐 (Expert B)
- **修复**: Step 5 增加 `--cut-mode` 选项：
  - fast (默认): stream copy + 自动搜索最近 keyframe，偏移>0.5s fallback 到 precise
  - precise: re-encode

### 7. LLM JSON 解析无恢复 (Expert C)
- **修复**: 同上 #1，json-repair + schema validation + fallback

### 8. 模型部署负担 & UX (Expert C)
- **修复**: 
  - 一键安装脚本含 model 预下载
  - `check` 命令：依赖验证 + 性能预估
  - `--dry-run`：预估 API cost 不调 LLM
  - `--model` 参数支持 tiny~large
  - ETA 显示 (tqdm)

## Major Concerns 处理

### 1. 中间产物 & 可恢复性 (Expert A)
- **修复**: 定义了中间产物路径约定 + `--resume` 标志

### 2. 时间精度 & 边界对齐 (Expert A)
- **修复**: Step 4 增加边界对齐——chapter 边界对齐到最近 transcript segment 边界

### 3. CLI-only 用户适配 (Expert C)
- **修复**: 定位调整为"技术人员工具"（运维/开发代为执行），MVP 不再强求非技术人员自服务。Phase 2 加 Gradio Web UI

### 4. 并行处理潜力 (Expert B)
- **修复**: config 预留 `compute_type` 和 `device` 配置项，自动检测 CUDA

### 5. 命名规则存储 (Expert B)
- **修复**: config.py 预留命名模板字段 `{basename}_{seq:02d}_{title}`

### 6. 批量处理 (Expert C)
- **修复**: 基础批量纳入 MVP——for-loop + 汇总报告

### 7. 字幕副产品 (Expert C)
- **修复**: transcript.json → SRT 转换纳入 scope（~30行代码）

## Minor Concerns 说明

- Expert A: batch CLI 在 MVP scope 已纳入，不再标记为 [Phase 2]
- Expert B: tests/ 目录区分 unit/ 和 integration/（integration 测试标记 skip 条件）
- Expert C: 所有中间产物路径规范已定义

## 请求重新评审

所有 Critical Issues 已修复，所有 Major Concerns 已处理。请求进入 Delphi Round 2。
