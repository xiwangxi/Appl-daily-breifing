"""美股大盘 & 隔夜全球市场速览。数据源：yfinance（免费）。"""


def _pct(a, b):
    if a is None or b is None or b == 0:
        return None
    return (a - b) / b * 100


def _snapshot(ticker: str, label_zh: str, label_en: str) -> dict:
    import yfinance as yf

    tk = yf.Ticker(ticker)
    hist = tk.history(period="5d", interval="1d")
    if hist.empty:
        return {"label_zh": label_zh, "label_en": label_en, "ticker": ticker, "last": None, "change_pct": None}

    last = round(hist["Close"].iloc[-1], 2)
    prev = round(hist["Close"].iloc[-2], 2) if len(hist) >= 2 else None
    return {
        "label_zh": label_zh,
        "label_en": label_en,
        "ticker": ticker,
        "last": last,
        "change_pct": round(_pct(last, prev), 2) if prev else None,
    }


# 美股三大指数 + 期货（用于判断盘前方向）：(ticker, 中文标签, English label)
US_INDICES = [
    ("^GSPC", "标普500", "S&P 500"),
    ("^IXIC", "纳斯达克", "Nasdaq"),
    ("^DJI", "道琼斯", "Dow Jones"),
]
US_FUTURES = [
    ("ES=F", "标普500期货", "S&P 500 Futures"),
    ("NQ=F", "纳指期货", "Nasdaq Futures"),
    ("YM=F", "道指期货", "Dow Futures"),
]

# 隔夜全球市场：亚洲收盘 + 欧洲盘中/收盘，美股开盘前参考
GLOBAL_INDICES = [
    ("^N225", "日经225", "Nikkei 225"),
    ("^HSI", "恒生指数", "Hang Seng"),
    ("000001.SS", "上证指数", "Shanghai Composite"),
    ("^GDAXI", "德国DAX", "Germany DAX"),
    ("^FTSE", "英国富时100", "FTSE 100"),
]


def get_market_snapshot() -> dict:
    try:
        us_indices = [_snapshot(t, zh, en) for t, zh, en in US_INDICES]
        us_futures = [_snapshot(t, zh, en) for t, zh, en in US_FUTURES]
        global_indices = [_snapshot(t, zh, en) for t, zh, en in GLOBAL_INDICES]
    except Exception as e:
        print(f"[fetch_market_indices] failed: {e}")
        return {"available": False, "error": str(e)}

    return {
        "available": True,
        "us_indices": us_indices,
        "us_futures": us_futures,
        "global_indices": global_indices,
    }
