# VideoSplitter v0.4.0 人工验收测试清单

## 环境预检（已自动完成）

| 项目 | 状态 |
|------|------|
| Python 依赖 | ✅ 已安装 (PySide6 6.11.1) |
| FFmpeg | ✅ 可用 (PATH 中) |
| 全量测试 | ✅ 424/424 通过 |
| 测试视频 | ✅ `ffmpeg-video-workspace/test-files/acceptance_test.mp4` (60s, 含音频) |
| GUI 可导入 | ✅ MainWindow 正常导入 |

## 启动方式

```
双击 launch-gui.bat
```

---

## 验收用例

### TC-01: GUI 启动与初始状态
- [ ] 窗口正常显示，标题 "VideoSplitter - Subtitle Review & Split"
- [ ] 左侧视频播放区域空白
- [ ] 右侧有两个 Tab: "Review" 和 "Split"
- [ ] 底部状态栏显示 Engine 状态（OK 或模型未下载的提示）
- [ ] 菜单栏有 File 和 Help 菜单

### TC-02: 打开视频 + 自动转录
- [ ] File → Open Video，选择 `ffmpeg-video-workspace/test-files/acceptance_test.mp4`
- [ ] 视频开始在左侧播放
- [ ] 状态栏显示 "Transcribing: ..." 进度
- [ ] 转录完成后状态栏显示 "Transcription complete"
- [ ] （注意：合成音频无语音，FunASR 可能返回空 segments，属正常现象）

### TC-03: 视频播放控制
- [ ] 空格键：播放/暂停切换
- [ ] 视频可正常播放，有声音（440Hz 正弦波）
- [ ] 状态栏显示当前播放位置 "Position: MM:SS"

### TC-04: Review Tab 功能
- [ ] 切换到 Review Tab
- [ ] 如果有转录结果：显示分段文本、Prev/Next 按钮可用
- [ ] Ctrl+Right: 跳到下一段
- [ ] Ctrl+Left: 回到上一段
- [ ] Ctrl+S: 保存当前修改
- [ ] Ctrl+Return: 保存并跳到下一段
- [ ] 编辑文本后可保存修正

### TC-05: Split Tab 基础布局
- [ ] 切换到 Split Tab
- [ ] 顶部有 "Detect Chapters"、"Validate"、"Cancel" 按钮
- [ ] 中间有章节列表和时间线
- [ ] 底部有 Output 路径、Browse、Start Split、Burn Subtitles 按钮

### TC-06: 章节检测（需要 LLM API）
- [ ] 前提：已配置 LLM API 环境变量（如 DEEPSEEK_API_KEY）
- [ ] 点击 "Detect Chapters"
- [ ] 状态栏显示检测进度
- [ ] 检测完成后章节列表显示结果
- [ ] Validate 按钮变为可用
- [ ] （注意：无语音转录可能无法触发有效章节检测）

### TC-07: 手动操作章节
- [ ] 如果有章节列表：
  - [ ] 双击章节标题可编辑
  - [ ] 右键菜单有 Remove / Merge 选项
  - [ ] 时间线上可拖拽章节边界
  - [ ] 点击时间线可跳转播放位置

### TC-08: 视频分割
- [ ] 前提：有章节数据
- [ ] 设置输出目录（默认在视频同目录 `_segments` 文件夹）
- [ ] 点击 "Start Split"
- [ ] 状态栏显示分割进度
- [ ] 完成后弹出对话框询问是否打开输出文件夹
- [ ] 输出文件夹中有分割后的视频文件

### TC-09: 字幕烧录
- [ ] 前提：已完成分割 + 有转录数据
- [ ] "Burn Subtitles" 按钮在分割完成后变为可用
- [ ] 点击 "Burn Subtitles"
- [ ] 状态栏显示烧录进度
- [ ] 完成后弹出确认对话框

### TC-10: 导出章节
- [ ] File → Export Chapters
- [ ] 弹出保存文件对话框
- [ ] 导出的 JSON 文件内容正确

### TC-11: 打开已有转录文件
- [ ] File → Open Transcript
- [ ] 选择一个 `.transcript.json` 文件
- [ ] Review Tab 正确加载并显示内容

### TC-12: 取消操作
- [ ] 在转录/检测/分割进行中时，Cancel 按钮可用
- [ ] 点击 Cancel 后操作终止

### TC-13: Help 菜单
- [ ] Help → About 显示版本和功能信息

### TC-14: 错误处理
- [ ] 未打开视频就点 Detect Chapters → 弹出提示
- [ ] 未打开视频就点 Start Split → 弹出提示
- [ ] 无转录数据时 Burn Subtitles → 弹出提示

---

## 验收结果汇总

| 用例 | 通过 | 备注 |
|------|------|------|
| TC-01 | ☐ | |
| TC-02 | ☐ | |
| TC-03 | ☐ | |
| TC-04 | ☐ | |
| TC-05 | ☐ | |
| TC-06 | ☐ | |
| TC-07 | ☐ | |
| TC-08 | ☐ | |
| TC-09 | ☐ | |
| TC-10 | ☐ | |
| TC-11 | ☐ | |
| TC-12 | ☐ | |
| TC-13 | ☐ | |
| TC-14 | ☐ | |

**验收结论：** ☐ 通过 / ☐ 有条件通过 / ☐ 不通过

**验收人：** _______________  **日期：** _______________
