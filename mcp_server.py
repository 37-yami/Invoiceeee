# -*- coding: utf-8 -*-
"""学生报销管家 · MCP 服务器(stdio,纯标准库)。

让任何 MCP 客户端(opencode、Claude Desktop、Cursor 等)用自然语言
查询本地票据库、看统计、生成报销汇总单。LLM 由客户端承担,
本服务器只提供数据工具——依然零云、零第三方依赖。

注册示例:
  opencode(~/.config/opencode/opencode.json):
    {"mcp": {"baoxiao": {"type": "local",
                         "command": ["python", "<本文件路径>"],
                         "enabled": true}}}
  Claude Desktop(claude_desktop_config.json):
    {"mcpServers": {"baoxiao": {"command": "python",
                                "args": ["<本文件路径>"]}}}

工作区解析:环境变量 BAOXIAO_WORKSPACE > GUI 记忆的工作区 > 当前目录默认。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core.db import Database  # noqa: E402
from core.models import CATEGORY_UNKNOWN, STATUS_CONFIRMED  # noqa: E402
from core.report_docx import generate as generate_docx  # noqa: E402
from core.summary import category_totals, total  # noqa: E402
from core.workspace import Workspace  # noqa: E402

CONFIG_PATH = Path.home() / ".student_invoice_gui.json"
SERVER_INFO = {"name": "baoxiao-manager", "version": "1.1.0"}
PROTOCOL_VERSION = "2024-11-05"
MAX_LIST_ROWS = 50

TOOLS = [
    {
        "name": "query_invoices",
        "description": "查询本地票据。可按状态/类别/日期范围/关键词筛选,"
                       "返回编号、状态、类别、日期、商户、金额、发票号。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string",
                           "enum": ["pending", "confirmed"]},
                "category": {"type": "string",
                             "description": "如 高铁/铁路、酒店住宿、网约车、餐饮"},
                "date_from": {"type": "string"},
                "date_to": {"type": "string"},
                "q": {"type": "string",
                      "description": "关键词,匹配商户/发票号/备注"},
            },
        },
    },
    {
        "name": "stats",
        "description": "统计全部票据:总张数、总金额、按类别合计。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "generate_report",
        "description": "按票据编号生成正式报销汇总单(docx),返回文件路径。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ids": {"type": "array", "items": {"type": "integer"},
                        "description": "票据编号(query_invoices 返回的编号)"},
                "meta": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "student_id": {"type": "string"},
                        "project": {"type": "string"},
                        "date_from": {"type": "string"},
                        "date_to": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                },
            },
            "required": ["ids"],
        },
    },
]


def _resolve_workspace() -> Path:
    env = os.environ.get("BAOXIAO_WORKSPACE")
    if env and Path(env).exists():
        return Path(env)
    if CONFIG_PATH.exists():
        try:
            ws = json.loads(CONFIG_PATH.read_text(encoding="utf-8")).get(
                "workspace")
            if ws and Path(ws).exists():
                return Path(ws)
        except (OSError, ValueError):
            pass
    ws = Path.cwd() / "报销管家工作区"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


class BaoxiaoServer:
    def __init__(self, ws: Workspace, db: Database):
        self.ws = ws
        self.db = db

    # ---- 工具实现 ----
    def _tool_query_invoices(self, args: dict) -> str:
        rows = self.db.list_invoices(
            status=args.get("status") or None,
            category=args.get("category") or None,
            date_from=args.get("date_from") or None,
            date_to=args.get("date_to") or None,
            q=args.get("q") or None,
        )
        if not rows:
            return "没有符合条件的票据。"
        total_count = len(rows)
        lines = [f"共 {total_count} 张"
                 + (f"(仅显示前 {MAX_LIST_ROWS} 张)"
                    if total_count > MAX_LIST_ROWS else "") + ":"]
        for r in rows[:MAX_LIST_ROWS]:
            status = "已确认" if r.status == STATUS_CONFIRMED else "待确认"
            category = ("(待定)" if r.category == CATEGORY_UNKNOWN
                        else r.category)
            amount = f"{r.amount:.2f}" if r.amount is not None else "未知"
            lines.append(
                f"- 编号{r.id} | {status} | {category} | "
                f"{r.invoice_date or '无日期'} | "
                f"{r.merchant or '无商户'} | {amount} 元 | "
                f"发票号 {r.invoice_no or '无'}"
            )
        return "\n".join(lines)

    def _tool_stats(self, _args: dict) -> str:
        rows = self.db.list_invoices()
        parts = [f"共 {len(rows)} 张,合计 {total(rows):.2f} 元。按类别:"]
        for cat, amount in sorted(category_totals(rows).items(),
                                  key=lambda kv: -kv[1]):
            parts.append(f"- {cat}: {amount:.2f} 元")
        return "\n".join(parts)

    def _tool_generate_report(self, args: dict) -> str:
        invoices = self.db.invoices_by_ids(args.get("ids") or [])
        if not invoices:
            return ("未选择票据:请提供有效的 ids"
                    "(可先用 query_invoices 查到编号)。")
        meta = args.get("meta") or {}
        for key, setting in (("name", "default_name"),
                             ("student_id", "default_student_id"),
                             ("project", "default_project")):
            meta.setdefault(key, self.db.get_setting(setting) or "")
        out = generate_docx(self.ws, invoices, meta)
        self.ws.log_action("report", kind="mcp", count=len(invoices))
        return f"已生成报销汇总单:\n{out}"

    def _call_tool(self, name: str, args: dict) -> str:
        if name == "query_invoices":
            return self._tool_query_invoices(args)
        if name == "stats":
            return self._tool_stats(args)
        if name == "generate_report":
            return self._tool_generate_report(args)
        raise KeyError(name)

    # ---- 协议处理 ----
    def handle(self, msg: dict) -> dict | None:
        """处理一条请求;通知(无 id)返回 None 不回复。"""
        method = msg.get("method", "")
        if msg.get("id") is None:
            return None
        if method == "initialize":
            requested = (msg.get("params") or {}).get("protocolVersion",
                                                      PROTOCOL_VERSION)
            return {"result": {
                "protocolVersion": requested,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            }}
        if method == "ping":
            return {"result": {}}
        if method == "tools/list":
            return {"result": {"tools": TOOLS}}
        if method == "tools/call":
            params = msg.get("params") or {}
            name = params.get("name", "")
            try:
                text = self._call_tool(name, params.get("arguments") or {})
            except KeyError:
                return {"error": {"code": -32602,
                                  "message": f"未知工具: {name}"}}
            except Exception as e:
                return {"result": {
                    "content": [{"type": "text", "text": f"执行出错: {e}"}],
                    "isError": True,
                }}
            return {"result": {
                "content": [{"type": "text", "text": text}],
                "isError": False,
            }}
        return {"error": {"code": -32601,
                          "message": f"未知方法: {method}"}}


def _emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> None:
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    ws = Workspace(_resolve_workspace())
    ws.ensure()
    db = Database(str(ws.db_path))
    db.init_schema()
    server = BaoxiaoServer(ws, db)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            _emit({"jsonrpc": "2.0", "id": None,
                   "error": {"code": -32700, "message": "解析错误"}})
            continue
        try:
            resp = server.handle(msg)
        except Exception as e:  # 服务器不因单请求退出
            resp = {"error": {"code": -32603,
                              "message": f"内部错误: {e}"}}
        if resp is None:
            continue
        _emit({"jsonrpc": "2.0", "id": msg.get("id"), **resp})
    db.close()


if __name__ == "__main__":
    main()
