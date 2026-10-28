"""ETF 分类与标的池（对标守猪逮兔常见杠杆/常规 ETF）。"""

from __future__ import annotations

# tab value -> (label, list of {code, name, stooq, yf})
# code 用富途风格 US.XXX / HK.XXXXX，便于对照

ETF_TABS: list[dict] = [
    {"value": "1", "label": "美股杠杆"},
    {"value": "2", "label": "美股常规"},
    {"value": "5", "label": "港股杠杆"},
    {"value": "6", "label": "港股常规"},
    {"value": "4", "label": "全球ETF"},
]

ETF_POOL: dict[str, list[dict]] = {
    "1": [
        {"code": "US.TQQQ", "name": "三倍纳指", "stooq": "tqqq.us", "yf": "TQQQ"},
        {"code": "US.SOXL", "name": "三倍半导体", "stooq": "soxl.us", "yf": "SOXL"},
        {"code": "US.UPRO", "name": "三倍标普", "stooq": "upro.us", "yf": "UPRO"},
        {"code": "US.TNA", "name": "三倍罗素", "stooq": "tna.us", "yf": "TNA"},
        {"code": "US.LABU", "name": "三倍生技", "stooq": "labu.us", "yf": "LABU"},
        {"code": "US.FNGU", "name": "三倍FANG", "stooq": "fngu.us", "yf": "FNGU"},
        {"code": "US.TECL", "name": "三倍科技", "stooq": "tecl.us", "yf": "TECL"},
        {"code": "US.SPXL", "name": "三倍标普500", "stooq": "spxl.us", "yf": "SPXL"},
        {"code": "US.QLD", "name": "两倍纳指", "stooq": "qld.us", "yf": "QLD"},
        {"code": "US.SSO", "name": "两倍标普", "stooq": "sso.us", "yf": "SSO"},
        {"code": "US.NUGT", "name": "两倍黄金矿", "stooq": "nugt.us", "yf": "NUGT"},
        {"code": "US.JNUG", "name": "两倍小黄金", "stooq": "jnug.us", "yf": "JNUG"},
        {"code": "US.ERX", "name": "两倍能源", "stooq": "erx.us", "yf": "ERX"},
        {"code": "US.YINN", "name": "三倍中国", "stooq": "yinn.us", "yf": "YINN"},
        {"code": "US.KORU", "name": "三倍韩国", "stooq": "koru.us", "yf": "KORU"},
        {"code": "US.UDOW", "name": "三倍道指", "stooq": "udow.us", "yf": "UDOW"},
    ],
    "2": [
        {"code": "US.SPY", "name": "标普500", "stooq": "spy.us", "yf": "SPY"},
        {"code": "US.QQQ", "name": "纳指100", "stooq": "qqq.us", "yf": "QQQ"},
        {"code": "US.IWM", "name": "罗素2000", "stooq": "iwm.us", "yf": "IWM"},
        {"code": "US.DIA", "name": "道指", "stooq": "dia.us", "yf": "DIA"},
        {"code": "US.XLK", "name": "科技板块", "stooq": "xlk.us", "yf": "XLK"},
        {"code": "US.XLF", "name": "金融板块", "stooq": "xlf.us", "yf": "XLF"},
        {"code": "US.XLE", "name": "能源板块", "stooq": "xle.us", "yf": "XLE"},
        {"code": "US.SMH", "name": "半导体", "stooq": "smh.us", "yf": "SMH"},
        {"code": "US.ARKK", "name": "方舟创新", "stooq": "arkk.us", "yf": "ARKK"},
        {"code": "US.GLD", "name": "黄金", "stooq": "gld.us", "yf": "GLD"},
        {"code": "US.SLV", "name": "白银", "stooq": "slv.us", "yf": "SLV"},
        {"code": "US.TLT", "name": "长债", "stooq": "tlt.us", "yf": "TLT"},
        {"code": "US.HYG", "name": "高收益债", "stooq": "hyg.us", "yf": "HYG"},
        {"code": "US.EEM", "name": "新兴市场", "stooq": "eem.us", "yf": "EEM"},
        {"code": "US.VTI", "name": "全美市场", "stooq": "vti.us", "yf": "VTI"},
    ],
    "5": [
        {"code": "HK.07226", "name": "南方两倍恒指", "stooq": "7226.hk", "yf": "7226.HK"},
        {"code": "HK.07552", "name": "南方两倍科指", "stooq": "7552.hk", "yf": "7552.HK"},
        {"code": "HK.07200", "name": "溢利两倍恒指", "stooq": "7200.hk", "yf": "7200.HK"},
        {"code": "HK.07211", "name": "南方两倍国企", "stooq": "7211.hk", "yf": "7211.HK"},
    ],
    "6": [
        {"code": "HK.02800", "name": "盈富基金", "stooq": "2800.hk", "yf": "2800.HK"},
        {"code": "HK.03033", "name": "南方恒生科技", "stooq": "3033.hk", "yf": "3033.HK"},
        {"code": "HK.02828", "name": "恒生中国企业", "stooq": "2828.hk", "yf": "2828.HK"},
        {"code": "HK.02823", "name": "安硕国债", "stooq": "2823.hk", "yf": "2823.HK"},
        {"code": "HK.03115", "name": "全球X中国生物", "stooq": "3115.hk", "yf": "3115.HK"},
        {"code": "HK.03067", "name": "iShares核心MSCI", "stooq": "3067.hk", "yf": "3067.HK"},
    ],
    "4": [
        {"code": "US.EFA", "name": "发达市场", "stooq": "efa.us", "yf": "EFA"},
        {"code": "US.VXUS", "name": "全球除美", "stooq": "vxus.us", "yf": "VXUS"},
        {"code": "US.INDA", "name": "印度", "stooq": "inda.us", "yf": "INDA"},
        {"code": "US.EWJ", "name": "日本", "stooq": "ewj.us", "yf": "EWJ"},
        {"code": "US.FXI", "name": "中国大盘", "stooq": "fxi.us", "yf": "FXI"},
        {"code": "US.KWEB", "name": "中概互联", "stooq": "kweb.us", "yf": "KWEB"},
        {"code": "US.MCHI", "name": "MSCI中国", "stooq": "mchi.us", "yf": "MCHI"},
        {"code": "US.ASHR", "name": "沪深300", "stooq": "ashr.us", "yf": "ASHR"},
    ],
}
