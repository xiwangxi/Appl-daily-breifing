"""近期重要宏观经济事件日历（CPI、非农、FOMC 利率决议等）。数据源：Finnhub /calendar/economic。

MVP 说明：这个接口在 Finnhub 免费层是否可用不确定（其它几个"专属"接口之前实测被限制成付费），
拿不到就整块标注"数据源暂不可用"，不阻塞大盘 Daily 的其它板块。
"""
from datetime import date, timedelta

import requests

FINNHUB_BASE = "https://finnhub.io/api/v1"
LOOKAHEAD_DAYS = 7

# 只保留对美股大盘有明显影响的事件，过滤掉海量低影响的小国数据
HIGH_IMPACT_EVENTS = {
    "cpi", "core cpi", "nonfarm payrolls", "unemployment rate", "fomc",
    "fed interest rate decision", "gdp", "ppi", "retail sales", "pmi",
    "consumer confidence", "ism manufacturing", "ism services", "pce",
}


def get_upcoming_events(api_key: str) -> dict:
    if not api_key:
        return {"available": False}

    today = date.today()
    to_date = today + timedelta(days=LOOKAHEAD_DAYS)
    try:
        resp = requests.get(
            f"{FINNHUB_BASE}/calendar/economic",
            params={"from": str(today), "to": str(to_date), "token": api_key},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[fetch_economic_calendar] failed: {e}")
        return {"available": False, "error": str(e)}

    events = data.get("economicCalendar") or data.get("result") or []
    filtered = []
    for ev in events:
        country = (ev.get("country") or "").upper()
        if country not in ("US", "USA", ""):
            continue
        name = (ev.get("event") or "").lower()
        if not any(key in name for key in HIGH_IMPACT_EVENTS):
            continue
        filtered.append({
            "event": ev.get("event"),
            "date": ev.get("time") or ev.get("date"),
            "actual": ev.get("actual"),
            "estimate": ev.get("estimate"),
            "previous": ev.get("prev"),
        })

    filtered.sort(key=lambda x: x.get("date") or "")
    return {"available": bool(filtered), "events": filtered[:8]}
