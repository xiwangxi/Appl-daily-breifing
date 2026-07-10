"""记录每个 digest 今天有没有发过，防止同一天被多个 cron 触发点重复触发发送。

背景：一个 workflow 里放了两个 digest（AAPL + 大盘），每个又有夏令时/冬令时两个 UTC cron
入口，四个 cron 在另一 digest 的目标小时上偶尔会有交叉（比如大盘的冬令时 cron 落在 AAPL
目标小时里）。靠这个"今天发过了没"的持久化标记兜底去重，比死抠 cron 分钟精度更可靠。
"""
import json
import os

PATH = os.path.join(os.path.dirname(__file__), "..", "data", "last_sent.json")


def _load() -> dict:
    if not os.path.exists(PATH):
        return {}
    try:
        with open(PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def already_sent_today(digest_key: str, today_str: str) -> bool:
    return _load().get(digest_key) == today_str


def mark_sent(digest_key: str, today_str: str) -> None:
    data = _load()
    data[digest_key] = today_str
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
