"""半导体板块聚焦：日韩台美几个核心芯片股/指数，用来捕捉板块级别的大波动。数据源：yfinance（免费）。"""
from fetch_market_indices import _snapshot

# (ticker, 中文标签, English label)
SEMI_TICKERS = [
    ("^SOX", "费城半导体指数(SOX)", "PHLX Semiconductor Index"),
    ("TSM", "台积电(ADR)", "TSMC (ADR)"),
    ("005930.KS", "三星电子", "Samsung Electronics"),
    ("000660.KS", "SK海力士", "SK Hynix"),
    ("ASML", "阿斯麦(ASML)", "ASML"),
    ("NVDA", "英伟达", "Nvidia"),
    ("AMD", "AMD", "AMD"),
]


def get_semiconductor_snapshot() -> dict:
    try:
        stocks = [_snapshot(t, zh, en) for t, zh, en in SEMI_TICKERS]
    except Exception as e:
        print(f"[fetch_semiconductor] failed: {e}")
        return {"available": False, "error": str(e)}

    return {"available": True, "stocks": stocks}
