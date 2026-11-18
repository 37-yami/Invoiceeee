# -*- coding: utf-8 -*-
"""学生报销管家入口。

用法:
  python app.py                       # 当前目录建工作区,监听 127.0.0.1:8765
  python app.py --workspace ~/报销管家 --port 9000
  python app.py --lan                 # 局域网开放(手机上传),生成访问码
"""
from __future__ import annotations

import argparse
import secrets
import socket
from pathlib import Path

from core.db import Database
from core.workspace import Workspace
from web.server import make_server

DEFAULT_WORKSPACE = Path("报销管家工作区")


def local_ips() -> list[str]:
    """取本机局域网 IPv4,用于打印手机可访问地址。"""
    ips: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            ip = info[4][0]
            if "." in ip and not ip.startswith("127."):
                ips.add(ip)
    except OSError:
        pass
    return sorted(ips)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="学生报销管家:本地票据归档与报销汇总,数据不离开本机"
    )
    parser.add_argument("--workspace", default=str(DEFAULT_WORKSPACE),
                        help="工作区目录(默认: ./报销管家工作区)")
    parser.add_argument("--port", type=int, default=8765,
                        help="监听端口(默认 8765)")
    parser.add_argument("--lan", action="store_true",
                        help="开放局域网访问(手机上传),将生成访问码")
    args = parser.parse_args()

    ws = Workspace(Path(args.workspace))
    ws.ensure()
    db = Database(str(ws.db_path))
    db.init_schema()

    host = "0.0.0.0" if args.lan else "127.0.0.1"
    access_code = f"{secrets.randbelow(1000000):06d}" if args.lan else None

    server = make_server(ws, db, host, args.port, access_code=access_code)
    print(f"工作区:{ws.root.resolve()}")
    print(f"本机访问:http://127.0.0.1:{args.port}")
    if access_code:
        print(f"访问码:{access_code}(手机首次访问时输入)")
        for ip in local_ips():
            print(f"手机访问:http://{ip}:{args.port}")
    print("Ctrl+C 退出")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("已退出")
    finally:
        server.server_close()
        db.close()


if __name__ == "__main__":
    main()
