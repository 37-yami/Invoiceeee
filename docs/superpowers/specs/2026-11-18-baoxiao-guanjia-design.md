# 学生报销管家 设计文档

日期:2026-11-18
状态:已经用户确认(聊天中逐节呈现后批准)

## 一句话

纯本地、零云、零账号的票据归档与报销汇总工具:拍照/上传票据 → 自动或半自动分类归档(数据库只做索引,原图可在文件系统直寻)→ 勾选票据一键生成正式 .docx 报销汇总单(+CSV)。

## 背景与用户

研究生、课题组出差人员。出差后手里一堆高铁票、酒店发票、网约车行程单、出租车票、机票图片;希望上传后自动归档、填少量信息、勾选、一键导出。解决在 lab/发票/ 里翻找票据的痛苦。

## 核心流程(MVP)

1. 首次选择本地工作区(如 ~/报销管家/)。
2. 本地 Web 页面上传票据图片;电脑拖拽;手机同一局域网拍照上传(--lan 模式 + 一次性访问码)。
3. 自动识别类型与字段;失败或低置信度 → 待确认队列,人工选类别、修字段。
4. 确认后原图归档到工作区目录,SQLite 建索引。
5. 票据库按日期/类别/项目/金额筛选,勾选。
6. 一键生成 .docx 汇总单(明细表、合计、附件张数、报销人、出差事由、页脚签名句);可导出 CSV。
7. 重复票据检测提示,可强制保留。

## 范围

**P0**(本 spec 覆盖):本地 Web 应用、工作区初始化、上传、数据模型、可插拔 OCR、关键词分类、待确认队列、归档、票据库(筛选/编辑/删除/回收站)、重复检测、docx/CSV 生成、操作日志、基础测试、README。

**P1(不做)**:缩略图预览、批量重命名、项目统计、图表、汇总单嵌图、文件名批量导入、规则配置页、备份按钮。

**明确不做**:用户系统、登录、云同步、协作、审批流、财务对接、移动 App、OCR 训练、机器学习分类、CDN、数据库服务、爬取发票。不引入默认重依赖。

## 技术约束

- Python 3.11+(当前环境 3.13);核心标准库;第三方默认仅 python-docx(1.2.0 已装)。
- SQLite 用 sqlite3;前端原生 HTML/CSS/JS,无 npm/Webpack/React/CDN。
- Web 用 http.server(ThreadingHTTPServer);默认监听 127.0.0.1:8765。
- 所有数据留在工作区;默认不联网。
- 测试用 unittest(标准库,零依赖)。

## 文件树

```
Invoiceeee/
├── app.py                 # 入口:工作区选择、--lan、启动服务
├── requirements.txt       # 仅 python-docx
├── README.md
├── core/
│   ├── __init__.py
│   ├── workspace.py       # 工作区初始化、目录、操作日志(logging 写文件)
│   ├── db.py              # sqlite3 封装:建表、CRUD、筛选查询
│   ├── models.py          # Invoice dataclass、类别枚举、状态枚举
│   ├── ocr.py             # OcrEngine 接口、NoopOcr、CliOcr(外部命令适配)
│   ├── classifier.py      # 关键词/正则分类 + 金额/日期/发票号提取
│   ├── archiver.py        # 归档路径规则、移动、重归档、回收站
│   ├── duplicate.py       # 重复检测(hash/发票号/日期+金额+商户)
│   ├── report_docx.py     # python-docx 汇总单
│   └── report_csv.py      # CSV 导出(utf-8-sig)
├── web/
│   ├── server.py          # 路由、multipart 解析、LAN 访问码校验
│   └── static/            # index.html / style.css / app.js
└── tests/                 # unittest
```

相比最初建议结构仅增 models.py(类别枚举与字段被 5 个模块共用);操作日志并入 workspace.py。

## 数据模型

```sql
CREATE TABLE invoices (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    original_path TEXT NOT NULL,   -- 上传原图路径(uploads/)
    archived_path TEXT,            -- 归档路径(invoices/YYYY-MM/类别/…)
    category      TEXT NOT NULL,   -- unknown | 高铁/铁路 | 机票 | 酒店住宿 | 网约车 | 出租车/客运 | 餐饮 | 其他
    amount        REAL,            -- 元;展示/导出两位小数;合计用 Decimal
    invoice_date  TEXT,            -- YYYY-MM-DD,字典序=日期序
    merchant      TEXT,            -- 商户/行程
    invoice_no    TEXT,            -- 发票号/车票号
    reimburse_by  TEXT,            -- 报销人
    project       TEXT,            -- 项目/课题组
    trip_reason   TEXT,            -- 出差事由
    note          TEXT,            -- 备注
    status        TEXT NOT NULL DEFAULT 'pending',  -- pending | confirmed
    dup_flag      INTEGER NOT NULL DEFAULT 0,
    dup_of        INTEGER,         -- 疑似重复的那张 id
    file_hash     TEXT,            -- SHA-256,上传即算
    created_at    TEXT NOT NULL
);
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
```

## 核心接口

```python
# core/ocr.py
class OcrEngine:
    def extract(self, image_path: str) -> str: ...
class NoopOcr(OcrEngine): ...      # 默认,返回 ""
class CliOcr(OcrEngine): ...       # 读配置命令,subprocess 调用,失败降级 ""

# core/classifier.py
def classify(text: str) -> tuple[str, float]    # (类别, 置信度);无关键词 → (unknown, 0.0)
def extract_fields(text: str) -> dict           # {amount, date, merchant, invoice_no}

# core/archiver.py
def archive_path(inv, workspace_root) -> Path   # invoices/YYYY-MM/类别/YYYYMMDD_商户_金额_id.ext
def archive(inv) -> Path                        # 移动原图;类别/日期/商户变更时重归档
def to_trash(inv) -> None                       # 移入 .trash/,时间戳前缀防覆盖

# core/duplicate.py
def find_dup_of(db, inv) -> int | None          # hash 相同 / 发票号相同 / 日期+金额+商户一致

# core/report_docx.py
def generate(workspace, invoices, meta) -> Path # meta: 姓名/学号/项目/起止日期/事由
```

## Web API

| 方法/路径 | 说明 |
|---|---|
| POST /api/upload | multipart 多图 + 可选类别;返回新记录与重复提示 |
| GET /api/invoices | 筛选:status/category/date_from/date_to/q |
| GET/PUT /api/invoices/{id} | 详情 / 修改(确认后自动重归档) |
| DELETE /api/invoices/{id} | 删索引,原图入回收站 |
| POST /api/invoices/{id}/force-keep | 清除重复标记强制保留 |
| POST /api/report/preview | 汇总预览(合计、张数) |
| POST /api/report/docx | 生成 .docx |
| POST /api/report/csv | 生成 CSV |
| GET/PUT /api/settings | 默认报销人信息 |
| GET /image/{id} | 图片访问 |

LAN 模式:监听 0.0.0.0,生成 6 位一次性访问码(控制台+设置页显示);手机首次访问输入,浏览器保存;本机 127.0.0.1 免验。

## 关键规则

**归档**:`工作区/invoices/YYYY-MM/类别/YYYYMMDD_商户_金额_id.ext`;商户做文件名安全化(去非法字符、限长);原图必须可直接在文件系统找到;数据库只做索引。

**重复判定**(三层,归一化后完全一致,不做模糊匹配):
1. file_hash 相同(同一文件重复上传);
2. invoice_no 相同(非空);
3. invoice_date + amount + merchant 归一化一致。
命中即标 dup_flag=1、dup_of=对方 id,界面提示,允许强制保留。

**删除**:只删索引,原图移 `工作区/.trash/YYYYMMDD_HHMMSS_id_文件名`。

**docx 汇总单**:
- 表头:报销人、学号/工号、项目/课题组、出差起止日期、出差事由、附件张数;
- 表格:序号 | 日期 | 类别 | 事由/行程 | 金额(元) | 票据编号 | 备注;
- 合计行金额自动求和(Decimal);
- 页脚:"由学生报销管家本地生成,数据未离开本机";
- 文件名:`报销汇总单_姓名_起止日期.docx`;风格正式克制可打印,复用 liwu 的 python-docx 经验。

**CSV**:utf-8-sig,字段与汇总单表格一致。

**日志**:`工作区/logs/app.log`,记录上传/归档/修改/删除/生成等动作 + id + 类别等元数据,不含 OCR 全文与敏感内容。

## 错误处理

- OCR 失败/不可用 → 空文本,流程继续,进待确认队列;绝不抛错阻塞。
- 上传非图片或损坏文件 → 拒绝并返回简短错误。
- 归档时目标已存在 → id 保证唯一,冲突时追加短随机后缀。

## 测试策略

unittest,覆盖:归档路径规则、分类关键词与字段提取、金额合计(Decimal)、重复检测三层、日期/类别筛选、docx 与 csv 生成不报错且内容正确。每个里程碑结束跑全量测试。

## 里程碑

| 周 | 交付 | 验证 |
|---|---|---|
| M1 | workspace/models/db/ocr/classifier/archiver/duplicate + 测试 | 单元测试 |
| M2 | web/server、前端、上传、待确认、票据库、重复提示、日志 | 测试 + 手动演示 |
| M3 | report_docx/report_csv、预览、设置页 | 测试 + 端到端演示 |
| M4 | README、示例工作区、示例汇总单、验收核对 | 全量回归 + 验收演示 |

## 验收标准

1. 断网可启动、上传、归档、生成 docx。
2. 高铁票/酒店票/滴滴票各一张:OCR 可用时自动分类;不可用时进待确认,修正后归档正确。
3. 重复上传有提示,可强制保留。
4. 3 张票据生成 docx,表格/合计/页脚正确。
5. 日期范围+类别筛选正确;CSV 字段与汇总单一致。
6. 工作区整目录复制即备份;原图文件系统直寻。
7. 4 周内完成 P0,结束时声明:P0 已完成,项目收尾,不欠维护。

## 已确认的设计决策

1. 金额存 REAL 元,两位小数,合计用 Decimal。
2. 重复判定归一化完全一致,无模糊匹配。
3. 删除只进回收站。
4. 接受 jpg/png/webp;原图先存 uploads/,确认后移入 invoices/。
5. 日志只记元数据。
6. CSV 用 utf-8-sig。
7. 测试用 unittest。
8. docx 不做大写金额、不嵌缩略图。
