---
kind: frontend_style
name: PySide6 原生样式策略（无 CSS/主题系统）
category: frontend_style
scope:
    - '**'
source_files:
    - gui/app.py
    - gui/widgets/subtitle_panel.py
    - gui/widgets/timeline.py
    - gui/widgets/split_panel.py
---

本仓库的 GUI 基于 PySide6（Qt for Python），采用**纯代码构建 + 硬编码颜色常量**的极简样式方案，未引入任何外部 CSS、QSS 样式表或主题框架。具体特征如下：

1. **布局与控件**：全部通过 `QVBoxLayout` / `QHBoxLayout` / `QSplitter` / `QTabWidget` 在 Python 中声明式组装，没有 `.ui` 文件。
2. **配色方案**：集中在自定义绘制组件内以模块级常量定义，如 `gui/widgets/timeline.py` 中的 `_CHAPTER_COLORS`（8 色循环调色板）、`_BAR_HEIGHT`、`_MARGIN_*` 等；其余控件直接使用 Qt 默认系统主题色，仅个别地方用 `setStyleSheet("color: #666; font-style: italic;")` 做极小范围覆盖（例如 `subtitle_panel.py` 的状态标签）。
3. **无全局主题机制**：未发现 `QApplication.setStyle()`、`QPalette` 替换、dark/light mode 切换逻辑，也未见任何 QSS 文件或样式资源目录。界面外观完全依赖操作系统当前 Qt 风格。
4. **可定制点**：如需统一换肤，应在各 widget 文件中集中提取颜色/尺寸常量到共享模块，并避免散落的 `setStyleSheet` 调用。

结论：该项目不存在跨模块的前端样式体系，所有视觉表现均为“就地硬编码”，不具备设计令牌、主题切换或样式复用能力。