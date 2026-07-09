"""AAPL 股价速览：昨收/涨跌幅/盘前盘后/5日走势/临近事件倒计时。数据源：yfinance（免费）。"""
from datetime import datetime, timezone


def _pct(a, b):
    if a is None or b is None or b == 0:
        return None
    return (a - b) / b * 100


def get_price_snapshot(ticker: str = "AAPL") -> dict:
    """返回股价速览数据。任何字段拿不到就是 None，由上层负责在消息里标注"数据暂不可用"。"""
    import yfinance as yf

    tk = yf.Ticker(ticker)
    info = tk.fast_info if hasattr(tk, "fast_info") else {}

    last_close = info.get("last_price") or info.get("lastPrice")
    prev_close = info.get("previous_close") or info.get("previousClose")

    # 5日走势 + 支撑阻力（用近5日高低粗略估计）
    hist = tk.history(period="10d", interval="1d")
    five_day = []
    support = resistance = None
    if not hist.empty:
        recent = hist.tail(5)
        five_day = [
            {"date": idx.strftime("%m-%d"), "close": round(row["Close"], 2)}
            for idx, row in recent.iterrows()
        ]
        support = round(recent["Low"].min(), 2)
        resistance = round(recent["High"].max(), 2)
        if last_close is None and not hist.empty:
            last_close = round(hist["Close"].iloc[-1], 2)
        if prev_close is None and len(hist) >= 2:
            prev_close = round(hist["Close"].iloc[-2], 2)

    change_pct = _pct(last_close, prev_close)

    # 盘前盘后价格：yfinance 的 info 字典里有 preMarketPrice / postMarketPrice（不保证总是有）
    pre_post = {}
    try:
        raw_info = tk.info
        pre_post["pre_market_price"] = raw_info.get("preMarketPrice")
        pre_post["pre_market_change_pct"] = raw_info.get("preMarketChangePercent")
        pre_post["post_market_price"] = raw_info.get("postMarketPrice")
        pre_post["post_market_change_pct"] = raw_info.get("postMarketChangePercent")
        pe_ttm = raw_info.get("trailingPE")
        pe_fwd = raw_info.get("forwardPE")
    except Exception:
        pe_ttm = pe_fwd = None

    # 临近事件：财报日
    upcoming_events = []
    try:
        cal = tk.calendar
        earnings_dates = None
        if isinstance(cal, dict):
            earnings_dates = cal.get("Earnings Date")
        elif cal is not None and hasattr(cal, "loc") and "Earnings Date" in getattr(cal, "index", []):
            earnings_dates = cal.loc["Earnings Date"].tolist()
        if earnings_dates:
            for d in earnings_dates:
                if d is None:
                    continue
                d_date = d if isinstance(d, datetime) else datetime.combine(d, datetime.min.time())
                days_left = (d_date.date() - datetime.now(timezone.utc).date()).days
                if 0 <= days_left <= 30:
                    upcoming_events.append({"type": "财报", "date": str(d_date.date()), "days_left": days_left})
    except Exception:
        pass

    return {
        "ticker": ticker,
        "last_close": last_close,
        "prev_close": prev_close,
        "change_pct": change_pct,
        "support": support,
        "resistance": resistance,
        "five_day": five_day,
        "pe_ttm": pe_ttm,
        "pe_forward": pe_fwd,
        "upcoming_events": upcoming_events,
        **pre_post,
    }
