"""富途 OpenD 取数；连不上时自动降级演示数据。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from app.config import settings
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
    score_realized_vol,
    score_strength,
    score_volatility,
)

MARKET_META = {
    "US": {
        "index": "US.SPY",
        "vix": "US.VIX",
        "haven": "US.TLT",
        "haven_gold": "US.GLD",
        "flow_symbol": "US.SPY",
        "label": "美股",
        # 行业/风格 ETF 篮子 → 近似涨跌家数（OpenD 无 rise_fall_distribution）
        "breadth_basket": [
            "US.SPY",
            "US.QQQ",
            "US.IWM",
            "US.DIA",
            "US.XLF",
            "US.XLE",
            "US.XLK",
            "US.XLV",
            "US.XLI",
            "US.XLP",
            "US.XLY",
            "US.XLU",
            "US.XLB",
            "US.XLRE",
            "US.SMH",
            "US.EEM",
            "US.EFA",
            "US.HYG",
        ],
    },
    "HK": {
        "index": "HK.800000",
        "vix": "HK.VHSI",
        "haven": "HK.02823",
        "haven_gold": "HK.02840",  # 黄金 ETF（若无权限则忽略）
        "flow_symbol": "HK.00700",
        "label": "港股",
        "breadth_basket": [
            "HK.00700",
            "HK.09988",
            "HK.03690",
            "HK.01810",
            "HK.00941",
            "HK.00005",
            "HK.01299",
            "HK.02318",
            "HK.00388",
            "HK.00883",
            "HK.01024",
            "HK.09618",
            "HK.02020",
            "HK.06618",
            "HK.09888",
            "HK.00016",
            "HK.00001",
            "HK.00386",
        ],
    },
}

# CNN 风格权重：有数的因子按权合成
FACTOR_WEIGHTS = {
    "momentum": 1.0,
    "breadth": 1.0,
    "strength": 0.8,
    "put_call": 1.0,
    "volatility": 1.0,
    "safe_haven": 0.8,
    "capital": 1.0,
}


def _demo_result(market: str) -> FearGreedResult:
    meta = MARKET_META.get(market, MARKET_META["US"])
    rng = np.random.default_rng(abs(hash(datetime.utcnow().strftime("%Y%m%d%H"))) % (2**32))
    days = pd.bdate_range(end=datetime.utcnow().date(), periods=160)
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
    score = int(round(aggregate(factors, FACTOR_WEIGHTS)))
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


def _alive_px(row: dict[str, Any]) -> float:
    for key in ("pre_price", "overnight_price", "last_price"):
        try:
            v = float(row.get(key) or 0)
            if v > 0:
                return v
        except Exception:
            continue
    return float("nan")


def _day_chg(row: dict[str, Any] | None) -> float:
    if not row:
        return float("nan")
    px = _alive_px(row)
    prev = float(row.get("prev_close_price") or 0)
    if px == px and prev > 0:
        return px / prev - 1.0
    try:
        return float(row.get("change_rate") or 0) / 100.0
    except Exception:
        return float("nan")


def _kline_to_series(df: pd.DataFrame) -> pd.Series:
    if df is None or getattr(df, "empty", True):
        return pd.Series(dtype=float)
    col = "close" if "close" in df.columns else "Close"
    time_col = "time_key" if "time_key" in df.columns else ("time" if "time" in df.columns else None)
    s = pd.Series(df[col].astype(float).values)
    if time_col:
        s.index = pd.to_datetime(df[time_col])
    return s.dropna()


def _request_kline(quote, code: str, days: int = 160) -> pd.Series:
    from futu import KLType, RET_OK

    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days + 40)).strftime("%Y-%m-%d")
    result = quote.request_history_kline(
        code, start=start, end=end, ktype=KLType.K_DAY, max_count=days
    )
    if not isinstance(result, tuple) or len(result) < 2:
        return pd.Series(dtype=float)
    ret, data = result[0], result[1]
    if ret != RET_OK:
        return pd.Series(dtype=float)
    return _kline_to_series(data)


def _breadth_from_basket(snaps: dict[str, dict[str, Any]], codes: list[str]) -> tuple[float, float, float, float]:
    advances = declines = strong_up = strong_down = 0.0
    for code in codes:
        row = snaps.get(code)
        chg = _day_chg(row)
        if chg != chg:
            continue
        pct = chg * 100
        if pct > 0.05:
            advances += 1
            if pct >= 1.0:
                strong_up += 1
        elif pct < -0.05:
            declines += 1
            if pct <= -1.0:
                strong_down += 1
    return advances, declines, strong_up, strong_down


def _fetch_capital_flow(quote, code: str) -> tuple[float, pd.Series | None]:
    """日频资金净流入 + 历史序列（百分位用）。"""
    try:
        from futu import PeriodType, RET_OK

        ret, data = quote.get_capital_flow(code, period_type=PeriodType.DAY)
        if ret != RET_OK or data is None or getattr(data, "empty", True):
            return float("nan"), None
        s = pd.to_numeric(data["in_flow"], errors="coerce").dropna()
        if s.empty:
            return float("nan"), None
        # 优先主力；无则用总流入
        if "main_in_flow" in data.columns:
            main = pd.to_numeric(data["main_in_flow"], errors="coerce")
            if main.notna().sum() >= 10:
                s = main.dropna()
        return float(s.iloc[-1]), s
    except Exception:
        return float("nan"), None


def _safe_haven_returns(
    quote,
    equity_code: str,
    bond_code: str,
    gold_code: str | None,
    eq_closes: pd.Series,
    snaps: dict[str, dict[str, Any]],
) -> tuple[float, float]:
    """近 20 日股票 vs 避险（债/金取更强者）；K 线不足时退回当日涨跌。"""
    haven_codes = [c for c in (bond_code, gold_code) if c]
    haven_closes: list[pd.Series] = []
    for code in haven_codes:
        s = _request_kline(quote, code, days=60)
        if len(s) >= 21:
            haven_closes.append(s)

    if len(eq_closes) >= 21 and haven_closes:
        eq_ret = float(eq_closes.iloc[-1] / eq_closes.iloc[-21] - 1)
        hv_ret = max(float(h.iloc[-1] / h.iloc[-21] - 1) for h in haven_closes)
        return eq_ret, hv_ret

    # 快照当日：避险相对强弱仍有信号
    eq = _day_chg(snaps.get(equity_code))
    hv_vals = [_day_chg(snaps.get(c)) for c in haven_codes]
    hv_vals = [x for x in hv_vals if x == x]
    if eq == eq and hv_vals:
        return eq, float(max(hv_vals))
    return float("nan"), float("nan")


def fetch_from_futu(market: str) -> FearGreedResult | None:
    """路径 B：广度/波动/动量/资金/避险（+可选 Put/Call）→ 百分位归一 → 0–100。"""
    try:
        from futu import OpenQuoteContext, RET_OK
    except ImportError:
        return None

    meta = MARKET_META.get(market, MARKET_META["US"])
    quote = OpenQuoteContext(host=settings.futu_host, port=settings.futu_port)
    try:
        basket = list(meta.get("breadth_basket") or [])
        need = list(
            dict.fromkeys(
                [meta["index"], meta["vix"], meta["haven"], meta.get("haven_gold") or ""]
                + basket
            )
        )
        need = [c for c in need if c]

        ret, snap = quote.get_market_snapshot(need)
        if ret != RET_OK or snap is None or snap.empty:
            return None
        by_code = {str(r["code"]): r.to_dict() for _, r in snap.iterrows()}
        idx = by_code.get(meta["index"])
        if not idx:
            return None

        # —— 动量：指数日 K vs 均线（额度不足则快照代理）——
        closes = _request_kline(quote, meta["index"], days=160)
        if len(closes) >= 30:
            mom = score_momentum(closes)
        else:
            chg = _day_chg(idx)
            proxy = float(np.clip((chg + 0.03) / 0.06, 0, 1) * 100) if chg == chg else 50.0
            mom = FactorResult(
                "momentum",
                "价格动量",
                round(proxy, 1),
                round(chg * 100, 2) if chg == chg else None,
                "快照涨跌代理（日 K 暂不可用）",
            )

        # —— 广度 / 强度：板块 ETF 篮子涨跌分布 ——
        adv, dec, su, sd = _breadth_from_basket(by_code, basket or [meta["index"]])
        breadth = score_breadth(adv, dec)
        if breadth.raw is not None:
            breadth = FactorResult(
                breadth.key,
                breadth.name,
                breadth.score,
                breadth.raw,
                f"{breadth.detail}（行业ETF篮子）",
            )
        strength = score_strength(su, sd)

        # —— Put/Call：当前 OpenD 无现成全市场期权统计，占位中性（合成时会被 raw=None 剔除）——
        put_call = score_put_call(float("nan"))

        # —— 波动率：优先 VIX/VHSI；无权限则用指数已实现波动 ——
        vix_row = by_code.get(meta["vix"])
        vix_now = _alive_px(vix_row) if vix_row else float("nan")
        vix_s = pd.Series(dtype=float)
        if vix_row and vix_now == vix_now:
            vix_s = _request_kline(quote, meta["vix"], days=160)
            vol = score_volatility(vix_now, vix_s if len(vix_s) >= 20 else None)
        elif len(closes) >= 40:
            vol = score_realized_vol(closes, window=20)
        else:
            vol = score_volatility(float("nan"))

        # —— 避险：债 / 金 相对股票 ——
        eq_ret, hv_ret = _safe_haven_returns(
            quote,
            meta["index"],
            meta["haven"],
            meta.get("haven_gold"),
            closes,
            by_code,
        )
        haven = score_safe_haven(eq_ret, hv_ret)

        # —— 资金情绪：capital_flow 日频净流入百分位 ——
        net, flow_hist = _fetch_capital_flow(quote, meta["flow_symbol"])
        capital = score_capital(net, flow_hist)

        factors = [mom, breadth, strength, put_call, vol, haven, capital]
        score = int(round(aggregate(factors, FACTOR_WEIGHTS)))
        level, level_key = classify(score)
        history = (
            build_history_from_closes(closes, {"vix": vix_s} if len(vix_s) else {}, lookback=45)
            if len(closes) >= 30
            else []
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
        try:
            quote.close()
        except Exception:
            pass


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
        try:
            from concurrent.futures import ThreadPoolExecutor
            from concurrent.futures import TimeoutError as FuturesTimeout

            with ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(fetch_from_futu, market)
                try:
                    result = fut.result(timeout=25)
                except FuturesTimeout:
                    result = None
        except Exception:
            result = None
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
