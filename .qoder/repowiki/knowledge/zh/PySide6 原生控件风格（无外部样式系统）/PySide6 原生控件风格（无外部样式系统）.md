---
kind: frontend_style
name: PySide6 原生控件风格（无外部样式系统）
slug: frontend_style
category: frontend_style
scope:
    - '**'
---

本仓库的 GUI 部分基于 PySide6 构建，采用**纯代码布局 + 原生控件外观**的方式实现界面，未引入任何 CSS/SCSS/Tailwind 等前端样式体系，也未使用 QSS 样式表或自定义主题引擎。具体表现如下：

1. **样式来源**：所有视觉呈现完全依赖 Qt 平台默认样式（Windows/macOS/Linux 原生主题），通过 `QApplication` 启动后自动继承系统外观。
2. **布局方式**：全部使用 `QVBoxLayout`、`QHBoxLayout`、`QSplitter`、`QTabWidget` 等容器在 Python 中声明式组合，没有独立的样式文件；字号、边距、颜色等均由各 Widget 构造函数内硬编码设置（如 `setFixedWidth(40)`、`setMinimumHeight(80)`、`addSpacing(8)`）。
3. **组件组织**：`gui/widgets/` 下每个 UI 片段封装为独立 `QWidget` 子类（`VideoPlayerWidget`、`SubtitlePanel`、`StatusBarWidget`），由 `gui/app.py` 中的 `MainWindow` 组装，遵循“一个类 = 一个可复用面板”的约定。
4. **交互与状态**：通过 PySide6 信号槽机制连接事件（如 `position_changed.connect(...)`、`textChanged.connect(...)`），未引入 MVVM 或响应式框架。
5. **国际化与文案**：按钮文本、占位符、提示语直接以中文硬编码在源码中（如 `"保存并继续 \u25b6"`、`"输入修正..."`），未见 i18n 资源文件或翻译键值表。

由于本项目是桌面端工具而非 Web 前端，不存在传统意义上的“前端样式系统”，因此该类别在本仓库中属于**不适用**场景。若未来需要统一外观，可在 `app.py` 入口处通过 `QApplication.setStyleSheet()` 注入全局 QSS 或使用 `QPalette` 定制调色板，目前尚无此类基础设施。