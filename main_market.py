"""US Market Daily 主入口：宏观视角的美股大盘晨报，中英双语，可以发给多个 Telegram 接收人。

每天运行一次：抓大盘指数/隔夜全球市场(日韩台重点)/半导体板块/宏观日历(FOMC/CPI/PPI/非农)/
财报日历/宏观新闻 -> Claude 生成中英双语摘要 ->
按每个接收人各自配置的语言发送（主接收人中英文都发，先中文后英文；第二接收人只发英文）。
任何数据源失败都不阻塞其它板块。
"""
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import build_message_market  # noqa: E402
import cache  # noqa: E402
import fetch_earnings_calendar  # noqa: E402
import fetch_econ_calendar_static  # noqa: E402
import fetch_market_indices  # noqa: E402
import fetch_market_news  # noqa: E402
import fetch_semiconductor  # noqa: E402
import last_sent  # noqa: E402
import send_telegram  # noqa: E402
import summarize  # noqa: E402

TARGET_LOCAL_TZ = ZoneInfo("Europe/Berlin")  # 只用来算"今天"的日期和判断周末，具体触发时间点由外部定时服务负责
MARKET_NEWS_CACHE_PATH = os.path.join(os.path.dirname(__file__), "data", "seen_market_news.json")
DEDUP_RETENTION_DAYS = 7


def load_config():
    secrets_path = os.path.join(os.path.dirname(__file__), "config", "secrets.env")
    if os.path.exists(secrets_path):
        load_dotenv(secrets_path)

    # 主接收人（你自己）中英文都收；第二接收人目前只收英文版。
    recipients = []
    primary_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if primary_chat_id:
        recipients.append({"chat_id": primary_chat_id, "langs": ["zh", "en"]})
    second_chat_id = os.environ.get("TELEGRAM_CHAT_ID_2")
    if second_chat_id:
        recipients.append({"chat_id": second_chat_id, "langs": ["en"]})

    return {
        "telegram_bot_token": os.environ.get("TELEGRAM_BOT_TOKEN"),
        "recipients": recipients,
        "finnhub_api_key": os.environ.get("FINNHUB_API_KEY"),
        "anthropic_api_key": os.environ.get("ANTHROPIC_API_KEY"),
        "claude_model": os.environ.get("CLAUDE_MODEL") or "claude-haiku-4-5-20251001",
    }


def should_run_now() -> bool:
    """GitHub 自带的 schedule 触发器实测完全不可靠，改为外部定时服务在正确的本地时间
    调用 workflow_dispatch。这里只做周末兜底（外部服务的 cron 表达式本身也该排除周末）。
    """
    if os.environ.get("RUN_MODE", "manual") != "scheduled":
        return True

    now_local = datetime.now(TARGET_LOCAL_TZ)
    if now_local.weekday() >= 5:
        print(f"[main_market] {now_local} 是周末，跳过")
        return False
    return True


def safe_call(fn, fallback, label):
    try:
        return fn()
    except Exception as e:
        print(f"[main_market] {label} 失败: {e}")
        return fallback


def main():
    cfg = load_config()

    if not should_run_now():
        return

    today_local = datetime.now(TARGET_LOCAL_TZ).strftime("%Y-%m-%d")
    scheduled = os.environ.get("RUN_MODE", "manual") == "scheduled"
    if scheduled and last_sent.already_sent_today("market", today_local):
        print(f"[main_market] 大盘 Daily 今天（{today_local}）已经发过了，跳过")
        return

    if not cfg["telegram_bot_token"] or not cfg["recipients"]:
        print("[main_market] 缺少 TELEGRAM_BOT_TOKEN 或没有配置任何 chat_id，无法发送，退出。")
        sys.exit(1)

    market = safe_call(fetch_market_indices.get_market_snapshot, {"available": False}, "fetch_market_indices")
    semi = safe_call(fetch_semiconductor.get_semiconductor_snapshot, {"available": False}, "fetch_semiconductor")
    calendar = safe_call(fetch_econ_calendar_static.get_upcoming_events, {"available": False}, "fetch_econ_calendar_static")
    earnings = safe_call(fetch_earnings_calendar.get_upcoming_earnings, [], "fetch_earnings_calendar")
    raw_news = safe_call(
        lambda: fetch_market_news.fetch_macro_news(cfg["finnhub_api_key"]),
        [],
        "fetch_market_news",
    )

    seen = cache.load(MARKET_NEWS_CACHE_PATH)
    unseen_news = cache.filter_unseen(raw_news, seen)

    context_for_summary = {
        "market": {k: v for k, v in market.items() if k != "available"},
        "semiconductor": {k: v for k, v in semi.items() if k != "available"},
        "calendar": {k: v for k, v in calendar.items() if k != "available"},
        "earnings": earnings,
    }
    digest = safe_call(
        lambda: summarize.summarize_market_digest(
            unseen_news, context_for_summary, cfg["anthropic_api_key"], cfg["claude_model"],
        ),
        summarize.fallback_market_summary(unseen_news),
        "summarize_market",
    )

    macro_news = digest.get("macro_news", [])
    messages_by_lang = {
        "zh": build_message_market.build_market_digest_messages(
            today_local, market, semi, calendar, earnings, macro_news, digest.get("today_focus_zh", ""), "zh",
        ),
        "en": build_message_market.build_market_digest_messages(
            today_local, market, semi, calendar, earnings, macro_news, digest.get("today_focus_en", ""), "en",
        ),
    }

    total_sent, total_failed = 0, 0
    for recipient in cfg["recipients"]:
        # 语言顺序固定 zh -> en，每个接收人只发自己配置的语言列表里有的那些
        for lang in ("zh", "en"):
            if lang not in recipient["langs"]:
                continue
            result = send_telegram.send_digest(cfg["telegram_bot_token"], recipient["chat_id"], messages_by_lang[lang])
            total_sent += result["sent"]
            total_failed += result["failed"]
    print(f"[main_market] 发送完成: sent={total_sent} failed={total_failed} 接收人数={len(cfg['recipients'])}")

    if scheduled:
        last_sent.mark_sent("market", today_local)

    shown_urls = [{"url": it.get("url")} for it in macro_news]
    seen = cache.mark_seen(shown_urls, seen)
    seen = cache.prune(seen, DEDUP_RETENTION_DAYS)
    cache.save(seen, MARKET_NEWS_CACHE_PATH)


if __name__ == "__main__":
    main()
