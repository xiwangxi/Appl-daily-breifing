"""期权市场数据：PCR、IV、max pain、异常大单启发式检测。数据源：Polygon.io Options API。

MVP 说明：
- Polygon 免费/基础套餐的期权数据有约15分钟延迟，足够"开盘前晨报"使用。
- "异常期权大单"（Unusual Options Activity）这里用启发式规则近似：
  单张合约当日成交量 >= 3倍未平仓量 且 成交量超过阈值，按成交额排序取前几名。
  这不等于 Unusual Whales 那种基于逐笔大单方向判断的专业数据，只作为参考信号。
- IV 历史百分位：本地把每天的 ATM IV 存进 data/iv_history.json 滚动积累，
  积累不足30个交易日之前，百分位会显示"历史数据积累中"。
"""
import json
import os
from datetime import datetime, date, timezone

import requests

POLYGON_BASE = "https://api.polygon.io"
IV_HISTORY_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "iv_history.json")
MAX_DAYS_TO_EXPIRY = 45
UNUSUAL_VOL_OI_RATIO = 3.0
UNUSUAL_MIN_VOLUME = 500


def _fetch_chain(ticker: str, api_key: str, max_pages: int = 8) -> list:
    url = f"{POLYGON_BASE}/v3/snapshot/options/{ticker}"
    params = {"apiKey": api_key, "limit": 250}
    results = []
    for _ in range(max_pages):
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        payload = resp.json()
        results.extend(payload.get("results", []))
        next_url = payload.get("next_url")
        if not next_url:
            break
        url = next_url
        params = {"apiKey": api_key}
    return results


def _days_to_expiry(expiration_date: str) -> int:
    exp = datetime.strptime(expiration_date, "%Y-%m-%d").date()
    return (exp - date.today()).days


def _load_iv_history() -> list:
    if not os.path.exists(IV_HISTORY_PATH):
        return []
    try:
        with open(IV_HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_iv_history(history: list) -> None:
    os.makedirs(os.path.dirname(IV_HISTORY_PATH), exist_ok=True)
    with open(IV_HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history[-252:], f, ensure_ascii=False, indent=2)


def _iv_percentile(today_iv: float) -> tuple[float | None, int]:
    history = _load_iv_history()
    history.append({"date": str(date.today()), "iv": today_iv})
    _save_iv_history(history)
    values = [h["iv"] for h in history if h.get("iv") is not None]
    if len(values) < 10:
        return None, len(values)
    rank = sum(1 for v in values if v <= today_iv) / len(values) * 100
    return round(rank, 1), len(values)


def _max_pain(contracts: list, underlying_price: float) -> float | None:
    """标准 max pain 算法：找使期权卖方总损失最小的行权价。"""
    by_strike = {}
    for c in contracts:
        details = c.get("details", {})
        strike = details.get("strike_price")
        oi = c.get("open_interest") or 0
        ctype = details.get("contract_type")
        if strike is None:
            continue
        by_strike.setdefault(strike, {"call_oi": 0, "put_oi": 0})
        if ctype == "call":
            by_strike[strike]["call_oi"] += oi
        elif ctype == "put":
            by_strike[strike]["put_oi"] += oi

    if not by_strike:
        return None

    strikes = sorted(by_strike.keys())
    best_strike, best_pain = None, None
    for candidate in strikes:
        total_pain = 0.0
        for strike, oi in by_strike.items():
            if strike < candidate:
                total_pain += (candidate - strike) * oi["call_oi"]
            elif strike > candidate:
                total_pain += (strike - candidate) * oi["put_oi"]
        if best_pain is None or total_pain < best_pain:
            best_pain, best_strike = total_pain, candidate
    return best_strike


def get_options_snapshot(ticker: str, api_key: str) -> dict:
    if not api_key:
        return {"available": False}

    try:
        raw = _fetch_chain(ticker, api_key)
    except Exception as e:
        print(f"[fetch_options] Polygon fetch failed: {e}")
        return {"available": False, "error": str(e)}

    if not raw:
        return {"available": False}

    underlying_price = None
    for c in raw:
        ua = c.get("underlying_asset", {})
        if ua.get("price"):
            underlying_price = ua["price"]
            break

    near_term = []
    for c in raw:
        exp = c.get("details", {}).get("expiration_date")
        if exp and 0 <= _days_to_expiry(exp) <= MAX_DAYS_TO_EXPIRY:
            near_term.append(c)

    call_vol = sum((c.get("day", {}) or {}).get("volume") or 0 for c in near_term if c.get("details", {}).get("contract_type") == "call")
    put_vol = sum((c.get("day", {}) or {}).get("volume") or 0 for c in near_term if c.get("details", {}).get("contract_type") == "put")
    call_oi = sum(c.get("open_interest") or 0 for c in near_term if c.get("details", {}).get("contract_type") == "call")
    put_oi = sum(c.get("open_interest") or 0 for c in near_term if c.get("details", {}).get("contract_type") == "put")

    pcr_volume = round(put_vol / call_vol, 2) if call_vol else None
    pcr_oi = round(put_oi / call_oi, 2) if call_oi else None

    # ATM IV：找最近到期、行权价离现价最近的合约
    atm_iv = None
    if underlying_price and near_term:
        sorted_by_dist = sorted(
            [c for c in near_term if c.get("implied_volatility")],
            key=lambda c: (
                _days_to_expiry(c["details"]["expiration_date"]),
                abs(c["details"]["strike_price"] - underlying_price),
            ),
        )
        if sorted_by_dist:
            atm_iv = sorted_by_dist[0]["implied_volatility"]

    iv_percentile, iv_history_days = (None, 0)
    if atm_iv is not None:
        iv_percentile, iv_history_days = _iv_percentile(atm_iv)

    max_pain_strike = _max_pain(near_term, underlying_price) if underlying_price else None

    # 异常大单启发式
    unusual = []
    for c in near_term:
        vol = (c.get("day", {}) or {}).get("volume") or 0
        oi = c.get("open_interest") or 0
        if vol >= UNUSUAL_MIN_VOLUME and oi > 0 and vol >= UNUSUAL_VOL_OI_RATIO * oi:
            last_price = (c.get("day", {}) or {}).get("close") or 0
            details = c.get("details", {})
            unusual.append({
                "type": details.get("contract_type"),
                "strike": details.get("strike_price"),
                "expiration": details.get("expiration_date"),
                "volume": vol,
                "open_interest": oi,
                "notional": round(vol * last_price * 100),
            })
    unusual.sort(key=lambda x: x["notional"], reverse=True)

    return {
        "available": True,
        "underlying_price": underlying_price,
        "pcr_volume": pcr_volume,
        "pcr_oi": pcr_oi,
        "atm_iv": round(atm_iv * 100, 1) if atm_iv is not None else None,
        "iv_percentile": iv_percentile,
        "iv_history_days": iv_history_days,
        "max_pain_strike": max_pain_strike,
        "unusual_activity": unusual[:5],
    }
