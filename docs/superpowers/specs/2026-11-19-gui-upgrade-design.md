# 学生报销管家 GUI 升级 设计文档

日期:2026-11-19
状态:已确认(技术选型与设计概要在对话中逐项批准)
前置:2026-11-18-baoxiao-guanjia-design.md(核心层不变,本文档为界面层替换)

## 目标

1. 去浏览器化:tkinter 桌面 GUI 成为唯一界面,删除 web/ 层。
2. 本地导入:一次选择多个文件,或导入整个文件夹(递归扫描)。
3. 按内容归纳:RapidOCR(可选依赖,安装即自动启用)读取票据文字 → 关键词分类 + 提取金额/日期/发票号;未安装回退文件名规则;识别结果均可人工修正。

## 不变

core/ 的数据结构、归档规则、重复检测、docx/CSV 生成全部复用;已有工作区(data.db)向后兼容;纯本地、零云、克制依赖的气质不变。

## 结构

```
app.py              # GUI 入口:python app.py [--workspace 路径]
gui/main_window.py  # 主窗口(工具栏/筛选/列表/编辑面板/状态栏)
gui/importer.py     # 导入编排(无头可测):多文件+文件夹扫描 → 入库管线
gui/report_dialog.py / gui/settings_dialog.py
core/ocr.py         # + RapidOcr 适配器 + make_engine 自动探测
web/                # 删除
```

## OCR 策略(优先级)

1. 设置里显式配置的 ocr_cmd → CliOcr(用户明确意图)
2. rapidocr_onnxruntime 可导入 → RapidOcr(延迟导入;失败/异常一律返回 "")
3. 都没有 → NoopOcr(文件名规则 + 待确认队列,绝不阻塞)

## 导入管线(importer,与原 web 管线等价)

校验扩展(jpg/jpeg/png/webp)→ 算 SHA-256 → 存 uploads/{id}_{文件名安全化}.ext →
OCR 文本 + 文件名关键词 classify → extract_fields(仅 OCR 文本)→ find_dup_of →
类别已知即归档;置信 ≥0.7 且有金额或日期 → 自动 confirmed,否则 pending。

## GUI 规格

- 单窗口三区:工具栏(添加图片/导入文件夹 + 筛选行)、票据表格(ttk.Treeview:
  状态│重复│类别│日期│商户/行程│金额│发票号,多选即勾选集)、编辑面板
  (字段 Entry + 打开原图/确认归档/保存/删除/强制保留)。
- 状态栏:工作区路径、已选张数与合计、生成汇总单/导出 CSV。
- 原图查看用系统默认看图工具(os.startfile),不嵌 GUI。
- 导入/OCR 在后台线程,经 queue + after() 回主线程刷新,不卡界面。
- 工作区记忆:~/.student_invoice_gui.json 存上次路径;启动顺序 参数 > 记忆 > 弹窗选择。
- 汇总单对话框:报销人信息(预填默认)→ 预览张数合计 → 生成 docx(导出 CSV 同入口)。

## 测试

- importer/RapidOCR/make_engine:unittest 无头测试(OCR 引擎注入假实现钉行为)。
- GUI 外观与交互:手动演示验收(与前端验收方式一致)。
- 删除 web 层及其 HTTP 测试;管线行为(重复/脏文件/自动分类)由 importer 测试接管。

## 文档

README 中英双语,中文为默认:`README.md` 以中文为主、顶部放 [English](README.en.md) 语言链接;`README.en.md` 为对应英文版,内容同步(启动、工作区、导入、OCR、备份、限制)。

## 验收

1. python app.py 打开 GUI(无浏览器);选择多张图片与整个文件夹均可导入。
2. 装 RapidOCR 后,拍照发票自动出类别/金额/日期/发票号;卸载后回退文件名规则仍可用。
3. 确认归档路径规则不变;重复提示与强制保留可用。
4. 勾选生成 docx/CSV,内容与原版一致(合计、页脚)。
5. 全量测试绿;README 更新;推送 GitHub。
