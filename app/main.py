from __future__ import annotations

import io
import socket
from pathlib import Path

import qrcode
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.etf_service import get_etf_list
from app.futu_client import get_fear_greed

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
TEMPLATES = Jinja2Templates(directory=str(ROOT / "templates"))

app = FastAPI(title="贪恐 GreedFear")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


def lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return TEMPLATES.TemplateResponse(
        "index.html",
        {
            "request": request,
            "lan_ip": lan_ip(),
            "port": request.url.port or 8000,
        },
    )


@app.get("/etf", response_class=HTMLResponse)
def etf_page(request: Request):
    return TEMPLATES.TemplateResponse("etf.html", {"request": request})


@app.get("/api/fear-greed")
def api_fear_greed(
    market: str = Query("US", pattern="^(US|HK|us|hk)$"),
    demo: bool | None = Query(None),
):
    result = get_fear_greed(market=market.upper(), force_demo=demo)
    return result.to_dict()


@app.get("/api/etf")
def api_etf(etf_type: str = Query("1")):
    return get_etf_list(etf_type=etf_type)


@app.get("/api/qr.png")
def api_qr(port: int = Query(8000)):
    url = f"http://{lan_ip()}:{port}"
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


@app.get("/api/meta")
def api_meta(request: Request):
    port = request.url.port or 8000
    ip = lan_ip()
    return {
        "lan_ip": ip,
        "port": port,
        "phone_url": f"http://{ip}:{port}",
    }
