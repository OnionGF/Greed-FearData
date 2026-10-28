"""富途 OpenD 取数；连不上时自动降级演示数据。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from app.config import settings
from app.fear_greed import (
    FearGreedResult,
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

MARKET_META = {
    "US": {
        "index": "US.SPY",
        "vix": "US.VIX",
        "haven": "US.TLT",
        "flow_symbol": "US.SPY",
        "option_market": "US_SECURITY",
        "label": "美股",
    },
    "HK": {
        "index": "HK.800000",
        "vix": "HK.VHSI",
        "haven": "HK.02823",  # 安硕国债 ETF 近似避险
        "flow_symbol": "HK.00700",
        "option_market": "HK_SECURITY",
        "label": "港股",
    },
}


def _demo_result(market: str) -> FearGreedResult:
    meta = MARKET_META.get(market, MARKET_META["US"])
    rng = np.random.default_rng(abs(hash(datetime.utcnow().strftime("%Y%m%d%H"))) % (2**32))
    days = pd.bdate_range(end=datetime.utcnow().date(), periods=160)
    # 带漂移的随机游走
    shocks = rng.normal(0.0004, 0.009, size=len(days))
    closes = 100 * np.cumprod(1 + shocks)
    close_s = pd.Series(closes, index=days)
    vix = pd.Series(18 + np.cumsum(rng.normal(0, 0.35, len(days))), index=days).clip(11, 45)
    pc = pd.Series(0.85 + np.cumsum(rng.normal(0, 0.02, len(days))), index=days).clip(0.5, 1.4)

    advances, declines = float(rng.integers(1800, 2800)), float(rng.integers(1200, 2200))
    strong_up, strong_down = float(rng.integers(80, 220)), float(rng.integers(60, 200))
    haven = close_s * (1.02 + np.cumsum(rng.normal(0, 0.002, len(days))) / 100)
    haven_s = pd.Series(haven, index=days)
    eq_ret = float(close_s.iloc[-1] / close_s.iloc[-21] - 1)
    hv_ret = float(haven_s.iloc[-1] / haven_s.iloc[-21] - 1)
    flow_hist = pd.Series(rng.normal(0, 1, 40))
    net_flow = float(flow_hist.iloc[-1])

    factors = [
        score_momentum(close_s),
        score_breadth(advances, declines),
        score_strength(strong_up, strong_down),
        score_put_call(float(pc.iloc[-1]), pc),
        score_volatility(float(vix.iloc[-1]), vix),
        score_safe_haven(eq_ret, hv_ret),
        score_capital(net_flow, flow_hist),
    ]
    score = int(round(aggregate(factors)))
    level, level_key = classify(score)
    history = build_history_from_closes(close_s, {"vix": vix}, lookback=45)
    return FearGreedResult(
        score=score,
        level=level,
        level_key=level_key,
        market=meta["label"],
        source="demo",
        updated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        factors=factors,
        history=history,
    )


def _parse_rise_fall(data: Any) -> tuple[float, float, float, float]:
    """从涨跌分布估算上涨/下跌、大涨/大跌家数。"""
    advances = declines = strong_up = strong_down = 0.0
    ranges = []
    if isinstance(data, dict):
        ranges = data.get("range_list") or data.get("rise_fall_distribution") or []
    elif isinstance(data, pd.DataFrame):
        ranges = data.to_dict("records")
    for row in ranges:
        left = row.get("left_border", row.get("left", 0)) or 0
        right = row.get("right_border", row.get("right", 0)) or 0
        count = float(row.get("stock_count", row.get("count", 0)) or 0)
        typ = str(row.get("type", ""))
        mid = (float(left) + float(right)) / 2 if right != left else float(left)
        if typ == "RISE_LIMIT" or mid > 0 or (left >= 0 and right > 0):
            advances += count
            if typ in {"RISE_LIMIT", "POSITIVE_INFINITY"} or mid >= 5:
                strong_up += count
        elif typ == "NEGATIVE_INFINITY" or mid < 0 or right <= 0:
            declines += count
            if typ == "NEGATIVE_INFINITY" or mid <= -5:
                strong_down += count
        else:
            # 跨零区间按比例粗分
            advances += count * 0.5
            declines += count * 0.5
    return advances, declines, strong_up, strong_down


def _kline_to_series(df: pd.DataFrame) -> pd.Series:
    if df is None or df.empty:
        return pd.Series(dtype=float)
    col = "close" if "close" in df.columns else "Close"
    time_col = "time_key" if "time_key" in df.columns else ("time" if "time" in df.columns else None)
    s = pd.Series(df[col].astype(float).values)
    if time_col:
        s.index = pd.to_datetime(df[time_col])
    return s


def fetch_from_futu(market: str) -> FearGreedResult | None:
    try:
        from futu import (
            KLType,
            Market,
            OpenQuoteContext,
            OptionMarket,
            OptionStatisticDataType,
            RET_OK,
        )
    except ImportError:
        return None

    meta = MARKET_META.get(market, MARKET_META["US"])
    quote = OpenQuoteContext(host=settings.futu_host, port=settings.futu_port)
    try:
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=260)).strftime("%Y-%m-%d")

        ret, data = quote.request_history_kline(
            meta["index"], start=start, end=end, ktype=KLType.K_DAY, max_count=260
        )
        if ret != RET_OK:
            return None
        closes = _kline_to_series(data)

        vix_s = pd.Series(dtype=float)
        ret_v, data_v = quote.request_history_kline(
            meta["vix"], start=start, end=end, ktype=KLType.K_DAY, max_count=260
        )
        if ret_v == RET_OK:
            vix_s = _kline_to_series(data_v)

        haven_s = pd.Series(dtype=float)
        ret_h, data_h = quote.request_history_kline(
            meta["haven"], start=start, end=end, ktype=KLType.K_DAY, max_count=260
        )
        if ret_h == RET_OK:
            haven_s = _kline_to_series(data_h)

        advances = declines = strong_up = strong_down = 0.0
        try:
            mkt = Market.US if market == "US" else Market.HK
            if hasattr(quote, "get_rise_fall_distribution"):
                ret_r, data_r = quote.get_rise_fall_distribution(market=mkt)
                if ret_r == RET_OK:
                    advances, declines, strong_up, strong_down = _parse_rise_fall(data_r)
        except Exception:
            pass

        # 板块快照兜底：用指数成分粗估不可用时保持 0，后面用演示式中性
        put_call = float("nan")
        pc_hist = pd.Series(dtype=float)
        try:
            opt_m = OptionMarket.US_SECURITY if market == "US" else OptionMarket.HK_SECURITY
            begin = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
            if hasattr(quote, "get_option_market_statistic"):
                ret_o, data_o, _ = quote.get_option_market_statistic(
                    opt_m,
                    OptionStatisticDataType.VOLUME,
                    begin_time=begin,
                    end_time=end,
                )
                if ret_o == RET_OK and data_o is not None and not data_o.empty:
                    if "ratio" in data_o.columns:
                        pc_hist = pd.Series(data_o["ratio"].astype(float).values)
                        put_call = float(pc_hist.iloc[0])  # 接口通常倒序
        except Exception:
            pass

        net_flow = float("nan")
        flow_hist = pd.Series(dtype=float)
        try:
            if hasattr(quote, "get_capital_flow"):
                ret_f, data_f = quote.get_capital_flow(meta["flow_symbol"])
                if ret_f == RET_OK and data_f is not None and not getattr(data_f, "empty", True):
                    # 不同版本字段名可能不同
                    for col in ("in_flow", "capital_flow", "net_in_flow", "last_capital_flow"):
                        if col in data_f.columns:
                            flow_hist = pd.Series(data_f[col].astype(float).values)
                            net_flow = float(flow_hist.iloc[-1])
                            break
        except Exception:
            pass

        eq_ret = hv_ret = float("nan")
        if len(closes) >= 21:
            eq_ret = float(closes.iloc[-1] / closes.iloc[-21] - 1)
        if len(haven_s) >= 21:
            hv_ret = float(haven_s.iloc[-1] / haven_s.iloc[-21] - 1)

        vix_now = float(vix_s.iloc[-1]) if len(vix_s) else float("nan")

        from app.fear_greed import FactorResult

        breadth = (
            score_breadth(advances, declines)
            if advances + declines > 0
            else FactorResult("breadth", "市场广度", 50.0, None, "暂无涨跌分布权限/数据")
        )
        strength = (
            score_strength(strong_up, strong_down)
            if strong_up + strong_down > 0
            else FactorResult("strength", "价格强度", 50.0, None, "暂无强度分布数据")
        )
        factors = [
            score_momentum(closes),
            breadth,
            strength,
            score_put_call(put_call, pc_hist if len(pc_hist) else None),
            score_volatility(vix_now, vix_s if len(vix_s) else None),
            score_safe_haven(eq_ret, hv_ret),
            score_capital(net_flow, flow_hist if len(flow_hist) else None),
        ]
        # 把完全缺数的中性因子（raw None）权重压低：aggregate 已等权；此处把无数据的标成 50 即可
        score = int(round(aggregate(factors)))
        level, level_key = classify(score)
        history = build_history_from_closes(
            closes, {"vix": vix_s} if len(vix_s) else {}, lookback=45
        )
        return FearGreedResult(
            score=score,
            level=level,
            level_key=level_key,
            market=meta["label"],
            source="futu",
            updated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            factors=factors,
            history=history,
        )
    except Exception:
        return None
    finally:
        quote.close()


_cache: dict[str, Any] = {"at": 0.0, "payload": None}


def get_fear_greed(market: str | None = None, force_demo: bool | None = None) -> FearGreedResult:
    import time

    market = (market or settings.market).upper()
    if market not in MARKET_META:
        market = "US"
    use_demo = settings.demo_mode if force_demo is None else force_demo

    now = time.time()
    cache_key = f"{market}:{use_demo}"
    cached = _cache.get("payload")
    if (
        cached
        and _cache.get("key") == cache_key
        and now - float(_cache.get("at", 0)) < settings.cache_seconds
    ):
        return cached

    result: FearGreedResult | None = None
    if not use_demo:
        # 本机有 OpenD → 富途；否则公开行情（适合云端 / 电脑关机）
        result = fetch_from_futu(market)
        if result is None:
            try:
                from app.public_data import fetch_from_public

                result = fetch_from_public(market)
            except Exception:
                result = None
    if result is None:
        result = _demo_result(market)

    _cache["at"] = now
    _cache["key"] = cache_key
    _cache["payload"] = result
    return result
