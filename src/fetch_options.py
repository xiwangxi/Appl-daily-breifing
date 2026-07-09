"""期权市场数据：PCR、IV、max pain、异常大单启发式检测。数据源：yfinance（免费，抓 Yahoo Finance 期权链）。

MVP 说明：
- 完全免费，不需要注册/API key，也没有付费门槛或美国身份限制。
- Yahoo Finance 的期权数据不是逐笔实时的，但对"开盘前晨报"这种场景足够。
- "异常期权大单"（Unusual Options Activity）这里用启发式规则近似：
  单张合约当日成交量 >= 3倍未平仓量 且 成交量超过阈值，按成交额排序取前几名。
  这不等于 Unusual Whales 那种基于逐笔大单方向判断的专业数据，只作为参考信号。
- IV 历史百分位：本地把每天的 ATM IV 存进 data/iv_history.json 滚动积累，
  积累不足10个交易日之前，百分位会显示"历史数据积累中"。
"""
import json
import os
from datetime import date, datetime

IV_HISTORY_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "iv_history.json")
MAX_DAYS_TO_EXPIRY = 45
UNUSUAL_VOL_OI_RATIO = 3.0
UNUSUAL_MIN_VOLUME = 500


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


def _iv_percentile(today_iv: float) -> tuple:
    history = _load_iv_history()
    history.append({"date": str(date.today()), "iv": today_iv})
    _save_iv_history(history)
    values = [h["iv"] for h in history if h.get("iv") is not None]
    if len(values) < 10:
        return None, len(values)
    rank = sum(1 for v in values if v <= today_iv) / len(values) * 100
    return round(rank, 1), len(values)


def _contracts_from_chain(chain, expiration: str) -> list:
    """把 yfinance option_chain() 返回的 calls/puts DataFrame 拍平成统一的 dict 列表。"""
    contracts = []
    for ctype, df in (("call", chain.calls), ("put", chain.puts)):
        for _, row in df.iterrows():
            contracts.append({
                "type": ctype,
                "strike": row.get("strike"),
                "expiration": expiration,
                "volume": int(row["volume"]) if row.get("volume") == row.get("volume") and row.get("volume") is not None else 0,
                "open_interest": int(row["openInterest"]) if row.get("openInterest") == row.get("openInterest") and row.get("openInterest") is not None else 0,
                "iv": row.get("impliedVolatility"),
                "last_price": row.get("lastPrice") or 0,
            })
    return contracts


def _max_pain(contracts: list) -> float | None:
    """标准 max pain 算法：找使期权卖方总损失最小的行权价。"""
    by_strike = {}
    for c in contracts:
        strike = c.get("strike")
        oi = c.get("open_interest") or 0
        if strike is None:
            continue
        by_strike.setdefault(strike, {"call_oi": 0, "put_oi": 0})
        if c["type"] == "call":
            by_strike[strike]["call_oi"] += oi
        elif c["type"] == "put":
            by_strike[strike]["put_oi"] += oi

    if not by_strike:
        return None

    best_strike, best_pain = None, None
    for candidate in sorted(by_strike.keys()):
        total_pain = 0.0
        for strike, oi in by_strike.items():
            if strike < candidate:
                total_pain += (candidate - strike) * oi["call_oi"]
            elif strike > candidate:
                total_pain += (strike - candidate) * oi["put_oi"]
        if best_pain is None or total_pain < best_pain:
            best_pain, best_strike = total_pain, candidate
    return best_strike


def get_options_snapshot(ticker: str) -> dict:
    import yfinance as yf

    tk = yf.Ticker(ticker)

    try:
        underlying_price = tk.fast_info.get("last_price") if hasattr(tk, "fast_info") else None
        expirations = list(tk.options or [])
    except Exception as e:
        print(f"[fetch_options] yfinance fetch failed: {e}")
        return {"available": False, "error": str(e)}

    near_expirations = [e for e in expirations if 0 <= _days_to_expiry(e) <= MAX_DAYS_TO_EXPIRY]
    if not near_expirations:
        return {"available": False}

    near_term = []
    for exp in near_expirations:
        try:
            chain = tk.option_chain(exp)
            near_term.extend(_contracts_from_chain(chain, exp))
        except Exception as e:
            print(f"[fetch_options] chain fetch failed for {exp}: {e}")

    if not near_term:
        return {"available": False}

    if underlying_price is None:
        # fast_info 拿不到就退而求其次，用最近到期日里离现价最近的行权价估个大概
        strikes = [c["strike"] for c in near_term if c.get("strike") is not None]
        underlying_price = sorted(strikes)[len(strikes) // 2] if strikes else None

    call_vol = sum(c["volume"] for c in near_term if c["type"] == "call")
    put_vol = sum(c["volume"] for c in near_term if c["type"] == "put")
    call_oi = sum(c["open_interest"] for c in near_term if c["type"] == "call")
    put_oi = sum(c["open_interest"] for c in near_term if c["type"] == "put")

    pcr_volume = round(put_vol / call_vol, 2) if call_vol else None
    pcr_oi = round(put_oi / call_oi, 2) if call_oi else None

    # ATM IV：找最近到期、行权价离现价最近的合约
    atm_iv = None
    if underlying_price:
        candidates = [c for c in near_term if c.get("iv") and c.get("strike") is not None]
        candidates.sort(key=lambda c: (_days_to_expiry(c["expiration"]), abs(c["strike"] - underlying_price)))
        if candidates:
            atm_iv = candidates[0]["iv"]

    iv_percentile, iv_history_days = (None, 0)
    if atm_iv is not None:
        iv_percentile, iv_history_days = _iv_percentile(atm_iv)

    max_pain_strike = _max_pain(near_term)

    # 异常大单启发式
    unusual = []
    for c in near_term:
        vol, oi = c["volume"], c["open_interest"]
        if vol >= UNUSUAL_MIN_VOLUME and oi > 0 and vol >= UNUSUAL_VOL_OI_RATIO * oi:
            unusual.append({
                "type": c["type"],
                "strike": c["strike"],
                "expiration": c["expiration"],
                "volume": vol,
                "open_interest": oi,
                "notional": round(vol * c["last_price"] * 100),
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
