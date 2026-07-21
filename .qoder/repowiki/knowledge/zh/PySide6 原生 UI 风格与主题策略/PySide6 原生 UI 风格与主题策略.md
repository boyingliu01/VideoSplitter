---
kind: frontend_style
name: PySide6 原生 UI 风格与主题策略
category: frontend_style
scope:
    - '**'
source_files:
    - gui/app.py
    - gui/widgets/split_panel.py
    - gui/widgets/subtitle_panel.py
    - gui/widgets/timeline.py
    - video_splitter/splitter/subtitle_burner.py
---

本项目的桌面端采用 PySide6（Qt for Python）构建，未引入任何 CSS/SCSS/Tailwind 等 Web 样式体系，而是完全基于 Qt 原生控件与自定义绘制实现界面。整体风格遵循轻量、功能优先的桌面工具范式：默认系统主题加少量硬编码配色常量，无全局 QSS 样式表、无深色模式切换、无设计令牌集中管理。

### 1. 使用的系统与框架
- UI 框架：PySide6.QtWidgets + PySide6.QtGui（QPainter 自绘）
- 布局方式：纯代码式 QVBoxLayout / QHBoxLayout / QSplitter 组合，无 .ui 文件
- 绘图方式：TimelineWidget 通过重写 paintEvent 使用 QPainter 绘制时间轴、章节色块、拖拽预览线；其余控件全部使用标准 Qt Widget
- 字体字号：统一使用 QFont.setPointSize(7~9) 的小字号，符合视频编辑类工具的紧凑信息密度需求
- 图标文字按钮：使用 Unicode 符号替代图标资源，避免额外资源依赖

### 2. 关键文件与位置
- gui/app.py：MainWindow 入口，负责菜单、中央 Splitter、信号连接与工作线程生命周期
- gui/widgets/split_panel.py：Split 标签页容器，编排 ChapterList + Timeline + 操作按钮
- gui/widgets/subtitle_panel.py：Review 标签页，原文修正区 + 导航按钮
- gui/widgets/timeline.py：自绘时间轴，定义章节颜色调色板 _CHAPTER_COLORS、最小章节时长 _MIN_CHAPTER_SECONDS、边距常量等视觉参数
- gui/widgets/chapter_list.py、gui/widgets/video_player.py、gui/widgets/status_bar.py：辅助组件
- video_splitter/splitter/subtitle_burner.py：FFmpeg 字幕硬烧入时通过 -vf subtitles=...:force_style='FontSize=24,PrimaryColour=&HFFFFFF,...' 指定渲染样式

### 3. 架构与约定
- 无全局样式表：未在 QApplication 级别调用 setStyleSheet/QPalette，也未加载任何 .qss 文件；所有颜色、字号、边距以模块级常量或构造函数内联形式存在
- 颜色来源：TimelineWidget 内部 _CHAPTER_COLORS 列表为唯一集中配色源，按章节索引循环取色；其余 UI 直接引用 QColor 字面量（如深灰背景 QColor(220,220,220)、红色播放指示 QColor(220,50,50)）
- 布局约束：通过 setMinimumHeight / setFixedWidth 控制组件尺寸，配合 QSplitter 的 stretchFactor 分配空间比例（主窗口 6:4，SplitPanel 内容 7:3）
- 状态反馈：通过 QPushButton.setEnabled(False)/True 与 setText(Detecting...) 切换文案表达运行态，而非进度条或动画
- 国际化：按钮文本与提示均为中文（上一段、保存并继续、跳到...），未使用 Qt 翻译机制

### 4. 开发者应遵循的规则
- 新增控件：优先使用标准 Qt Widget + 布局管理器，仅在需要数据可视化（如图表、波形、时间轴）时才重写 paintEvent
- 颜色管理：若需新增全局颜色，应在对应 widget 模块顶部以模块级常量声明，避免在方法体内散落 QColor 字面量
- 字号规范：正文使用 8pt，标题标签使用 9pt，时间戳等辅助信息使用 7pt，保持与现有 Timeline 一致
- 交互反馈：禁用态用 setEnabled(False)，进行中用 setText 追加 ... 后缀，错误用 QMessageBox.warning 弹窗，不自行实现 Toast
- 响应式适配：不追求多分辨率自适应，固定最小高度并通过 QSplitter 拉伸填充；如需新增全屏缩放逻辑，应在 MainWindow 层统一处理
- 字幕渲染样式：FFmpeg 硬烧入的字幕样式集中在 subtitle_burner.py 的 force_style 字符串中，修改时需同步更新字号、描边、边距等参数