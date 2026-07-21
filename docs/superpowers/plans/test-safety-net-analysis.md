# VideoSplitter 自动化测试防护网评估报告

**日期**: 2026-07-14
**评估人**: Sisyphus (AI Agent)
**测试框架**: pytest 9.0.3

---

## 一、总体概况

| 维度 | 数据 |
|------|------|
| 测试文件数 | 8 + 1 conftest |
| 测试函数数 | 111 |
| 测试代码量 | ~1,550 行 |
| 代码覆盖率 | 39%（按语句行） |
| 测试通过率 | 111/111 ✅ |
| CI/CD | 无 |
| pytest 配置 | 无（无 pytest.ini / pyproject.toml [tool.pytest] / setup.cfg / .coveragerc） |

## 二、测试质量评级（按模块）

| 测试文件 | 评级 | 亮点 | 关键问题 |
|----------|------|------|----------|
| `tests/test_transcribe_funasr.py` | A | 引擎 mock 最完善，`__import__` 级 ImportError 测试，Factory 全路径覆盖 | — |
| `tests/test_review_controller.py` | A- | 导航状态机全覆盖，进度持久化，SRT 导出 | 1 处过度 mock（4 patches，1 个未使用） |
| `video_splitter/tests/test_review.py` | A- | 最佳文件隔离（tmp_path），损坏文件优雅处理，5 场景集成测试 | — |
| `tests/test_workers.py` | B+ | 3 条信号路径全覆盖 | 同步调用，未测试 QThread 契约 |
| `video_splitter/tests/test_validator.py` | B | 合并/拆分边界测试扎实 | 硬编码路径，无 fixture |
| `video_splitter/tests/test_chapter.py` | B | 时间戳解析覆盖多种格式 | 硬编码路径，LLM detect() 0% 覆盖 |
| `video_splitter/tests/test_transcribe.py` | B | SRT 格式 + Token 估算 | 硬编码路径，断言过松 |
| `ffmpeg-skill/tests.py` | C+ | 参数校验层测试完善 | 无真实 FFmpeg 执行路径测试 |
| `tests/conftest.py` | C+ | sys.path 注入 | `_load_gui_module()` 死代码 |

## 三、覆盖率缺口（按优先级）

### 🔴 高危 — 0% 覆盖的核心模块

| 模块 | 行数 | 覆盖 | 风险说明 |
|------|------|------|----------|
| `video_splitter/pipeline.py` | 90 | 0% | 全流程编排器，损坏则一切崩溃 |
| `video_splitter/cli.py` | 195 | 0% | 7 个子命令，用户的主要入口 |
| `video_splitter/splitter/cutter.py` | 55 | 0% | 最终输出——实际切割视频 |
| `video_splitter/extractor/audio.py` | 66 | 0% | 流水线第一阶段，失败 = 下游全灭 |
| `ffmpeg-skill/__init__.py` | 204 | 0% | `_run_command()` 执行路径完全未测试 |

### 🟡 中危 — GUI 组件 0% 覆盖

| 模块 | 行数 | 覆盖 | 风险说明 |
|------|------|------|----------|
| `gui/app.py` | 180 | 0% | MainWindow + QApplication 入口 |
| `gui/widgets/video_player.py` | 53 | 0% | 核心视频播放 widget |
| `gui/widgets/subtitle_panel.py` | 86 | 0% | 主字幕显示/编辑 widget |
| `gui/widgets/status_bar.py` | 15 | 0% | 简单状态栏 |

### 🟠 部分覆盖但关键逻辑遗漏

| 模块 | 覆盖 | 缺失 |
|------|------|------|
| `video_splitter/analyzer/chapter.py` | 31% | `ChapterDetector.detect()`（LLM 调用路径）完全未测试 |
| `video_splitter/config.py` | 67% | `from_env()` 方法未测试 |
| `video_splitter/review.py` | 82% | 交互式命令处理未覆盖 |
| `gui/controllers/review_controller.py` | 92% | `save_correction` 和 `export_srt` 的异常路径未覆盖 |

## 四、结构性缺陷

### 致命问题

3 个核心测试文件硬编码了已不存在的 worktree 路径：
- `video_splitter/tests/test_chapter.py:6`
- `video_splitter/tests/test_validator.py:5`
- `video_splitter/tests/test_transcribe.py:5`

```python
sys.path.insert(0, r'E:\Private\skill开发\.worktrees\sprint\sprint-2026-06-02-01')
```

### 工程基础设施缺失

- 无 CI/CD
- 无 pytest 配置
- 无 coverage 配置
- `video_splitter/tests/` 使用 `importlib` 动态导入，绕过静态分析
- 无 `@pytest.fixture` 使用，大量重复 setup

## 五、改进项清单

### 第一优先：修复现有测试（16 项改进点）

1. 移除 `test_chapter.py` 硬编码路径，改用计算项目根
2. 移除 `test_validator.py` 硬编码路径，改用计算项目根
3. 移除 `test_transcribe.py` 硬编码路径，改用计算项目根
4. `test_chapter.py` 改为正常 `import`（不再用 `importlib`）
5. `test_validator.py` 改为正常 `import`（不再用 `importlib`）
6. `test_transcribe.py` 改为正常 `import`（不再用 `importlib`）
7. `test_chapter.py` 引入 `@pytest.fixture` 消除重复 setup
8. `test_validator.py` 引入 `@pytest.fixture` 消除重复 setup
9. 删除 `conftest.py` 中 `_load_gui_module()` 死代码
10. 增强 `test_chapter.py`：测试 `ChapterDetector.detect()`（mock LLM 调用）
11. 增强 `test_chapter.py`：测试 `config.from_env()` 方法
12. 增强 `test_review_controller.py`：覆盖 `save_correction` 异常路径
13. 增强 `test_review_controller.py`：覆盖 `export_srt` 异常路径
14. 增强 `test_workers.py`：增加 QThread + `moveToThread` 集成测试
15. 修复 `test_review_controller.py` 过度 mock（移除 `test_loads_segments_and_emits_progress` 中未使用的 `builtins.open` patch）
16. GUI widget 冒烟测试（实例化不崩溃，信号连接正确）

### 第二优先：补齐关键模块测试（4 个新测试模块）

17. 新建 `video_splitter/tests/test_pipeline.py`：全流程编排测试
18. 新建 `video_splitter/tests/test_audio.py`：音频提取测试
19. 新建 `video_splitter/tests/test_cli.py`：7 个子命令测试
20. 新建 `video_splitter/tests/test_cutter.py`：视频切割测试

### 第三优先：工程化

21. 创建 `pyproject.toml` 的 `[tool.pytest.ini_options]`
22. 创建 `.coveragerc` 或 `[tool.coverage]` 配置
23. 创建 `.github/workflows/test.yml` CI 配置
24. ffmpeg-skill 补充真实 FFmpeg 执行路径测试

---

**总计：24 项改进**
