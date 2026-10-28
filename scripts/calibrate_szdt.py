"""对照 VIP 真值校准本地贪恐公式（会员有效期内可跑）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

import numpy as np
from numpy.linalg import lstsq

from app.futu_quotes import (
    _alive_price,
    _ma_bias,
    _range_pos,
    _rsi,
    fetch_daily_closes_batch,
    fetch_snapshots,
    score_emotion,
)
from app.szdt_client import fetch_stock_emotion, has_vip_auth


def main() -> None:
    if not has_vip_auth():
        print("缺少 SZDT_AUTH，无法拉 VIP 真值")
        return

    labels: dict[str, int] = {}
    for et in ("1", "2", "3", "4"):
        rows = fetch_stock_emotion(et) or []
        for r in rows:
            code = str(r.get("code") or "")
            if code.startswith("US."):
                labels[code] = int(r["score"])

    codes = sorted(labels)
    snaps = fetch_snapshots(codes)
    klines = fetch_daily_closes_batch(codes, days=200)
    feats = []
    for code in codes:
        snap = snaps.get(code)
        s = klines.get(code)
        if snap is None or s is None or len(s) < 120:
            continue
        px = _alive_price(snap)
        ss = s.astype(float).copy()
        ss.iloc[-1] = px
        y = labels[code]
        local = score_emotion(ss, live_price=px)
        feats.append(
            {
                "code": code,
                "y": y,
                "local": local,
                "b60": _ma_bias(ss, 60),
                "pos120": _range_pos(ss, 120),
                "pos60": _range_pos(ss, 60),
                "rsi14": _rsi(ss, 14),
            }
        )

    if len(feats) < 20:
        print("样本不足", len(feats))
        return

    err = [abs(f["local"] - f["y"]) for f in feats]
    print(
        f"n={len(feats)} local vs VIP: mae={np.mean(err):.1f} "
        f"median={np.median(err):.1f} within20={np.mean(np.array(err)<=20):.0%}"
    )
    cols = ["b60", "pos120", "pos60", "rsi14"]
    A = np.column_stack([[f[c] for f in feats] for c in cols] + [np.ones(len(feats))])
    y = np.array([f["y"] for f in feats], dtype=float)
    coef, _, _, _ = lstsq(A, y, rcond=None)
    print("refit coef", dict(zip(cols + ["bias"], map(float, np.round(coef, 4)))))
    out = ROOT / "data" / "szdt_vip_scores.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(labels, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
