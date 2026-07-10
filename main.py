"""AAPL Daily Telegram Digest 主入口。

每天运行一次：抓股价/新闻/分析师/期权数据 -> 用 Claude 摘要 -> 拼消息 -> 发 Telegram。
任何一个数据源失败都不应该导致整条推送发不出去，失败的板块会标注"数据源暂不可用"。
"""
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import yaml
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import cache  # noqa: E402
import fetch_analyst  # noqa: E402
import fetch_news  # noqa: E402
import fetch_options  # noqa: E402
import fetch_price  # noqa: E402
import build_message  # noqa: E402
import last_sent  # noqa: E402
import send_telegram  # noqa: E402
import summarize  # noqa: E402

TARGET_LOCAL_TZ = ZoneInfo("Europe/Berlin")
TARGET_LOCAL_HOUR = 7  # 用户希望醒来看到推送的当地时间


def load_config():
    secrets_path = os.path.join(os.path.dirname(__file__), "config", "secrets.env")
    if os.path.exists(secrets_path):
        load_dotenv(secrets_path)

    tickers_path = os.path.join(os.path.dirname(__file__), "config", "tickers.yaml")
    with open(tickers_path, "r", encoding="utf-8") as f:
        tickers_config = yaml.safe_load(f)

    return {
        "telegram_bot_token": os.environ.get("TELEGRAM_BOT_TOKEN"),
        "telegram_chat_id": os.environ.get("TELEGRAM_CHAT_ID"),
        "finnhub_api_key": os.environ.get("FINNHUB_API_KEY"),
        "anthropic_api_key": os.environ.get("ANTHROPIC_API_KEY"),
        "claude_model": os.environ.get("CLAUDE_MODEL") or "claude-haiku-4-5-20251001",
        "tickers": tickers_config,
    }


def should_run_now() -> bool:
    """GitHub Actions 用两个 UTC cron 触发点覆盖夏令时/冬令时，这里只在真正接近
    用户本地7点、且是工作日时才真正发送，避免夏令时切换期间重复推送或错过。
    RUN_MODE=manual（本地手动跑）时跳过这个检查。
    """
    if os.environ.get("RUN_MODE", "manual") != "scheduled":
        return True

    now_local = datetime.now(TARGET_LOCAL_TZ)
    if now_local.weekday() >= 5:  # 周六=5, 周日=6，美股不开盘
        print(f"[main] {now_local} 是周末，跳过")
        return False
    if now_local.hour != TARGET_LOCAL_HOUR:
        print(f"[main] 当前本地时间 {now_local}，不在目标小时 {TARGET_LOCAL_HOUR} 点，跳过")
        return False
    return True


def safe_call(fn, fallback, label):
    try:
        return fn()
    except Exception as e:
        print(f"[main] {label} 失败: {e}")
        return fallback


def main():
    cfg = load_config()

    if not should_run_now():
        return

    today_local = datetime.now(TARGET_LOCAL_TZ).strftime("%Y-%m-%d")
    scheduled = os.environ.get("RUN_MODE", "manual") == "scheduled"
    if scheduled and last_sent.already_sent_today("aapl", today_local):
        print(f"[main] AAPL digest 今天（{today_local}）已经发过了，跳过（同一天多个 cron 触发点撞到同一小时）")
        return

    if not cfg["telegram_bot_token"] or not cfg["telegram_chat_id"]:
        print("[main] 缺少 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID，无法发送，退出。")
        sys.exit(1)

    ticker = cfg["tickers"]["primary"]["ticker"]

    price = safe_call(lambda: fetch_price.get_price_snapshot(ticker), {}, "fetch_price")
    raw_news = safe_call(
        lambda: fetch_news.fetch_all_news(cfg["tickers"], cfg["finnhub_api_key"]),
        {"aapl": [], "supply_chain": []},
        "fetch_news",
    )
    analyst = safe_call(
        lambda: fetch_analyst.get_analyst_snapshot(ticker),
        {"available": False},
        "fetch_analyst",
    )
    options = safe_call(
        lambda: fetch_options.get_options_snapshot(ticker),
        {"available": False},
        "fetch_options",
    )

    seen = cache.load()
    unseen_aapl = cache.filter_unseen(raw_news.get("aapl", []), seen)
    unseen_supply = cache.filter_unseen(raw_news.get("supply_chain", []), seen)

    context_for_summary = {
        "price": price,
        "analyst": {k: v for k, v in analyst.items() if k != "available"},
        "options": {k: v for k, v in options.items() if k != "available"},
    }
    digest = safe_call(
        lambda: summarize.summarize_digest(
            unseen_aapl, unseen_supply, context_for_summary,
            cfg["anthropic_api_key"], cfg["claude_model"],
        ),
        summarize.fallback_summary(unseen_aapl, unseen_supply),
        "summarize",
    )

    messages = build_message.build_digest_messages(
        today_local, price,
        digest.get("aapl_news", []), digest.get("supply_chain_news", []),
        analyst, options, digest.get("today_focus", ""),
    )

    result = send_telegram.send_digest(cfg["telegram_bot_token"], cfg["telegram_chat_id"], messages)
    print(f"[main] 发送完成: {result}")
    if scheduled:
        last_sent.mark_sent("aapl", today_local)

    all_shown_urls = [{"url": it.get("url")} for it in digest.get("aapl_news", []) + digest.get("supply_chain_news", [])]
    seen = cache.mark_seen(all_shown_urls, seen)
    retention_days = cfg["tickers"].get("dedup_retention_days", 7)
    seen = cache.prune(seen, retention_days)
    cache.save(seen)


if __name__ == "__main__":
    main()
