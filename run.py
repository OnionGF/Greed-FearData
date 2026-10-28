"""启动本地贪恐看板：电脑浏览器与同一 Wi-Fi 手机均可访问。"""

from __future__ import annotations

import socket

import uvicorn


def lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


if __name__ == "__main__":
    host = "0.0.0.0"
    port = int(__import__("os").environ.get("PORT", "8765"))
    ip = lan_ip()
    print("=" * 48, flush=True)
    print("  贪恐 GreedFear", flush=True)
    print(f"  本机:  http://127.0.0.1:{port}", flush=True)
    print(f"  手机:  http://{ip}:{port}", flush=True)
    print("  云端部署后电脑关机也可外网访问", flush=True)
    print("=" * 48, flush=True)
    uvicorn.run("app.main:app", host=host, port=port, reload=False)
