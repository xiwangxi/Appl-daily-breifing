"""新闻抓取：苹果自身 + 供应链/生态相关公司。
数据源：Finnhub /company-news（需要 key，覆盖美股上市公司），
      Google News RSS（免 key，用于非美股上市公司如富士康、大立光、华为，以及作为补充）。
"""
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

import feedparser
import requests

FINNHUB_BASE = "https://finnhub.io/api/v1"


def _finnhub_company_news(ticker: str, api_key: str, lookback_hours: int) -> list:
    if not api_key:
        return []
    to_date = datetime.now(timezone.utc).date()
    from_date = to_date - timedelta(days=max(2, lookback_hours // 24 + 1))
    url = f"{FINNHUB_BASE}/company-news"
    params = {"symbol": ticker, "from": str(from_date), "to": str(to_date), "token": api_key}
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    items = resp.json()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    out = []
    for it in items:
        ts = it.get("datetime")
        if not ts:
            continue
        published = datetime.fromtimestamp(ts, tz=timezone.utc)
        if published < cutoff:
            continue
        out.append({
            "ticker": ticker,
            "title": it.get("headline"),
            "url": it.get("url"),
            "source": it.get("source"),
            "summary": it.get("summary", ""),
            "published": published.isoformat(),
        })
    return out


def _google_news_rss(query: str, lookback_hours: int, ticker: str = None) -> list:
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
    feed = feedparser.parse(url)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    out = []
    for entry in feed.entries:
        published = None
        if getattr(entry, "published_parsed", None):
            published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        if published and published < cutoff:
            continue
        source = None
        if getattr(entry, "source", None):
            source = getattr(entry.source, "title", None)
        out.append({
            "ticker": ticker,
            "title": entry.get("title"),
            "url": entry.get("link"),
            "source": source or "Google News",
            "summary": "",
            "published": published.isoformat() if published else None,
        })
    return out


def fetch_news_for_company(entry: dict, finnhub_key: str, lookback_hours: int) -> list:
    """entry 是 config/tickers.yaml 里 primary/core_suppliers/... 下的一条。"""
    results = []
    ticker = entry.get("ticker")
    name = entry.get("name", ticker)

    if ticker and not entry.get("name_only"):
        try:
            results.extend(_finnhub_company_news(ticker, finnhub_key, lookback_hours))
        except Exception as e:
            print(f"[fetch_news] Finnhub failed for {ticker}: {e}")

    keywords = entry.get("news_keywords") or [name]
    for kw in keywords:
        try:
            query = f'"{kw}" Apple' if ticker != "AAPL" else kw
            results.extend(_google_news_rss(query, lookback_hours, ticker=ticker or name))
        except Exception as e:
            print(f"[fetch_news] Google News RSS failed for {kw}: {e}")

    # 按 url 去重（同一公司多渠道可能抓到重复文章）
    seen_urls = set()
    deduped = []
    for r in results:
        if not r.get("url") or r["url"] in seen_urls:
            continue
        seen_urls.add(r["url"])
        deduped.append(r)
    return deduped


def fetch_all_news(tickers_config: dict, finnhub_key: str) -> dict:
    """返回 {"aapl": [...], "supply_chain": [...]}，供 summarize.py 使用。"""
    lookback = tickers_config.get("news_lookback_hours", 48)

    aapl_news = fetch_news_for_company(tickers_config["primary"], finnhub_key, lookback)

    supply_chain_news = []
    for group in ("core_suppliers", "customers_channel", "competitors", "ecosystem"):
        for entry in tickers_config.get(group, []):
            supply_chain_news.extend(fetch_news_for_company(entry, finnhub_key, lookback))
            time.sleep(0.3)  # 别把免费额度打太猛

    return {"aapl": aapl_news, "supply_chain": supply_chain_news}
