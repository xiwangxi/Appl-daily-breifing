"""拼装美股大盘宏观 Daily 的 Telegram HTML 消息，中英双语。复用 build_message.py 的分段打包逻辑。"""
from html import escape as _esc

from build_message import UNAVAILABLE, pack_messages

LABELS = {
    "zh": {
        "title": "🌎 <b>US Market Daily</b> — {date}",
        "s1": "【一、大盘速览】",
        "s2": "【二、隔夜全球市场】",
        "s3": "【三、经济日历 & 重要事件（未来7天）】",
        "s4": "【四、宏观新闻】",
        "s5": "【五、今日市场关注点】",
        "no_events": "近期没有查到高影响力的美国经济数据/事件",
        "no_news": "近48小时暂无重要宏观新闻",
    },
    "en": {
        "title": "🌎 <b>US Market Daily</b> — {date} (EN)",
        "s1": "<b>1. US Market Snapshot</b>",
        "s2": "<b>2. Overnight Global Markets</b>",
        "s3": "<b>3. Economic Calendar (next 7 days)</b>",
        "s4": "<b>4. Macro News</b>",
        "s5": "<b>5. Today's Market Focus</b>",
        "no_events": "No high-impact US economic events found in the lookahead window",
        "no_news": "No major macro news in the last 48 hours",
    },
}


def _fmt_pct(v):
    if v is None:
        return "N/A"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.2f}%"


def _label(item: dict, lang: str) -> str:
    return item.get("label_zh" if lang == "zh" else "label_en") or item.get("label") or ""


def build_indices_section(market: dict, lang: str) -> str:
    t = LABELS[lang]
    header = t["s1"]
    if not market or not market.get("available"):
        return f"{header}\n{UNAVAILABLE}"

    lines = [header]
    for idx in market.get("us_indices", []):
        val = f"${idx['last']:,.2f}" if idx.get("last") is not None else "N/A"
        lines.append(f"{_esc(_label(idx, lang))}: {val} ({_fmt_pct(idx.get('change_pct'))})")

    futures = market.get("us_futures", [])
    if futures:
        parts = [f"{_esc(_label(f, lang))} {_fmt_pct(f.get('change_pct'))}" for f in futures]
        prefix = "盘前期货: " if lang == "zh" else "Futures: "
        lines.append(prefix + " / ".join(parts))

    return "\n".join(lines)


def build_global_section(market: dict, lang: str) -> str:
    t = LABELS[lang]
    header = t["s2"]
    if not market or not market.get("available"):
        return f"{header}\n{UNAVAILABLE}"

    lines = [header]
    for idx in market.get("global_indices", []):
        val = f"{idx['last']:,.2f}" if idx.get("last") is not None else "N/A"
        lines.append(f"{_esc(_label(idx, lang))}: {val} ({_fmt_pct(idx.get('change_pct'))})")
    return "\n".join(lines)


def build_calendar_section(calendar: dict, lang: str) -> str:
    t = LABELS[lang]
    header = t["s3"]
    if not calendar or not calendar.get("available"):
        return f"{header}\n{t['no_events']}"

    lines = [header]
    for ev in calendar.get("events", []):
        est = f" (est. {ev['estimate']})" if ev.get("estimate") else ""
        lines.append(f"• {_esc(str(ev.get('date') or ''))} {_esc(ev.get('event') or '')}{_esc(est)}")
    return "\n".join(lines)


def build_news_section(macro_news: list, lang: str) -> str:
    t = LABELS[lang]
    header = t["s4"]
    if not macro_news:
        return f"{header}\n{t['no_news']}"

    key = "summary_zh" if lang == "zh" else "summary_en"
    lines = [header]
    for it in macro_news:
        summary = _esc(it.get(key) or "")
        source = _esc(it.get("source") or "")
        url = it.get("url")
        if url:
            link_text = "链接" if lang == "zh" else "link"
            lines.append(f"• {summary} <i>({source})</i> — <a href=\"{_esc(url, quote=True)}\">{link_text}</a>")
        else:
            lines.append(f"• {summary} <i>({source})</i>")
    return "\n".join(lines)


def build_focus_section(focus: str, lang: str) -> str:
    t = LABELS[lang]
    header = t["s5"]
    if not focus:
        return f"{header}\n{UNAVAILABLE}"
    return f"{header}\n💡 {_esc(focus)}"


def build_market_digest_messages(date_str: str, market: dict, calendar: dict,
                                  macro_news: list, focus: str, lang: str) -> list:
    header = LABELS[lang]["title"].format(date=_esc(date_str))
    sections = [
        build_indices_section(market, lang),
        build_global_section(market, lang),
        build_calendar_section(calendar, lang),
        build_news_section(macro_news, lang),
        build_focus_section(focus, lang),
    ]
    return pack_messages(header, sections)
