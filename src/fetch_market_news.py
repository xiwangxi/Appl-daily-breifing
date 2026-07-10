"""宏观新闻：影响美股大盘的公司无关事件（美联储、利率、通胀、关税、地缘政治等）。
数据源：Finnhub /news（general 分类，免费额度可用）+ Google News RSS（宏观关键词）。
"""
import re
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

import feedparser
import requests

FINNHUB_BASE = "https://finnhub.io/api/v1"
MAX_SUMMARY_CHARS = 300
_TAG_RE = re.compile(r"<[^>]+>")

# 影响大盘/宏观层面的关键词，覆盖美国国内政策 + 全球地缘政治
MACRO_KEYWORDS = [
    "Federal Reserve interest rate",
    "US inflation CPI",
    "US jobs report",
    "US tariff trade war",
    "US stock market outlook",
    "geopolitical risk markets",
    "US government shutdown debt",
    "China US relations economy",
]


def _clean_summary(raw: str) -> str:
    if not raw:
        return ""
    text = _TAG_RE.sub(" ", raw)
    text = " ".join(text.split())
    return text[:MAX_SUMMARY_CHARS]


def _finnhub_general_news(api_key: str, lookback_hours: int) -> list:
    resp = requests.get(
        f"{FINNHUB_BASE}/news",
        params={"category": "general", "token": api_key},
        timeout=15,
    )
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
            "title": it.get("headline"),
            "url": it.get("url"),
            "source": it.get("source"),
            "summary": _clean_summary(it.get("summary", "")),
            "published": published.isoformat(),
        })
    return out


def _google_news_rss(query: str, lookback_hours: int) -> list:
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
            "title": entry.get("title"),
            "url": entry.get("link"),
            "source": source or "Google News",
            "summary": _clean_summary(entry.get("summary", "")),
            "published": published.isoformat() if published else None,
        })
    return out


def fetch_macro_news(finnhub_key: str, lookback_hours: int = 48) -> list:
    results = []

    if finnhub_key:
        try:
            results.extend(_finnhub_general_news(finnhub_key, lookback_hours))
        except Exception as e:
            print(f"[fetch_market_news] Finnhub general news failed: {e}")

    for kw in MACRO_KEYWORDS:
        try:
            results.extend(_google_news_rss(kw, lookback_hours))
        except Exception as e:
            print(f"[fetch_market_news] Google News RSS failed for '{kw}': {e}")
        time.sleep(0.3)

    seen_urls = set()
    deduped = []
    for r in results:
        if not r.get("url") or r["url"] in seen_urls:
            continue
        seen_urls.add(r["url"])
        deduped.append(r)
    return deduped
