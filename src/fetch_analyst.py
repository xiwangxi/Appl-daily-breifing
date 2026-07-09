"""分析师评级 / 目标价 / 估值。数据源：yfinance（免费）。

原本用 Finnhub 的 /stock/price-target 和 /stock/upgrade-downgrade，但这两个接口在
Finnhub 免费版被限制成付费专属（实测返回 403），所以换成 yfinance 自带的分析师数据
（Yahoo Finance 本身也是聚合各家机构评级，覆盖面和 Finnhub 免费版差不多）。
"""


def _get_price_target(info: dict) -> dict:
    return {
        "target_high": info.get("targetHighPrice"),
        "target_low": info.get("targetLowPrice"),
        "target_mean": info.get("targetMeanPrice"),
        "target_median": info.get("targetMedianPrice"),
    }


def _get_recommendation_trend(tk) -> dict:
    rec = tk.recommendations
    if rec is None or rec.empty:
        return {}
    latest = rec.iloc[0]
    return {
        "period": latest.get("period"),
        "strong_buy": int(latest.get("strongBuy") or 0),
        "buy": int(latest.get("buy") or 0),
        "hold": int(latest.get("hold") or 0),
        "sell": int(latest.get("sell") or 0),
        "strong_sell": int(latest.get("strongSell") or 0),
    }


def _get_recent_rating_changes(tk, limit: int = 5) -> list:
    upg = tk.upgrades_downgrades
    if upg is None or upg.empty:
        return []
    recent = upg.sort_index(ascending=False).head(limit)
    out = []
    for idx, row in recent.iterrows():
        date_str = idx.isoformat() if hasattr(idx, "isoformat") else str(idx)
        out.append({
            "firm": row.get("Firm"),
            "from_grade": row.get("FromGrade"),
            "to_grade": row.get("ToGrade"),
            "action": (row.get("Action") or "").lower(),
            "date": date_str,
        })
    return out


def get_analyst_snapshot(ticker: str) -> dict:
    import yfinance as yf

    tk = yf.Ticker(ticker)

    price_target = {}
    try:
        price_target = _get_price_target(tk.info)
    except Exception as e:
        print(f"[fetch_analyst] price target lookup failed: {e}")

    recommendation = {}
    try:
        recommendation = _get_recommendation_trend(tk)
    except Exception as e:
        print(f"[fetch_analyst] recommendation trend failed: {e}")

    recent_changes = []
    try:
        recent_changes = _get_recent_rating_changes(tk)
    except Exception as e:
        print(f"[fetch_analyst] upgrades/downgrades failed: {e}")

    available = bool(price_target.get("target_mean") or recommendation or recent_changes)
    return {
        "available": available,
        "price_target": price_target,
        "recent_changes": recent_changes,
        "recommendation": recommendation,
    }
