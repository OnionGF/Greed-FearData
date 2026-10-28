"""公开行情合成贪恐——云端无需本机 OpenD / 富途登录。

优先 Stooq CSV（稳、免 key），失败再试 yfinance。
"""

from __future__ import annotations

from datetime import datetime
from io import StringIO

import numpy as np
import pandas as pd

from app.fear_greed import (
    FearGreedResult,
    FactorResult,
    aggregate,
    build_history_from_closes,
    classify,
    score_breadth,
    score_capital,
    score_momentum,
    score_put_call,
    score_safe_haven,
    score_strength,
    score_volatility,
)

PUBLIC_META = {
    "US": {
        "label": "美股",
        "index": "spy.us",
        "vix": "^vix",
        "haven": "tlt.us",
        "yf_index": "SPY",
        "basket": [
            "aapl.us",
            "msft.us",
            "nvda.us",
            "amzn.us",
            "googl.us",
            "meta.us",
            "jpm.us",
            "xom.us",
        ],
    },
    "HK": {
        "label": "港股",
        "index": "^hsi",
        "vix": "^vhsi",
        "haven": "2823.hk",
        "yf_index": "2800.HK",
        "basket": [
            "0700.hk",
            "9988.hk",
            "0005.hk",
            "0941.hk",
            "1299.hk",
            "0388.hk",
            "2318.hk",
            "3690.hk",
        ],
    },
}


def _http_get(url: str, timeout: int = 12) -> str:
    """优先 curl（绕过部分环境 SSL 握手问题），再退回 urllib。"""
    import shutil
    import subprocess

    curl = shutil.which("curl")
    if curl:
        try:
            proc = subprocess.run(
                [curl, "-fsSL", "--max-time", str(timeout), "-A", "GreedFear/1.0", url],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout:
                return proc.stdout
        except Exception:
            pass

    import ssl
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "GreedFear/1.0"})
    ctx = ssl._create_unverified_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _stooq_close(symbol: str) -> pd.Series:
    url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
    try:
        text = _http_get(url)
    except Exception:
        return pd.Series(dtype=float)
    if not text or ("Date" not in text[:120] and "No data" in text):
        return pd.Series(dtype=float)
    try:
        df = pd.read_csv(StringIO(text))
    except Exception:
        return pd.Series(dtype=float)
    if df.empty or "Close" not in df.columns:
        return pd.Series(dtype=float)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date")
    s = pd.Series(df["Close"].astype(float).values, index=df["Date"])
    return s.dropna()


def _yf_close(symbol: str) -> pd.Series:
    try:
        import os

        # 部分环境存在中间人证书，放宽校验以便拉取公开行情
        os.environ.setdefault("PYTHONHTTPSVERIFY", "0")
        import ssl

        ssl._create_default_https_context = ssl._create_unverified_context
        import yfinance as yf

        t = yf.Ticker(symbol)
        hist = t.history(period="1y", auto_adjust=True)
        if hist is None or hist.empty:
            return pd.Series(dtype=float)
        s = hist["Close"].astype(float)
        s.index = pd.to_datetime(s.index).tz_localize(None)
        return s.dropna()
    except Exception:
        return pd.Series(dtype=float)


def _load_close(stooq_sym: str, yf_sym: str | None = None) -> pd.Series:
    try:
        s = _stooq_close(stooq_sym)
        if len(s) >= 40:
            return s
    except Exception:
        pass
    if yf_sym:
        return _yf_close(yf_sym)
    # stooq 失败时把 spy.us → SPY 试一下
    rough = stooq_sym.replace(".us", "").replace(".hk", ".HK").upper()
    if rough.startswith("^"):
        return _yf_close(rough.upper())
    return _yf_close(rough)


def _basket_breadth(changes: pd.Series) -> tuple[float, float, float, float]:
    ups = float((changes > 0).sum())
    downs = float((changes < 0).sum())
    strong_up = float((changes >= 0.02).sum())
    strong_down = float((changes <= -0.02).sum())
    return ups, downs, strong_up, strong_down


def _put_call_proxy(vix: pd.Series, closes: pd.Series) -> FactorResult:
    """无期权链时：用波动率分位 + 近端回报粗估 Put/Call 情绪。"""
    if len(vix) < 20 or len(closes) < 6:
        return FactorResult("put_call", "Put/Call", 50.0, None, "无期权链，跳过")
    from app.fear_greed import percentile_rank

    ret5 = float(closes.iloc[-1] / closes.iloc[-6] - 1)
    vix_pct = percentile_rank(vix, float(vix.iloc[-1]))
    # 高 VIX + 下跌 → 偏恐惧（低分）
    fear = 0.65 * vix_pct + 0.35 * (1.0 - np.clip((ret5 + 0.04) / 0.08, 0, 1))
    score = (1.0 - float(fear)) * 100
    return FactorResult(
        "put_call",
        "Put/Call",
        round(score, 1),
        round(float(vix.iloc[-1]), 2),
        f"波动代理（VIX={vix.iloc[-1]:.1f}，5日 {ret5 * 100:+.1f}%）",
    )


def fetch_from_public(market: str) -> FearGreedResult | None:
    market = market.upper()
    meta = PUBLIC_META.get(market, PUBLIC_META["US"])

    closes = _load_close(meta["index"], meta.get("yf_index"))
    if len(closes) < 40:
        return None

    vix_s = _load_close(meta["vix"])
    haven_s = _load_close(meta["haven"])

    changes = []
    for sym in meta["basket"]:
        try:
            s = _load_close(sym)
            if len(s) >= 2:
                changes.append(float(s.iloc[-1] / s.iloc[-2] - 1))
        except Exception:
            continue

    ch = pd.Series(changes)
    if len(ch):
        advances, declines, strong_up, strong_down = _basket_breadth(ch)
        # 放大到「市场感」数量级，仅影响文案观感
        scale = 200 if market == "US" else 80
        breadth = score_breadth(advances * scale, declines * scale)
        strength = score_strength(strong_up * scale, strong_down * scale)
        breadth = FactorResult(
            breadth.key,
            breadth.name,
            breadth.score,
            breadth.raw,
            f"样本股上涨 {int(advances)} / 下跌 {int(declines)}",
        )
        strength = FactorResult(
            strength.key,
            strength.name,
            strength.score,
            strength.raw,
            f"样本股大涨 {int(strong_up)} / 大跌 {int(strong_down)}",
        )
    else:
        breadth = FactorResult("breadth", "市场广度", 50.0, None, "成分股数据不足")
        strength = FactorResult("strength", "价格强度", 50.0, None, "成分股数据不足")

    eq_ret = hv_ret = float("nan")
    if len(closes) >= 21:
        eq_ret = float(closes.iloc[-1] / closes.iloc[-21] - 1)
    if len(haven_s) >= 21:
        hv_ret = float(haven_s.iloc[-1] / haven_s.iloc[-21] - 1)

    vix_now = float(vix_s.iloc[-1]) if len(vix_s) else float("nan")

    # 价格波动幅度代理「资金活跃」
    rets = closes.pct_change().dropna()
    if len(rets) >= 20:
        vol20 = rets.iloc[-20:].std()
        hist = rets.rolling(20).std().dropna()
        from app.fear_greed import percentile_rank

        pct = percentile_rank(hist, float(vol20))
        # 活跃偏贪婪一点：用 1 - 过高波动的惩罚
        capital = score_capital(float(pct * 2 - 1), None)
        capital = FactorResult(
            capital.key,
            capital.name,
            capital.score,
            round(float(vol20) * 100, 2),
            f"20日波动分位 {pct * 100:.0f}%",
        )
    else:
        capital = FactorResult("capital", "资金流向", 50.0, None, "样本不足")

    put_call = (
        _put_call_proxy(vix_s, closes)
        if len(vix_s)
        else score_put_call(float("nan"))
    )

    factors = [
        score_momentum(closes),
        breadth,
        strength,
        put_call,
        score_volatility(vix_now, vix_s if len(vix_s) else None),
        score_safe_haven(eq_ret, hv_ret),
        capital,
    ]
    score = int(round(aggregate(factors)))
    level, level_key = classify(score)
    history = build_history_from_closes(closes, {"vix": vix_s} if len(vix_s) else {}, lookback=45)
    return FearGreedResult(
        score=score,
        level=level,
        level_key=level_key,
        market=meta["label"],
        source="public",
        updated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        factors=factors,
        history=history,
    )
