# 学生报销管家 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 纯本地票据归档与报销汇总工具:上传 → 分类归档 → 筛选勾选 → 生成 .docx/CSV 汇总单。

**Architecture:** 核心逻辑在 `core/`(workspace/db/models/ocr/classifier/archiver/duplicate/report_*),Web 层用 `http.server` 薄封装只做路由与 JSON,前端原生三件套。SQLite 只做索引,原图始终可在文件系统直寻。

**Tech Stack:** Python 3.11+ 标准库;第三方仅 python-docx;SQLite(sqlite3);unittest。

**Spec:** `docs/superpowers/specs/2026-11-18-baoxiao-guanjia-design.md`

## Global Constraints

- Python 3.11+;默认第三方依赖仅 python-docx(requirements.txt 只写它)。
- 页脚句逐字固定:"由学生报销管家本地生成,数据未离开本机"。
- 默认监听 127.0.0.1:8765;`--lan` 才监听 0.0.0.0 并启用访问码。
- 类别枚举固定:`高铁/铁路 机票 酒店住宿 网约车 出租车/客运 餐饮 其他` + `unknown`。
- 状态:`pending | confirmed`。
- 归档路径:`invoices/YYYY-MM/类别/YYYYMMDD_商户_金额_id.ext`。
- 测试命令:`python -m unittest discover -s tests -v`(Windows,powershell)。
- 界面与文档中文;代码注释中文;commit 中文。
- 删除=移入 `.trash/` + 删索引,不物理删除。

## Review Focus

1. 多种日期写法(`2026-11-18`、`2026/11/18`、`2026年11月18日`)→ 均归一化 `YYYY-MM-DD` → Task 3 测试。
2. 千分位金额(`1,234.50元`)→ 解析为 1234.50 → Task 3 测试。
3. 商户名含 Windows 非法字符(`北京/上海?酒店`)→ 归档文件名安全化 → Task 4 测试。
4. 同一文件重复上传 → 哈希命中,标记重复而非报错 → Task 6 测试。
5. 空选择生成汇总单 → 明确拒绝(count=0 报错)→ Task 9 测试。

---

## M1:后端地基

### Task 1: models.py + workspace.py

**Files:**
- Create: `core/__init__.py`(空)、`core/models.py`、`core/workspace.py`
- Test: `tests/test_models.py`、`tests/test_workspace.py`

**Interfaces (Produces):**
- `core/models.py`:`CATEGORIES: list[str]`(7 类)、`CATEGORY_UNKNOWN = "unknown"`、`STATUS_PENDING = "pending"`、`STATUS_CONFIRMED = "confirmed"`、`@dataclass Invoice`(字段=spec 表结构,`id: int | None = None`,`created_at: str = ""`)、`Invoice.from_row(dict) -> Invoice`、`Invoice.to_dict() -> dict`(给 JSON 用,日期字段空值转 `""`)。
- `core/workspace.py`:`Workspace(root: Path)`、`.ensure()` 创建 `invoices/ uploads/ .trash/ logs/ exports/`、`.db_path/.invoices_dir/.uploads_dir/.trash_dir/.logs_dir/.exports_dir`、`.log_action(action: str, **meta)` 用 logging 写 `logs/app.log` 一行 JSON(动作+元数据,不含全文)。

- [ ] Step 1: 写失败测试 —— `test_models.py`:构造 Invoice 默认 status/dup_flag 正确;from_row/to_dict 往返字段一致。`test_workspace.py`:tmp 目录 ensure() 后五个子目录存在;log_action 后 app.log 存在且含 action 名。
- [ ] Step 2: 跑测试确认失败(模块不存在)。
- [ ] Step 3: 实现两个模块。
- [ ] Step 4: 跑测试通过。
- [ ] Step 5: `git add -A; git commit -m "feat(M1): 数据模型与工作区"`

### Task 2: db.py

**Files:**
- Create: `core/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `models.Invoice`。
- Produces: `Database(path: str)`;`.init_schema()`(spec 的两张表);`.insert_invoice(inv: Invoice) -> Invoice`(填 id、created_at);`.get_invoice(id) -> Invoice | None`;`.update_invoice(inv)`;`.delete_invoice(id)`(仅删索引);`.list_invoices(status=None, category=None, date_from=None, date_to=None, q=None) -> list[Invoice]`(q 模糊匹配 merchant/invoice_no/note,大小写不敏感;date_from/to 含端点);`.invoices_by_ids(ids: list[int]) -> list[Invoice]`(按传入顺序);`.get_setting(key, default=None) / .set_setting(key, value)`;连接用 `check_same_thread=False` + 每方法内短事务,`sqlite3.Row` 转 dict。

- [ ] Step 1: 失败测试 —— 插入/读取往返;按 status、category、date_from+date_to(含端点)、q 过滤;update 后再读一致;delete 后 get 为 None;settings 读写。
- [ ] Step 2: 确认失败。
- [ ] Step 3: 实现 db.py。
- [ ] Step 4: 通过。
- [ ] Step 5: commit `feat(M1): SQLite 数据层`

### Task 3: ocr.py + classifier.py

**Files:**
- Create: `core/ocr.py`、`core/classifier.py`
- Test: `tests/test_ocr.py`、`tests/test_classifier.py`

**Interfaces:**
- Produces `core/ocr.py`:`class OcrEngine(ABC): extract(image_path: str) -> str`;`NoopOcr().extract() == ""`;`CliOcr(cmd_template: str)`,模板中 `{image}` 占位,`subprocess.run` 超时 30s,任何异常/非零退出返回 `""`。
- Produces `core/classifier.py`:`classify(text: str) -> tuple[str, float]`(按优先级匹配关键词组:网约车→出租车/客运→酒店住宿→机票→高铁/铁路→餐饮;命中返回 `(类别, 0.7)`,无 `(unknown, 0.0)`);`extract_fields(text: str) -> dict`(键 `amount: float|None, date: str|None, invoice_no: str|None`;金额含千分位;日期三格式归一化;发票号 `发票号码|发票号|号码[:：]?\s*(\d{8,20})`)。
- Consumes: `models.CATEGORIES`。

- [ ] Step 1: 失败测试 —— NoopOcr 空;CliOcr 用 `cmd /c echo hello`(win)返回含 hello,用 `cmd /c exit 1` 返回 "";classify 七类样例文本各归对、无关文本 unknown;extract_fields:`"价税合计:¥1,234.50 开票日期:2026年11月18日 发票号码:042001900111"` → amount 1234.5、date "2026-11-18"、invoice_no 该串;`2026/11/18` 与 `2026-11-18` 归一;无字段文本全 None。
- [ ] Step 2: 确认失败。
- [ ] Step 3: 实现。
- [ ] Step 4: 通过。
- [ ] Step 5: commit `feat(M1): OCR 适配器与关键词分类器`

### Task 4: archiver.py + duplicate.py

**Files:**
- Create: `core/archiver.py`、`core/duplicate.py`
- Test: `tests/test_archiver.py`、`tests/test_duplicate.py`

**Interfaces:**
- Consumes: `models.Invoice`、`workspace.Workspace`、`db.Database`。
- Produces `core/archiver.py`:`sanitize_filename(name: str, maxlen: int = 30) -> str`(去 `\/:*?"<>|` 与空白折叠、空给 `未命名`);`archive_path(ws: Workspace, inv: Invoice) -> Path`(日期缺省用 created_at 的日期,金额缺省 `0`,商户缺省 `未命名`);`archive(ws, inv, db) -> Path`(把 `original_path` 或旧 `archived_path` 的文件 shutil.move 到新路径,写回 `inv.archived_path` 并 update;目标已存在追加 `_1/_2`);`to_trash(ws, inv, db) -> Path`(移 `.trash/YYYYMMDD_HHMMSS_id_原名`,清空 archived_path)。
- Produces `core/duplicate.py`:`normalize(s: str) -> str`;`find_dup_of(db, inv) -> int | None`(顺序:file_hash 相同 → invoice_no 非空相同 → date+amount+merchant 归一化全同;排除自身;均已确认/待确认均参与)。

- [ ] Step 1: 失败测试 —— 路径规则含中文类别目录;`北京/上海?酒店` 安全化;archive 移动后原位置无文件、DB archived_path 更新;改类别再 archive → 新目录且旧文件消失;to_trash 后文件在 .trash 且带时间戳前缀;duplicate 三层各命中一次、无字段时 None。
- [ ] Step 2: 确认失败。
- [ ] Step 3: 实现。
- [ ] Step 4: 通过。
- [ ] Step 5: commit `feat(M1): 归档器与重复检测`,M1 完成,跑全量测试。

## M2:Web 工作台

### Task 5: web/server.py 核心(路由/静态/JSON/multipart)

**Files:**
- Create: `web/__init__.py`、`web/server.py`、`web/static/index.html`(占位)、`web/static/style.css`、`web/static/app.js`(占位)
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: Task 1–4 全部。
- Produces: `make_server(ws: Workspace, db: Database, host: str, port: int, access_code: str | None = None) -> ThreadingHTTPServer`;内部 `AppHandler(BaseHTTPRequestHandler)`:GET `/`与`/static/*` 静态文件(按扩展名给 Content-Type);`GET /api/invoices`(透传 list_invoices 筛选参数);`GET /image/{id}` 返回归档原图;POST JSON 读取 helper `read_json(handler) -> dict`;multipart 解析函数 `parse_multipart(body: bytes, content_type: str) -> list[tuple[str, str, bytes]]`(字段名、文件名、内容;用 email.parser,自实现因 Python 3.13 已移除 cgi);JSON 响应 helper。

- [ ] Step 1: 失败测试 —— 启动线程内 server(127.0.0.1, 随机端口),urllib 请求 `/` 得 200 与 HTML;`/api/invoices` 空 JSON 列表;`/image/999` 404;parse_multipart 对手工构造体解析出文件名与字节。
- [ ] Step 2: 确认失败。
- [ ] Step 3: 实现。
- [ ] Step 4: 通过。
- [ ] Step 5: commit `feat(M2): Web 服务器核心`

### Task 6: 上传与自动分类管线

**Files:**
- Modify: `web/server.py`
- Test: `tests/test_upload.py`

**Interfaces:**
- Consumes: `ocr`、`classifier`、`duplicate.find_dup_of`、`archiver.archive`。
- Produces: `POST /api/upload`:multipart 字段 `files`(多图)+ 可选 `category`;每张:校验扩展 jpg/jpeg/png/webp、存 `uploads/原文件名_id.ext`、算 SHA-256、建 pending 记录、跑 OCR+classify(有 category 参数则优先用户选择,置信 0.9)、extract_fields 预填、`find_dup_of` 命中则 dup_flag=1/dup_of;置信 ≥0.7 且有日期或金额 → 自动 confirmed 并 archive,否则 pending 留 uploads;返回新记录列表;全程 `ws.log_action("upload", ...)`。非图片字段/空文件跳过不报错。

- [ ] Step 1: 失败测试 —— 构造含最小合法 PNG 的 multipart 上传 3 张不同图 → 3 条 pending(NoopOcr);上传带 category → 该类别;同一 PNG 二次上传 → 第二条 dup_flag=1 且 dup_of=第一条 id;含文本字段与空文件部件的请求不崩、只入库图片。
- [ ] Step 2: 确认失败。
- [ ] Step 3: 实现。
- [ ] Step 4: 通过。
- [ ] Step 5: commit `feat(M2): 上传与自动分类`

### Task 7: 票据库 CRUD API

**Files:**
- Modify: `web/server.py`
- Test: `tests/test_api_invoices.py`

**Interfaces:**
- Produces:`PUT /api/invoices/{id}`(JSON 体=可变字段;status 变 confirmed 时自动 `archive`;已 confirmed 改 category/日期/商户后重归档);`DELETE /api/invoices/{id}`(`to_trash` + 删索引);`POST /api/invoices/{id}/force-keep`(dup_flag=0, dup_of=None);所有动作 log_action;404 处理。

- [ ] Step 1: 失败测试 —— PUT 确认后文件在 invoices/ 正确路径;改商户后重归档旧文件消失;DELETE 后 DB 无记录且原图在 .trash;force-keep 清标记。
- [ ] Step 2–5: 同前,commit `feat(M2): 票据库 API`

### Task 8: 前端页面 + LAN 访问码 + app.py 入口

**Files:**
- Create: `app.py`;重写 `web/static/index.html、style.css、app.js`
- Test: `tests/test_lan.py`

**Interfaces:**
- Produces:`app.py`:`python app.py [--workspace 路径] [--port 8765] [--lan]`;无工作区时在当前目录建 `报销管家工作区/`;--lan 生成 `secrets` 6 位数字码,打印本机 IP 与码。server:非 127.0.0.1 请求需 `X-Access-Code` 头或 `?code=` 匹配,否则 401;`GET /api/access-info` 返回是否需要码。前端:四入口 tab(上传/待确认、票据库、生成汇总单、设置);上传含类别下拉;待确认列表每条"修正/确认";票据库筛选+勾选+编辑+删除+强制保留;设置页存默认报销人;手机可用(视口、大按钮);文案短。
- 前端逻辑以手动演示验收;API 层用测试钉住。

- [ ] Step 1: 失败测试 —— 无码 401:构造 handler 层 `client_ip != 127.0.0.1` 的请求(直接函数级测 `_check_access(handler)` 或以非本机头模拟);有码 200;/api/access-info 正确。
- [ ] Step 2: 确认失败。
- [ ] Step 3: 实现 server 访问码 + app.py + 三件套前端。
- [ ] Step 4: 通过 + 全量回归;commit `feat(M2): 前端工作台与局域网访问码`,M2 完成。

## M3:报销汇总单

### Task 9: report_docx.py

**Files:**
- Create: `core/report_docx.py`
- Test: `tests/test_report_docx.py`

**Interfaces:**
- Consumes: `models.Invoice`、`Workspace`。
- Produces:`generate(ws: Workspace, invoices: list[Invoice], meta: dict) -> Path`;meta 键:`name, student_id, project, date_from, date_to, reason`;空列表 raise `ValueError("未选择票据")`;文档:标题"报销汇总单"、信息段(报销人/学号/项目/出差起止/事由/附件张数)、明细表(序号|日期|类别|事由/行程|金额(元)|票据编号|备注)、合计行(`Decimal` 求和两位小数)、节页脚居中含固定句"由学生报销管家本地生成,数据未离开本机";输出 `exports/报销汇总单_{name}_{date_from}-{date_to}.docx`;金额列右对齐。

- [ ] Step 1: 失败测试 —— 3 张票(含 1234.5 + 88.00 + 0.01)生成文件存在;用 `Document()` 重开:表头行文本正确、数据 3 行、合计行 1322.51、页脚含固定句;空列表 raise ValueError。
- [ ] Step 2: 确认失败。
- [ ] Step 3: 实现(python-docx,克制排版:黑体/宋体常规字号,表格 Table Grid)。
- [ ] Step 4: 通过。
- [ ] Step 5: commit `feat(M3): docx 汇总单`

### Task 10: report_csv.py + preview/settings + 汇总单页

**Files:**
- Create: `core/report_csv.py`;Modify: `web/server.py`、`web/static/app.js`
- Test: `tests/test_report_csv.py`、`tests/test_report_api.py`

**Interfaces:**
- Produces:`generate_csv(ws, invoices) -> Path`(utf-8-sig;表头与 docx 明细列一致 + 合计行);`POST /api/report/preview` `{ids, meta?}` → `{count, total, items}`;`POST /api/report/docx` `{ids, meta}` → `{path, filename}`(meta 缺失用 settings 默认);`POST /api/report/csv`;`GET/PUT /api/settings`(键 `default_name/default_student_id/default_project`)。前端汇总单页:勾选带入 → 填 meta(预填默认)→ 预览合计 → 生成 docx/csv → 下载。

- [ ] Step 1: 失败测试 —— csv 文件内容行数与表头、Excel 可读(utf-8-sig BOM 首字节 `\xef\xbb\xbf`);preview 传 3 id 返回 count=3 与 Decimal 字符串合计;docx 端点返回的文件存在;settings PUT 后 GET 一致。
- [ ] Step 2–5: 实现、通过、全量回归,commit `feat(M3): CSV 与汇总 API`,M3 完成。

## M4:收尾

### Task 11: README + 示例工作区 + 验收

**Files:**
- Create: `README.md`、`tools/make_samples.py`、`samples/`(生成物)
- Test: 全量回归 + 手动验收清单

**Interfaces:**
- `tools/make_samples.py`:纯 stdlib 生成 3 张最小 PNG(文件名含 12306/酒店/滴滴字样)→ 建示例工作区 `samples/demo_workspace/` → 走上传/确认/归档流程 → 生成 `samples/报销汇总单_示例_20261101-20261118.docx`。README:启动方式、工作区目录说明、手机上传步骤、备份(整目录复制)、已知限制(OCR 需自配、无模糊去重、单机单用户)。

- [ ] Step 1: 跑 make_samples.py 生成示例工作区与示例汇总单,人工打开 docx 核对。
- [  ] Step 2: README 完成。
- [ ] Step 3: `python -m unittest discover -s tests -v` 全绿。
- [ ] Step 4: 按 spec 验收标准 1–7 逐项核对并在最终回复给出演示步骤。
- [ ] Step 5: commit `docs: README 与示例`,声明:P0 已完成,项目收尾,不欠维护。
