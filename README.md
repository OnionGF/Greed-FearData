# 贪恐 GreedFear

本地 / 手机可看的多因子贪恐看板，含市场总览与 ETF 列表页（对标常见贪恐指数交互）。

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
PORT=8765 python run.py
```

- 市场总览：http://127.0.0.1:8765/
- ETF 贪恐：http://127.0.0.1:8765/etf

同一 Wi-Fi 下手机可访问电脑局域网地址；电脑需保持服务运行。

## 数据说明

1. 本机有富途 OpenD 时，市场页优先用富途行情合成。
2. 否则退回公开行情 / 演示数据。
3. ETF 贪恐分由本地算法计算（120/60 日区间位置 + MA60 乖离 + RSI14，对照对标站 VIP 真值拟合），不依赖会员。
4. 可选：会员有效期内用 `SZDT_AUTH` 跑 `python scripts/calibrate_szdt.py` 对照校准；密钥只放 `.env`。

## 配置

见 `.env.example`。
