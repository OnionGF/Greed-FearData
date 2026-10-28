"""富途 OpenD 实时快照 + 对标站风格贪恐分（本地反推，不依赖 VIP）。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from app.config import settings

# 日 K 缓存：code -> (ts, series)
_kline_cache: dict[str, tuple[float, pd.Series]] = {}
_KLINE_TTL = 600  # 10 分钟

# 2026-10-28 用 VIP 标签对美股 ETF 拟合（LOOCV mae≈16，corr≈0.88）
# score ≈ 80*MA60乖离 + 110*pos120 - 50*pos60 + 0.91*RSI14 - 93
_B60 = 80.0
_POS120 = 110.0
_POS60 = -50.0
_RSI = 0.91
_BIAS = -93.0


def _alive_price(row: dict[str, Any]) -> float:
    for key in ("pre_price", "overnight_price", "last_price"):
        v = row.get(key)
        try:
            if v is not None and float(v) == float(v) and float(v) > 0:
                return float(v)
        except Exception:
            continue
    return float("nan")


def _rsi(closes: pd.Series, n: int = 14) -> float:
    if len(closes) < n + 2:
        return 50.0
    delta = closes.diff()
    gain = delta.clip(lower=0).rolling(n).mean()
    loss = (-delta.clip(upper=0)).rolling(n).mean()
    g = float(gain.iloc[-1] or 0)
    l = float(loss.iloc[-1] or 0)
    if l <= 1e-12:
        return 100.0 if g > 0 else 50.0
    rs = g / l
    return float(100 - (100 / (1 + rs)))


def _ma_bias(closes: pd.Series, window: int) -> float:
    if len(closes) < window:
        return 0.0
    ma = float(closes.iloc[-window:].mean())
    if ma <= 0:
        return 0.0
    return float(closes.iloc[-1] / ma - 1.0)


def _range_pos(closes: pd.Series, window: int) -> float:
    if len(closes) < window:
        return 0.5
    hi = float(closes.iloc[-window:].max())
    lo = float(closes.iloc[-window:].min())
    if hi <= lo:
        return 0.5
    return float((float(closes.iloc[-1]) - lo) / (hi - lo))


def score_emotion(
    closes: pd.Series,
    live_price: float | None = None,
    leveraged: bool = True,
    prev_close: float | None = None,
) -> int:
    """
    本地贪恐分：-100~100（≥60 贪婪，≤-60 恐慌）。

    对标站分数与「当日涨跌」几乎无关，更接近中期位置情绪：
    120/60 日区间位置 + MA60 乖离 + RSI14。
    系数由 VIP 真值拟合，会员到期后仍可离线计算。
    """
    del leveraged, prev_close  # 保留参数兼容旧调用
    if len(closes) < 60:
        return 0
    s = closes.astype(float).copy()
    px = float(live_price) if live_price is not None and live_price == live_price else float(s.iloc[-1])
    s.iloc[-1] = px

    b60 = _ma_bias(s, 60)
    pos120 = _range_pos(s, 120) if len(s) >= 120 else _range_pos(s, len(s))
    pos60 = _range_pos(s, 60)
    rsi14 = _rsi(s, 14)

    raw = _B60 * b60 + _POS120 * pos120 + _POS60 * pos60 + _RSI * rsi14 + _BIAS
    return int(np.clip(round(raw), -100, 100))


def is_leveraged(code: str, name: str = "") -> bool:
    text = f"{code} {name}".upper()
    keys = (
        "两倍",
        "三倍",
        "2X",
        "3X",
        "BULL",
        "BEAR",
        "TQQQ",
        "SOXL",
        "UPRO",
        "TNA",
        "QLD",
        "YINN",
        "LABU",
        "TECL",
        "SPXL",
        "UDOW",
        "FNGU",
    )
    return any(k in text for k in keys)


def score_from_snapshot(row: dict[str, Any], name: str = "") -> int:
    """无足够 K 线时的弱兜底：用短窗涨跌粗估，精度远低于完整公式。"""
    del name
    price = _alive_price(row)
    prev = float(row.get("prev_close_price") or 0) or float("nan")
    if not (price == price and prev == prev and prev > 0):
        return 0
    # 无历史时只能给弱信号，避免假精确
    chg = price / prev - 1.0
    return int(np.clip(round(chg / 0.05 * 40), -40, 40))


def fetch_snapshots(codes: list[str]) -> dict[str, dict[str, Any]]:
    if not codes:
        return {}
    try:
        from futu import OpenQuoteContext, RET_OK
    except ImportError:
        return {}

    out: dict[str, dict[str, Any]] = {}
    quote = OpenQuoteContext(host=settings.futu_host, port=settings.futu_port)
    try:
        for i in range(0, len(codes), 80):
            batch = codes[i : i + 80]
            ret, data = quote.get_market_snapshot(batch)
            if ret != RET_OK or data is None or getattr(data, "empty", True):
                continue
            for _, row in data.iterrows():
                d = row.to_dict()
                code = str(d.get("code") or "")
                if code:
                    out[code] = d
    except Exception:
        return out
    finally:
        try:
            quote.close()
        except Exception:
            pass
    return out


def _request_kline(quote, code: str, days: int = 160) -> pd.Series:
    from futu import KLType, RET_OK

    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days + 40)).strftime("%Y-%m-%d")
    result = quote.request_history_kline(
        code, start=start, end=end, ktype=KLType.K_DAY, max_count=days
    )
    if isinstance(result, tuple) and len(result) >= 2:
        ret, data = result[0], result[1]
    else:
        return pd.Series(dtype=float)
    if ret != RET_OK or data is None or getattr(data, "empty", True):
        return pd.Series(dtype=float)
    col = "close" if "close" in data.columns else "Close"
    time_col = "time_key" if "time_key" in data.columns else "time"
    s = pd.Series(data[col].astype(float).values, index=pd.to_datetime(data[time_col]))
    return s.dropna()


def fetch_daily_closes_batch(codes: list[str], days: int = 160) -> dict[str, pd.Series]:
    """单连接串行拉日 K，带缓存。"""
    now = datetime.now().timestamp()
    out: dict[str, pd.Series] = {}
    missing: list[str] = []
    for code in codes:
        hit = _kline_cache.get(code)
        if hit and now - hit[0] < _KLINE_TTL and len(hit[1]) >= 60:
            out[code] = hit[1]
        else:
            missing.append(code)
    if not missing:
        return out

    try:
        from futu import OpenQuoteContext
    except ImportError:
        return out

    quote = OpenQuoteContext(host=settings.futu_host, port=settings.futu_port)
    try:
        for code in missing:
            try:
                s = _request_kline(quote, code, days=days)
                if len(s) >= 60:
                    _kline_cache[code] = (now, s)
                    out[code] = s
            except Exception:
                continue
    finally:
        try:
            quote.close()
        except Exception:
            pass
    return out


def enrich_rows_with_futu(rows: list[dict[str, Any]], use_kline: bool = True) -> tuple[list[dict[str, Any]], str]:
    codes = [r["code"] for r in rows if r.get("code")]
    snaps = fetch_snapshots(codes)
    if not snaps:
        return rows, ""

    klines: dict[str, pd.Series] = {}
    if use_kline:
        klines = fetch_daily_closes_batch([c for c in codes if c in snaps])

    enriched: list[dict[str, Any]] = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for r in rows:
        code = r.get("code") or ""
        snap = snaps.get(code)
        if not snap:
            enriched.append(r)
            continue
        price = _alive_price(snap)
        name = str(r.get("name") or snap.get("name") or code)
        lev = is_leveraged(code, name)
        prev = float(snap.get("prev_close_price") or 0) or None
        closes = klines.get(code)
        if closes is not None and len(closes) >= 60:
            score = score_emotion(
                closes, live_price=price, leveraged=lev, prev_close=prev
            )
        else:
            score = score_from_snapshot(snap, name=name)

        scale = r.get("scale")
        aum = snap.get("trust_aum")
        try:
            if aum is not None and float(aum) == float(aum) and float(aum) > 0:
                scale = round(float(aum) / 1e8, 2)
        except Exception:
            pass

        enriched.append(
            {
                **r,
                "name": name.replace("ETF", ""),
                "score": int(score),
                "price": f"{price:.3f}" if price == price else r.get("price", "-"),
                "scale": scale if scale is not None else "-",
                "updated_at": now,
            }
        )
    return enriched, "futu"
