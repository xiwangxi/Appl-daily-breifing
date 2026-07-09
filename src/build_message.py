"""按模板拼装 Telegram HTML 消息，超过约4096字符自动按板块分段发送（不在句子中间硬切）。"""
from html import escape as _esc

TELEGRAM_LIMIT = 4096
SAFETY_MARGIN = 100  # 留一点余量给 Telegram 自己的开销
MAX_MSG_LEN = TELEGRAM_LIMIT - SAFETY_MARGIN

UNAVAILABLE = "⚠️ 数据源暂不可用"


def _fmt_pct(v):
    if v is None:
        return "N/A"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.2f}%"


def _fmt_num(v, prefix="", suffix="", digits=2):
    if v is None:
        return "N/A"
    return f"{prefix}{v:.{digits}f}{suffix}"


def build_header(date_str: str) -> str:
    return f"🍎 <b>AAPL Daily Brief</b> — {_esc(date_str)}"


def build_price_section(price: dict) -> str:
    if not price or price.get("last_close") is None:
        return f"<b>【一、股价速览】</b>\n{UNAVAILABLE}"

    lines = ["<b>【一、股价速览】</b>"]
    change_str = _fmt_pct(price.get("change_pct"))
    lines.append(f"昨收: <b>${_fmt_num(price.get('last_close'))}</b> ({change_str})")

    pre = price.get("pre_market_price")
    post = price.get("post_market_price")
    if pre:
        lines.append(f"盘前: ${_fmt_num(pre)} ({_fmt_pct(price.get('pre_market_change_pct'))})")
    if post:
        lines.append(f"盘后: ${_fmt_num(post)} ({_fmt_pct(price.get('post_market_change_pct'))})")

    five_day = price.get("five_day") or []
    if five_day:
        trend = " → ".join(f"${d['close']}" for d in five_day)
        lines.append(f"近5日: {_esc(trend)}")
    if price.get("support") and price.get("resistance"):
        lines.append(f"关键区间: 支撑 ${price['support']} / 阻力 ${price['resistance']}")

    pe_ttm, pe_fwd = price.get("pe_ttm"), price.get("pe_forward")
    if pe_ttm or pe_fwd:
        lines.append(f"P/E: TTM {_fmt_num(pe_ttm, digits=1)} / Forward {_fmt_num(pe_fwd, digits=1)}")

    events = price.get("upcoming_events") or []
    for ev in events:
        lines.append(f"⏰ {ev['days_left']}天后: {_esc(ev['type'])} ({ev['date']})")

    return "\n".join(lines)


def _format_news_items(items: list) -> list:
    lines = []
    for it in items:
        summary = _esc(it.get("summary") or "")
        source = _esc(it.get("source") or "")
        url = it.get("url")
        ticker = it.get("ticker")
        prefix = f"[{_esc(ticker)}] " if ticker and ticker != "AAPL" else ""
        if url:
            lines.append(f"• {prefix}{summary} <i>({source})</i> — <a href=\"{_esc(url, quote=True)}\">链接</a>")
        else:
            lines.append(f"• {prefix}{summary} <i>({source})</i>")
    return lines


def build_aapl_news_section(news: list) -> str:
    header = "<b>【二、苹果公司自身新闻】</b>"
    if not news:
        return f"{header}\n（近48小时暂无重要更新，或{UNAVAILABLE}）"
    return "\n".join([header] + _format_news_items(news))


def build_supply_chain_section(news: list) -> str:
    header = "<b>【三、供应链 & 生态相关公司动态】</b>"
    if not news:
        return f"{header}\n（近48小时暂无重要更新，或{UNAVAILABLE}）"
    return "\n".join([header] + _format_news_items(news))


def build_analyst_section(analyst: dict) -> str:
    header = "<b>【四、分析师观点 & 估值】</b>"
    if not analyst or not analyst.get("available"):
        return f"{header}\n{UNAVAILABLE}"

    lines = [header]
    changes = analyst.get("recent_changes") or []
    if changes:
        for c in changes[:5]:
            action_emoji = {"up": "⬆️", "down": "⬇️"}.get(c.get("action"), "➡️")
            grade = f"{_esc(c.get('from_grade') or '')} → {_esc(c.get('to_grade') or '')}".strip(" →")
            lines.append(f"{action_emoji} <b>{_esc(c.get('firm') or 'N/A')}</b>: {grade}")
    else:
        lines.append("近7日无评级变化")

    pt = analyst.get("price_target") or {}
    if pt.get("target_mean"):
        lines.append(
            f"目标价: 均值 ${_fmt_num(pt.get('target_mean'))}"
            f"（最高 ${_fmt_num(pt.get('target_high'))} / 最低 ${_fmt_num(pt.get('target_low'))}）"
        )

    rec = analyst.get("recommendation") or {}
    if rec.get("strong_buy") is not None:
        lines.append(
            f"评级分布: 强买{rec.get('strong_buy', 0)} 买{rec.get('buy', 0)} "
            f"持有{rec.get('hold', 0)} 卖{rec.get('sell', 0)} 强卖{rec.get('strong_sell', 0)}"
        )

    return "\n".join(lines)


def build_options_section(options: dict) -> str:
    header = "<b>【五、期权市场异动】</b>"
    if not options or not options.get("available"):
        return f"{header}\n{UNAVAILABLE}"

    lines = [header]
    if options.get("pcr_volume") is not None:
        lines.append(f"Put/Call Ratio (成交量): {options['pcr_volume']}")
    if options.get("pcr_oi") is not None:
        lines.append(f"Put/Call Ratio (未平仓量): {options['pcr_oi']}")
    if options.get("atm_iv") is not None:
        pct = options.get("iv_percentile")
        pct_str = f"，历史百分位 {pct}%" if pct is not None else "（历史数据积累中，暂无百分位）"
        lines.append(f"平值隐含波动率(IV): {options['atm_iv']}%{pct_str}")
    if options.get("max_pain_strike") is not None:
        lines.append(f"Max Pain 行权价: ${options['max_pain_strike']}")

    unusual = options.get("unusual_activity") or []
    if unusual:
        lines.append("异常大单（成交量≥3倍未平仓量，启发式检测，仅供参考）:")
        for u in unusual:
            direction = "📈 Call" if u["type"] == "call" else "📉 Put"
            lines.append(
                f"  {direction} ${u['strike']} 到期{u['expiration']} "
                f"量{u['volume']}/OI{u['open_interest']} 约${u['notional']:,}"
            )
    else:
        lines.append("暂未检测到明显异常大单")

    return "\n".join(lines)


def build_focus_section(focus: str) -> str:
    header = "<b>【六、今日关注点】</b>"
    if not focus:
        return f"{header}\n{UNAVAILABLE}"
    return f"{header}\n💡 {_esc(focus)}"


def _split_long_section(text: str, limit: int) -> list:
    """单个板块本身就超长时的兜底：按行切，不切断单行。"""
    lines = text.split("\n")
    chunks, current = [], ""
    for line in lines:
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            if current:
                chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def pack_messages(header: str, sections: list) -> list:
    """把各板块贪心打包进尽量少的消息里，每条不超过 Telegram 长度限制，不在板块中间硬切。"""
    messages = []
    current = header

    for section in sections:
        candidate = f"{current}\n\n{section}"
        if len(candidate) <= MAX_MSG_LEN:
            current = candidate
            continue

        # 当前消息已经放不下这个板块了，先把当前消息收尾
        if current.strip() and current.strip() != header.strip():
            messages.append(current)
            current = header

        candidate = f"{current}\n\n{section}"
        if len(candidate) <= MAX_MSG_LEN:
            current = candidate
        else:
            # 单个板块自己就超长，强制拆分
            for chunk in _split_long_section(section, MAX_MSG_LEN - len(header) - 4):
                messages.append(f"{current}\n\n{chunk}" if current else chunk)
                current = header

    if current.strip() and current.strip() != header.strip():
        messages.append(current)

    return messages if messages else [header]


def build_digest_messages(date_str: str, price: dict, aapl_news: list, supply_chain_news: list,
                           analyst: dict, options: dict, focus: str) -> list:
    header = build_header(date_str)
    sections = [
        build_price_section(price),
        build_aapl_news_section(aapl_news),
        build_supply_chain_section(supply_chain_news),
        build_analyst_section(analyst),
        build_options_section(options),
        build_focus_section(focus),
    ]
    return pack_messages(header, sections)
