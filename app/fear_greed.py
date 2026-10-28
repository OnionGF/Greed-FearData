"""多因子贪恐指数：0–100，参考 CNN Fear & Greed 结构，适配富途可得数据。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd


LEVELS = (
    (25, "极度恐惧", "extreme-fear"),
    (45, "恐惧", "fear"),
    (55, "中性", "neutral"),
    (75, "贪婪", "greed"),
    (101, "极度贪婪", "extreme-greed"),
)


@dataclass
class FactorResult:
    key: str
    name: str
    score: float
    raw: float | None
    detail: str


@dataclass
class FearGreedResult:
    score: int
    level: str
    level_key: str
    market: str
    source: str
    updated_at: str
    factors: list[FactorResult]
    history: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload


def _clip01(x: float) -> float:
    return float(np.clip(x, 0.0, 1.0))


def percentile_rank(series: pd.Series, value: float) -> float:
    """当前值在历史序列中的百分位（0–1）。"""
    clean = series.dropna()
    if clean.empty:
        return 0.5
    return float((clean <= value).mean())


def score_momentum(closes: pd.Series, window: int = 125) -> FactorResult:
    """价格相对均线：高于均线越多越贪婪。"""
    if len(closes) < max(20, window // 4):
        return FactorResult("momentum", "价格动量", 50.0, None, "样本不足")
    sma = closes.rolling(min(window, len(closes))).mean()
    ratio = (closes.iloc[-1] / sma.iloc[-1]) - 1.0
    # 历史百分位 + 绝对偏离 混合，避免单边行情时百分位失真
    hist = (closes / sma) - 1.0
    pct = percentile_rank(hist.dropna(), float(ratio))
    abs_score = _clip01((float(ratio) + 0.08) / 0.16)
    score = (0.55 * pct + 0.45 * abs_score) * 100
    return FactorResult(
        "momentum",
        "价格动量",
        round(score, 1),
        round(float(ratio) * 100, 2),
        f"相对 {min(window, len(closes))} 日均线 {ratio * 100:+.2f}%",
    )


def score_breadth(advances: float, declines: float) -> FactorResult:
    """涨跌家数广度。"""
    total = advances + declines
    if total <= 0:
        return FactorResult("breadth", "市场广度", 50.0, None, "无涨跌分布")
    ratio = advances / total
    # 线性映射：30%→恐惧，70%→贪婪
    score = _clip01((ratio - 0.30) / 0.40) * 100
    return FactorResult(
        "breadth",
        "市场广度",
        round(score, 1),
        round(ratio * 100, 1),
        f"上涨 {int(advances)} / 下跌 {int(declines)}",
    )


def score_strength(strong_up: float, strong_down: float) -> FactorResult:
    """强势股占比（大涨 vs 大跌）。"""
    total = strong_up + strong_down
    if total <= 0:
        return FactorResult("strength", "价格强度", 50.0, None, "无极端涨跌样本")
    ratio = strong_up / total
    score = _clip01((ratio - 0.25) / 0.50) * 100
    return FactorResult(
        "strength",
        "价格强度",
        round(score, 1),
        round(ratio * 100, 1),
        f"大涨 {int(strong_up)} / 大跌 {int(strong_down)}",
    )


def score_put_call(put_call_ratio: float, history: pd.Series | None = None) -> FactorResult:
    """Put/Call：越高越恐惧，取历史百分位后反转。"""
    if put_call_ratio is None or np.isnan(put_call_ratio):
        return FactorResult("put_call", "Put/Call", 50.0, None, "无期权统计")
    if history is not None and len(history.dropna()) >= 10:
        pct = percentile_rank(history, float(put_call_ratio))
        score = (1.0 - pct) * 100
        detail = f"P/C={put_call_ratio:.2f}（历史百分位 {pct * 100:.0f}%）"
    else:
        # 经验区间：0.6 贪婪端，1.2 恐惧端
        score = (1.0 - _clip01((put_call_ratio - 0.6) / 0.6)) * 100
        detail = f"P/C={put_call_ratio:.2f}"
    return FactorResult(
        "put_call",
        "Put/Call",
        round(score, 1),
        round(float(put_call_ratio), 2),
        detail,
    )


def score_volatility(vix: float, vix_history: pd.Series | None = None) -> FactorResult:
    """波动率：高 VIX = 恐惧。"""
    if vix is None or np.isnan(vix):
        return FactorResult("volatility", "市场波动", 50.0, None, "无波动率数据")
    if vix_history is not None and len(vix_history.dropna()) >= 20:
        pct = percentile_rank(vix_history, float(vix))
        score = (1.0 - pct) * 100
        detail = f"VIX={vix:.2f}（历史偏高 {pct * 100:.0f}%）"
    else:
        score = (1.0 - _clip01((vix - 12) / 28)) * 100
        detail = f"VIX={vix:.2f}"
    return FactorResult(
        "volatility",
        "市场波动",
        round(score, 1),
        round(float(vix), 2),
        detail,
    )


def score_realized_vol(closes: pd.Series, window: int = 20) -> FactorResult:
    """无 VIX 权限时：用指数已实现波动率（年化）百分位，高波动=恐惧。"""
    if len(closes) < window + 5:
        return FactorResult("volatility", "市场波动", 50.0, None, "无波动率数据")
    rets = closes.pct_change().dropna()
    if len(rets) < window:
        return FactorResult("volatility", "市场波动", 50.0, None, "无波动率数据")
    vol_now = float(rets.iloc[-window:].std() * np.sqrt(252) * 100)
    hist = rets.rolling(window).std().dropna() * np.sqrt(252) * 100
    pct = percentile_rank(hist, vol_now)
    score = (1.0 - pct) * 100
    return FactorResult(
        "volatility",
        "市场波动",
        round(score, 1),
        round(vol_now, 2),
        f"已实现波动 {vol_now:.1f}%（{window}日年化，历史偏高 {pct * 100:.0f}%）",
    )


def score_safe_haven(equity_ret: float, haven_ret: float) -> FactorResult:
    """避险相对收益：避险跑赢股票 → 恐惧。"""
    if any(np.isnan(x) for x in (equity_ret, haven_ret)):
        return FactorResult("safe_haven", "避险需求", 50.0, None, "无避险对照")
    spread = haven_ret - equity_ret
    # spread 高（债/金更强）→ 恐惧
    score = (1.0 - _clip01((spread + 0.05) / 0.10)) * 100
    return FactorResult(
        "safe_haven",
        "避险需求",
        round(score, 1),
        round(spread * 100, 2),
        f"避险相对股票 {spread * 100:+.2f}%",
    )


def score_capital(net_inflow: float, history: pd.Series | None = None) -> FactorResult:
    """资金净流入：越高越贪婪。"""
    if net_inflow is None or np.isnan(net_inflow):
        return FactorResult("capital", "资金流向", 50.0, None, "无资金流数据")
    if history is not None and len(history.dropna()) >= 10:
        pct = percentile_rank(history, float(net_inflow))
        score = pct * 100
        detail = f"净流入历史百分位 {pct * 100:.0f}%"
    else:
        score = 50.0 + np.clip(net_inflow, -1, 1) * 40
        detail = f"净流入代理值 {net_inflow:.2f}"
    return FactorResult(
        "capital",
        "资金流向",
        round(float(np.clip(score, 0, 100)), 1),
        round(float(net_inflow), 2),
        detail,
    )


def classify(score: float) -> tuple[str, str]:
    for upper, label, key in LEVELS:
        if score < upper:
            return label, key
    return "极度贪婪", "extreme-greed"


def aggregate(factors: list[FactorResult], weights: dict[str, float] | None = None) -> float:
    """只合成有真实数据的因子（raw 非空）；全缺时退回等权均值。"""
    weights = weights or {f.key: 1.0 for f in factors}
    usable = [(f, weights.get(f.key, 1.0)) for f in factors if f.raw is not None]
    if not usable:
        usable = [(f, weights.get(f.key, 1.0)) for f in factors]
    total_w = sum(w for _, w in usable) or 1.0
    return float(sum(f.score * w for f, w in usable) / total_w)


def build_history_from_closes(
    closes: pd.Series,
    other_series: dict[str, pd.Series] | None = None,
    lookback: int = 60,
) -> list[dict[str, Any]]:
    """用动量主轴粗略回放近 N 日合成分，供前端画迷你趋势。"""
    other_series = other_series or {}
    if len(closes) < 30:
        return []
    out: list[dict[str, Any]] = []
    window = min(lookback, len(closes) - 20)
    for i in range(len(closes) - window, len(closes)):
        sub = closes.iloc[: i + 1]
        mom = score_momentum(sub)
        parts = [mom.score]
        if "vix" in other_series:
            v = other_series["vix"].iloc[: i + 1]
            if len(v.dropna()):
                parts.append(score_volatility(float(v.iloc[-1]), v).score)
        score = int(round(sum(parts) / len(parts)))
        ts = sub.index[-1]
        date = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
        out.append({"date": date, "score": score})
    return out
