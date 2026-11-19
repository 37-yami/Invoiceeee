# GUI 升级 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 tkinter 桌面 GUI 替换 Web 层:多文件/文件夹导入、RapidOCR 自动归纳、删除 web/,README 中英双语。

**Architecture:** core/ 全复用;新 gui/ 三模块(importer 无头管线 + 主窗口 + 对话框);core/ocr.py 增 RapidOcr 与 make_engine 探测;导入/OCR 后台线程 + queue + after() 刷新。

**Tech Stack:** tkinter/ttk(标准库);rapidocr-onnxruntime(可选依赖);其余同原项目。

**Spec:** `docs/superpowers/specs/2026-11-19-gui-upgrade-design.md`

## Global Constraints

- 接受图片格式:`.jpg .jpeg .png .webp .bmp .tif .tiff .gif`(扩展名判断;HEIC 暂不支持,列入已知限制)。
- 依赖放宽(用户已确认):python-docx(docx 生成,保留)、rapidocr-onnxruntime(可选 OCR,未装不阻塞)、Pillow(GUI 嵌入式图片预览)、tkinterdnd2(可选拖拽导入,未装优雅回退)。
- OCR 优先级:ocr_cmd 设置 > RapidOCR(可导入)> NoopOcr;任何 OCR 异常返回 ""。
- 归档/重复/汇总规则与原 spec 完全一致;data.db 向后兼容。
- 界面中文;代码注释中文;commit 中文;测试命令 `python -m unittest discover -s tests -v`。
- GUI 交互手动验收;可测逻辑(importer/engine)必须 unittest。

## Review Focus

1. 文件夹递归导入含非图片/子目录 → 只入库合法图片且不重复 — T2 测试。
2. RapidOCR 未安装时导入流程零报错(Noop 回退)— T2 测试。
3. OCR 文本与文件名同时含冲突类别关键词 → 按 OCR 文本优先归类 — T2 测试(extract 用 OCR 文本,分类按 classifier 优先级)。
4. 导入中用户再点导入(并发)→ 不崩、不重复入库(线程串行化)— T4 GUI 手动 + importer 侧 queue 串行设计。
5. 大文件夹(如 200 张)导入 → UI 不冻结、可继续操作 — T4 手动验收(后台线程)。

---

### Task 1: 文档与依赖准备

**Files:** spec(已写)、本计划、requirements.txt
- [ ] requirements.txt 增 rapidocr-onnxruntime;pip 安装;commit spec+plan。

### Task 2: RapidOcr 适配器 + make_engine + importer 无头管线

**Files:**
- Create: `gui/__init__.py`、`gui/importer.py`;Modify: `core/ocr.py`、`tests/test_ocr.py`
- Test: `tests/test_importer.py`

**Interfaces (Produces):**
- `core/ocr.py`:`class RapidOcr(OcrEngine)`(延迟导入 rapidocr_onnxruntime.RapidOCR,extract 拼接识别文本,异常→"");`make_engine(db) -> OcrEngine`(优先级:ocr_cmd 设置 > RapidOCR 可导入 > NoopOcr)。
- `gui/importer.py`:`class Importer(ws, db, engine=None)`(engine 缺省 make_engine(db),可注入);`.import_files(paths: list[Path]) -> list[Invoice]`(管线:校验→哈希→uploads 暂存→OCR+classify→extract_fields→find_dup→类别已知归档、字段齐全自动 confirmed);`.scan_folder(folder: Path) -> list[Path]`(递归收集图片、按绝对路径去重、排序);`.reimport_unknown()`(对 unknown 且 pending 的记录重跑识别)。

- [ ] Step 1: 失败测试 —— test_ocr:make_engine 无设置无 rapidocr 环境注入返回 Noop(用 monkeypatch 移除模块)、有 ocr_cmd 返回 CliOcr;test_importer:3 张图 pending 留 uploads;文件名 12306 → 高铁/铁路 且归档;假 OCR 引擎返回发票文本(含"酒店 住宿 ¥358.00 开票日期:2026-11-02 发票号码:042001900111")→ confirmed + 金额日期发票号入库 + 归档;同内容二次导入 dup_flag=1;非图片/空文件跳过;scan_folder 递归+去重+仅图片。
- [ ] Step 2: 确认失败。
- [ ] Step 3: 实现 RapidOcr/make_engine/Importer(管线逻辑自 web/server.py 平移)。
- [ ] Step 4: 通过 + 全量。
- [ ] Step 5: commit `feat(G1): RapidOCR 适配与导入管线`

### Task 3: 删除 web 层 + app.py 改 GUI 入口

**Files:**
- Delete: `web/`、`tests/test_server.py、test_upload.py、test_api_invoices.py、test_report_api.py、test_lan.py、test_security.py`
- Modify: `app.py`(argparse --workspace,启动 gui)
- Test: 全量回归(管线覆盖已由 T2 接管)

**Interfaces (Produces):** `python app.py [--workspace 路径]` 启动 GUI;无 web 依赖。

- [ ] Step 1: git rm web 与六个 web 测试;app.py 重写为 GUI 启动(暂引用 gui.main_window,占位可导入)。
- [ ] Step 2: 全量测试绿(importer 测试独立于 web)。
- [ ] Step 3: commit `feat(G1): 删除 Web 层,app.py 改 GUI 入口`

### Task 4: gui/main_window.py 主窗口

**Files:**
- Create: `gui/main_window.py`;Modify: `gui/importer.py`(如需回调)
- Test: 手动演示清单(无头测试不适用 UI)

**Interfaces (Produces):**
- `class App(tk.Tk)`;`launch(args)` 供 app.py 调用;工作区记忆 `~/.student_invoice_gui.json`;工具栏(添加图片/导入文件夹/刷新);筛选行(状态/类别/起止/搜索);Treeview 多选为勾选集;编辑面板(嵌入缩略图预览(Pillow,加载失败回退为"打开原图"按钮)+ 类别/金额/日期/商户/发票号/备注 + 打开原图/确认归档/保存/删除/强制保留);状态栏(已选合计 + 生成汇总单/导出CSV 按钮);导入后台线程 + queue + after(200);拖拽导入(tkinterdnd2 可导入则启用,未装不影响)。

- [ ] Step 1: 实现主窗口(布局与行为按 spec GUI 规格)。
- [ ] Step 2: 手动验收清单:导入 3 张示例图 → 列表刷新;筛选;编辑确认归档;重复提示+强制保留;删除入 .trash;勾选合计正确;打开原图调系统看图。
- [ ] Step 3: commit `feat(G2): tkinter 主窗口`

### Task 5: 汇总单与设置对话框

**Files:**
- Create: `gui/report_dialog.py`、`gui/settings_dialog.py`;Modify: `gui/main_window.py`(入口按钮)

**Interfaces (Produces):**
- `ReportDialog(parent, ws, db, invoices)`:meta 表单预填默认 → 预览张数合计 → 生成 docx(文件写入 exports/,弹窗提示路径并 os.startfile 打开目录);导出 CSV 同参数。
- `SettingsDialog(parent, db)`:默认报销人/学号/项目/OCR 命令,保存到 settings。

- [ ] Step 1: 实现两对话框。
- [ ] Step 2: 手动验收:3 张票生成 docx 打开核对(表格/合计/页脚);CSV;设置保存后预填。
- [ ] Step 3: commit `feat(G2): 汇总单与设置对话框`

### Task 6: README 双语 + 示例更新 + 收尾推送

**Files:**
- Modify: `README.md`(中文主文档 + 顶部 [English](README.en.md));Create: `README.en.md`;`tools/make_samples.py`(如入口变化则调整);`.superpowers` 不入库
- Test: 全量回归 + make_samples 重跑 + 手动冒烟 python app.py

- [ ] Step 1: 两份 README 内容同步(启动/工作区/导入/OCR/备份/限制,GUI 为唯一入口)。
- [ ] Step 2: make_samples 重跑,示例 docx 核对。
- [ ] Step 3: 全量测试绿;python app.py 冒烟;commit `docs(G3): 双语 README 与示例更新`。
- [ ] Step 4: git push origin master;最终汇报。
