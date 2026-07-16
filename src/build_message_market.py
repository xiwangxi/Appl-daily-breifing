"""拼装美股大盘宏观 Daily 的 Telegram HTML 消息，中英双语。复用 build_message.py 的分段打包逻辑。"""
from html import escape as _esc

from build_message import UNAVAILABLE, pack_messages

LABELS = {
    "zh": {
        "title": "🌎 <b>US Market Daily</b> — {date}",
        "s1": "【一、大盘速览】",
        "s2": "【二、隔夜全球市场（日韩台重点关注）】",
        "s3": "【三、半导体板块聚焦】",
        "s4": "【四、近期重要事件（美联储/经济数据/财报）】",
        "s5": "【五、宏观新闻】",
        "s6": "【六、今日市场关注点】",
        "no_events": "未来3天内没有查到静态日历收录的重要事件",
        "no_news": "近48小时暂无重要宏观新闻",
    },
    "en": {
        "title": "🌎 <b>US Market Daily</b> — {date} (EN)",
        "s1": "<b>1. US Market Snapshot</b>",
        "s2": "<b>2. Overnight Global Markets (Japan/Korea/Taiwan focus)</b>",
        "s3": "<b>3. Semiconductor Sector Watch</b>",
        "s4": "<b>4. Upcoming Events (Fed/Data/Earnings)</b>",
        "s5": "<b>5. Macro News</b>",
        "s6": "<b>6. Today's Market Focus</b>",
        "no_events": "No events found in the static calendar for the next 3 days",
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


def build_semiconductor_section(semi: dict, lang: str) -> str:
    t = LABELS[lang]
    header = t["s3"]
    if not semi or not semi.get("available"):
        return f"{header}\n{UNAVAILABLE}"

    lines = [header]
    for s in semi.get("stocks", []):
        val = f"{s['last']:,.2f}" if s.get("last") is not None else "N/A"
        lines.append(f"{_esc(_label(s, lang))}: {val} ({_fmt_pct(s.get('change_pct'))})")
    return "\n".join(lines)


def build_events_section(calendar: dict, earnings: list, lang: str) -> str:
    """合并宏观日历(FOMC/CPI/PPI/NFP) + 自选清单财报，按日期排序，未来3天内的事件。"""
    t = LABELS[lang]
    header = t["s4"]

    entries = []
    if calendar and calendar.get("available"):
        for ev in calendar.get("events", []):
            label = ev.get("label_zh" if lang == "zh" else "label_en") or ""
            entries.append((ev.get("date") or "", label))
    for e in earnings or []:
        prefix = "财报：" if lang == "zh" else "Earnings: "
        entries.append((e.get("date") or "", f"{prefix}{e.get('ticker')}"))

    if not entries:
        return f"{header}\n{t['no_events']}"

    entries.sort(key=lambda x: x[0])
    lines = [header]
    for d, label in entries:
        lines.append(f"• {_esc(d)} {_esc(label)}")
    return "\n".join(lines)


def build_news_section(macro_news: list, lang: str) -> str:
    t = LABELS[lang]
    header = t["s5"]
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
    header = t["s6"]
    if not focus:
        return f"{header}\n{UNAVAILABLE}"
    return f"{header}\n💡 {_esc(focus)}"


def build_market_digest_messages(date_str: str, market: dict, semi: dict, calendar: dict,
                                  earnings: list, macro_news: list, focus: str, lang: str) -> list:
    header = LABELS[lang]["title"].format(date=_esc(date_str))
    sections = [
        build_indices_section(market, lang),
        build_global_section(market, lang),
        build_semiconductor_section(semi, lang),
        build_events_section(calendar, earnings, lang),
        build_news_section(macro_news, lang),
        build_focus_section(focus, lang),
    ]
    return pack_messages(header, sections)
