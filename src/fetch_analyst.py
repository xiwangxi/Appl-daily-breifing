"""分析师评级 / 目标价 / 估值。数据源：Finnhub。

注意：Finnhub 免费额度下 /stock/price-target 和 /stock/upgrade-downgrade 部分字段
可能受限或返回空，代码对此做容错，拿不到就返回 None，由上层标注"数据源暂不可用"。
"""
from datetime import datetime, timedelta, timezone

import requests

FINNHUB_BASE = "https://finnhub.io/api/v1"


def _get(path: str, params: dict) -> dict | list | None:
    try:
        resp = requests.get(f"{FINNHUB_BASE}/{path}", params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[fetch_analyst] {path} failed: {e}")
        return None


def get_price_target(ticker: str, api_key: str) -> dict:
    data = _get("stock/price-target", {"symbol": ticker, "token": api_key})
    if not data:
        return {}
    return {
        "target_high": data.get("targetHigh"),
        "target_low": data.get("targetLow"),
        "target_mean": data.get("targetMean"),
        "target_median": data.get("targetMedian"),
        "last_updated": data.get("lastUpdated"),
    }


def get_recent_rating_changes(ticker: str, api_key: str, lookback_days: int = 7) -> list:
    """近期评级变化（上调/下调/维持），来自 /stock/upgrade-downgrade。"""
    to_date = datetime.now(timezone.utc).date()
    from_date = to_date - timedelta(days=lookback_days)
    data = _get("stock/upgrade-downgrade", {
        "symbol": ticker,
        "from": str(from_date),
        "to": str(to_date),
        "token": api_key,
    })
    if not data:
        return []
    out = []
    for item in data:
        out.append({
            "firm": item.get("company"),
            "from_grade": item.get("fromGrade"),
            "to_grade": item.get("toGrade"),
            "action": item.get("action"),  # up / down / main / init
            "date": item.get("gradeTime"),
        })
    # 最新的在前
    out.sort(key=lambda x: x.get("date") or "", reverse=True)
    return out


def get_recommendation_trend(ticker: str, api_key: str) -> dict:
    """买入/持有/卖出统计（最新一期）。"""
    data = _get("stock/recommendation", {"symbol": ticker, "token": api_key})
    if not data:
        return {}
    latest = data[0] if isinstance(data, list) and data else {}
    return {
        "period": latest.get("period"),
        "strong_buy": latest.get("strongBuy"),
        "buy": latest.get("buy"),
        "hold": latest.get("hold"),
        "sell": latest.get("sell"),
        "strong_sell": latest.get("strongSell"),
    }


def get_analyst_snapshot(ticker: str, api_key: str) -> dict:
    if not api_key:
        return {"available": False}
    return {
        "available": True,
        "price_target": get_price_target(ticker, api_key),
        "recent_changes": get_recent_rating_changes(ticker, api_key),
        "recommendation": get_recommendation_trend(ticker, api_key),
    }
