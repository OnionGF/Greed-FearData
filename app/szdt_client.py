"""可选：拉取守猪逮兔公开 API 的 ETF 列表（签名与前端一致）。"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import ssl
import urllib.request
from datetime import datetime, timezone
from typing import Any

BASE = os.getenv("SZDT_API_BASE", "https://szdt.tech/api")


def _secret() -> str:
    return os.getenv("SZDT_API_SECRET", "").strip()


def _sign(method: str, path_with_query: str, body: str = "") -> tuple[str, str]:
    secret = _secret()
    if not secret:
        raise RuntimeError("missing SZDT_API_SECRET")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    key = secret + ts
    msg = f"{method.upper()}_{path_with_query}_{body}_{key}"
    sig = hmac.new(key.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return ts, sig


def fetch_stock_emotion(etf_type: str = "1") -> list[dict[str, Any]] | None:
    if not _secret():
        return None
    path = f"/invest/stock_emotion?etf_type={etf_type}"
    ts, sig = _sign("GET", path)
    req = urllib.request.Request(
        BASE + path,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "X-Timestamp": ts,
            "X-Signature": sig,
            "X-Auth": "",
        },
    )
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
            payload = json.loads(resp.read().decode())
    except Exception:
        return None
    if not isinstance(payload, dict) or payload.get("status") != 1:
        return None
    data = payload.get("data") or []
    rows: list[dict[str, Any]] = []
    for a in data:
        emotion = a.get("emotion") or {}
        score = emotion.get("score")
        if score is None:
            continue
        rows.append(
            {
                "code": a.get("code") or emotion.get("code") or "",
                "name": str(a.get("name") or "").replace("ETF", ""),
                "score": int(score),
                "price": str(emotion.get("price") or "-"),
                "scale": a.get("scale") if a.get("scale") is not None else "-",
                "danger": int(a.get("danger") or 0),
                "updated_at": emotion.get("updated_at")
                or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    return rows
