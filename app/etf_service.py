"""单只 ETF 贪恐评分：输出 -100~100，阈值 ±60（对标参考站）。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from app.etf_universe import ETF_POOL, ETF_TABS
from app.fear_greed import percentile_rank, score_momentum
from app.public_data import _stooq_close

_cache: dict[str, Any] = {}


def _to_signed(score_0_100: float) -> int:
    return int(round(float(np.clip(score_0_100, 0, 100)) * 2 - 100))


def _score_etf_series(closes: pd.Series) -> tuple[int, float]:
    if len(closes) < 30:
        return 0, float("nan")
    mom = score_momentum(closes, window=60)
    rets = closes.pct_change().dropna()
    vol_score = 50.0
    if len(rets) >= 40:
        vol = float(rets.iloc[-20:].std())
        hist = rets.rolling(20).std().dropna()
        pct = percentile_rank(hist, vol)
        ret5 = float(closes.iloc[-1] / closes.iloc[-6] - 1) if len(closes) >= 6 else 0.0
        vol_score = (1.0 - pct) * 50 + (np.clip(ret5 + 0.08, 0, 0.16) / 0.16) * 50
    ret20 = float(closes.iloc[-1] / closes.iloc[-21] - 1) if len(closes) >= 21 else 0.0
    strength = float(np.clip((ret20 + 0.15) / 0.30, 0, 1) * 100)
    blended = 0.45 * mom.score + 0.30 * vol_score + 0.25 * strength
    return _to_signed(blended), float(closes.iloc[-1])


def _demo_row(item: dict) -> dict:
    """网络不可用时的确定性演示行，保证页面可打开。"""
    seed = abs(hash(item["code"] + datetime.now().strftime("%Y%m%d%H"))) % (2**32)
    rng = np.random.default_rng(seed)
    score = int(rng.integers(-95, 96))
    price = float(rng.uniform(5, 120))
    return {
        "code": item["code"],
        "name": item["name"].replace("ETF", ""),
        "score": score,
        "price": f"{price:.3f}",
        "scale": "-",
        "danger": 0,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _fetch_one(item: dict) -> dict | None:
    try:
        closes = _stooq_close(item["stooq"])
        if len(closes) < 30:
            return None
        score, price = _score_etf_series(closes)
        if price != price:
            return None
        return {
            "code": item["code"],
            "name": item["name"].replace("ETF", ""),
            "score": score,
            "price": f"{price:.3f}",
            "scale": "-",
            "danger": 0,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    except Exception:
        return None


def get_etf_list(etf_type: str = "1") -> dict[str, Any]:
    etf_type = str(etf_type)
    cache_key = f"etf:{etf_type}"
    now = datetime.now().timestamp()
    cached = _cache.get(cache_key)
    if cached and now - cached["at"] < 30:
        return cached["payload"]

    pool = ETF_POOL.get(etf_type) or ETF_POOL["1"]
    rows: list[dict] = []
    source = "public"

    # 1) 列表骨架：对标站（名称/规模，免费分常为 0）或本地池
    try:
        from app.szdt_client import fetch_stock_emotion

        live = fetch_stock_emotion(etf_type)
        if live:
            rows = live
            source = "live"
    except Exception:
        live = None

    if not rows:
        rows = [
            {
                "code": x["code"],
                "name": x["name"],
                "score": 0,
                "price": "-",
                "scale": "-",
                "danger": 0,
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            for x in pool
        ]

    # 2) 本地反推算法覆盖分数（不依赖会员；VIP 仅用于校准脚本）
    try:
        from app.futu_quotes import enrich_rows_with_futu

        enriched, tag = enrich_rows_with_futu(rows, use_kline=True)
        if tag:
            rows = enriched
            source = f"{source}+local" if source != "public" else "local"
    except Exception:
        pass

    # 3) 仍无有效价时，公开行情 / 演示兜底
    priced = sum(1 for r in rows if str(r.get("price") or "-") not in {"-", "", "nan"})
    if priced < max(3, len(rows) // 4):
        with ThreadPoolExecutor(max_workers=3) as ex:
            futs = [ex.submit(_fetch_one, item) for item in pool]
            got = []
            for fut in as_completed(futs):
                row = fut.result()
                if row:
                    got.append(row)
        if got:
            rows = got
            source = "public"
        else:
            rows = [_demo_row(item) for item in pool]
            source = "demo"

    rows.sort(key=lambda r: r["code"])
    statics = {"fear": 0, "neutral": 0, "greed": 0}
    for r in rows:
        if r["score"] <= -60:
            statics["fear"] += 1
        elif r["score"] >= 60:
            statics["greed"] += 1
        else:
            statics["neutral"] += 1

    updated = max(
        (r["updated_at"] for r in rows),
        default=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    payload = {
        "tabs": ETF_TABS,
        "etf_type": etf_type,
        "items": rows,
        "statics": statics,
        "updated_at": updated,
        "source": source,
    }
    _cache[cache_key] = {"at": now, "payload": payload}
    return payload
