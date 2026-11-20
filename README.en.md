# Student Reimbursement Manager (学生报销管家)

[中文](README.md)

A local desktop tool: import receipt photos/scans → auto-recognize content and categorize → select and generate a formal reimbursement summary (.docx / CSV).

Fully local, no accounts, privacy first: all data stays in your own workspace folder — no network, no uploads by default.

## Quick Start

**Easiest way**: double-click **启动报销管家.bat** in the project root. The first run auto-installs dependencies (internet needed, ~1-2 minutes); afterwards every double-click opens the main window directly — **no workspace-picker dialog**. Records are stored by default in the 「工作区」 folder inside the project directory (auto-created).

Requires Windows with Python 3.11+ (check *Add Python to PATH* during install).

Manual equivalent:

```bash
pip install -r requirements.txt
python app.py
```

## Interface

One complete workspace with four pages in the left navigation:

- **概览 (Overview)**: welcome card, big import buttons (multi-select / folder / drag into window), current-workspace glance and recent imports; you can set your own background image in Settings
- **票据库 (Invoices)**: filters, multi-select table, edit panel for correcting every field, confirm/archive, delete, force-keep
- **统计 (Stats)**: per-category totals of the current filter
- **设置 (Settings)**: default claimant, OCR command, workspace switching, background image

On first launch you pick (or create) a workspace folder; it is remembered afterwards.

- `python app.py --workspace D:\reimburse` to specify a workspace directly
- Local OCR enables automatically once `rapidocr-onnxruntime` is installed; the app works without it (see below)

## Workflow (two steps)

1. **Import**: click "添加票据图片" to multi-select files, or "导入文件夹" to import a folder recursively, or just drag files into the window. The tool reads content automatically — text PDFs are extracted directly, images go through local OCR — and recognizes category, amount, date, and invoice number. Anything unrecognized goes to the pending queue (yellow rows).
2. **Summarize**: filter by date/category/keyword and multi-select rows as your pick set — the status bar shows count and total live; "统计" opens per-category totals of the current filter; click "生成汇总单", fill in the claimant info, preview, and generate the docx (or "导出 CSV").

Every automatic result can be corrected in the edit panel. Confirming **learns a merchant→category rule** (a "learn" loop borrowed from knowledge-ontology tooling): confirm "汉庭" once as hotel lodging and future receipts mentioning 汉庭 classify automatically even without keyword hits. Duplicates (same file / invoice number / date+amount+merchant) are flagged; "强制保留" keeps them. Deleting only moves originals into the workspace `.trash/` folder.

## AI Agent access (MCP)

A dependency-free MCP server (`mcp_server.py`) lets opencode, Claude Desktop, Cursor or any MCP client query your local receipts, view stats, and generate summaries in natural language. The LLM lives on the client side; data never leaves your machine.

opencode (`~/.config/opencode/opencode.json`):

```json
{
  "mcp": {
    "baoxiao": {
      "type": "local",
      "command": ["python", "E:\\path\\to\\Invoiceeee\\mcp_server.py"],
      "enabled": true
    }
  }
}
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "baoxiao": {"command": "python", "args": ["E:\\path\\to\\Invoiceeee\\mcp_server.py"]}
  }
}
```

Workspace resolution: `BAOXIAO_WORKSPACE` env var > the folder last opened in the GUI.

## Receipt formats

Images `.jpg .jpeg .png .webp .bmp .tif .tiff .gif`, plus PDF e-invoices (text PDFs are extracted directly — no OCR needed; scanned PDFs are rendered and go through OCR).

## OCR (content-based recognition)

- With `rapidocr-onnxruntime` installed (included in requirements.txt): text is recognized locally on import → keyword classification (railway / flight / hotel / ride-hailing / taxi / dining) + regex extraction of amount, date, and invoice number.
- Without it: falls back to filename keyword rules (e.g. a filename containing "12306" is filed as railway); everything else goes to the pending queue. **Import is never blocked.**
- Auto-confirmation requires a recognized **amount**; date-only explanation documents stay pending for manual review.
- You can also configure an external OCR command template (with a `{image}` placeholder) in Settings; an explicit command takes priority over RapidOCR.

## Workspace layout

```
workspace/
├── data.db        # SQLite index (images are not stored here)
├── uploads/       # imported originals (moved away after confirmation)
├── invoices/      # archived receipts: YYYY-MM/category/YYYYMMDD_merchant_amount_id.img
├── exports/       # generated summaries and CSV files
├── logs/app.log   # action log (actions and metadata only)
└── .trash/        # recycle bin for deleted originals
```

## Backup & migration

Copy the whole workspace folder to back up. Move it to another machine and run `python app.py --workspace <path>` to continue. Every original can be found under `invoices/` as `month/category/date_merchant_amount`.

## Tests

```bash
python -m unittest discover -s tests -v   # unit and pipeline tests
python tools/smoke_gui.py                 # automated end-to-end GUI smoke
```

## Samples

`samples/` contains a complete demo workspace and a generated summary; regenerate with `python tools/make_samples.py`.

## Known limitations

- HEIC (iPhone native format) is not supported yet; convert to JPG first.
- Duplicate detection is exact-match (hash / invoice number / date+amount+merchant); no fuzzy matching.
- Single user on one machine; no accounts, sync, or cloud services.
- Amounts use two decimals; no Chinese-uppercase amounts; no embedded thumbnails in the summary.
- GUI interaction itself is manually verified (logic layer has 71 tests plus a smoke script).

## Project status

P0 (including the GUI upgrade) is complete. The project is closed — no maintenance debt.
