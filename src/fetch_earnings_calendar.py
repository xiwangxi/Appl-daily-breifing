"""重点公司财报日历：不是全市场财报（免费数据源没有这个），而是一份权重股/半导体龙头的
自选清单，用 yfinance 逐个查下一次财报日期，命中"未来几天内"就提醒。数据源：yfinance（免费）。
"""
from datetime import date, timedelta

LOOKAHEAD_DAYS = 3  # 今天 + 未来2天

WATCHLIST = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
    "TSM", "ASML", "AMD", "INTC", "QCOM", "AVGO",
]


def _next_earnings_dates(ticker: str) -> list:
    import yfinance as yf

    tk = yf.Ticker(ticker)
    cal = tk.calendar
    raw_dates = []
    if isinstance(cal, dict):
        raw_dates = cal.get("Earnings Date") or []
    elif cal is not None and hasattr(cal, "loc"):
        try:
            raw_dates = list(cal.loc["Earnings Date"])
        except Exception:
            raw_dates = []

    out = []
    for d in raw_dates:
        if d is None:
            continue
        out.append(d.date() if hasattr(d, "date") else d)
    return out


def get_upcoming_earnings(today: date = None) -> list:
    today = today or date.today()
    window_end = today + timedelta(days=LOOKAHEAD_DAYS - 1)

    upcoming = []
    for ticker in WATCHLIST:
        try:
            for d in _next_earnings_dates(ticker):
                if today <= d <= window_end:
                    upcoming.append({"ticker": ticker, "date": d.isoformat()})
        except Exception as e:
            print(f"[fetch_earnings_calendar] {ticker} 查询失败: {e}")
            continue

    upcoming.sort(key=lambda x: (x["date"], x["ticker"]))
    return upcoming
