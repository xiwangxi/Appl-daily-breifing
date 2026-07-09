"""近期已推送新闻链接的去重缓存。存成 JSON，超过保留期自动清理。"""
import json
import os
from datetime import datetime, timedelta, timezone

DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "seen_news.json")


def load(path: str = DEFAULT_PATH) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save(seen: dict, path: str = DEFAULT_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2, sort_keys=True)


def prune(seen: dict, retention_days: int) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    kept = {}
    for url, seen_at in seen.items():
        try:
            ts = datetime.fromisoformat(seen_at)
        except ValueError:
            continue
        if ts >= cutoff:
            kept[url] = seen_at
    return kept


def filter_unseen(items: list, seen: dict) -> list:
    """items: list of dict with a 'url' key. 返回还没推送过的条目。"""
    return [item for item in items if item.get("url") not in seen]


def mark_seen(items: list, seen: dict) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    for item in items:
        url = item.get("url")
        if url:
            seen[url] = now
    return seen
