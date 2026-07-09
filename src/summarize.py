"""用 Claude API 对当天抓到的新闻做去重、按重要性排序、压缩成一句话摘要，并生成"今日关注点"。

如果 Claude API 调用失败（没配 key / 网络问题 / 超时），降级为「按标题去重 + 按时间排序」
的朴素规则，保证推送流程不因为这一步失败而完全发不出去。
"""
import json
import os

SYSTEM_PROMPT = """你是一名苹果(AAPL)股票/期权交易员的助理。给你一批新闻条目(JSON数组，每条含
title/url/source/ticker/published)，请完成：
1. 去重：同一事件的多篇报道只保留信息量最大/来源最权威的一条。
2. 按对 AAPL 股价/期权交易的重要性从高到低排序。
3. 每条压缩成一句中文摘要（不超过40字），客观陈述事实，不要加你自己的推测或投资建议。
4. 最多保留 aapl_news 8 条、supply_chain_news 6 条。
5. 基于这些新闻 + 我给你的股价/期权/分析师数据，生成一句"今日关注点"（不超过50字中文），
   点出今天开盘前最值得注意的1-2件事。

严格只输出如下 JSON，不要有多余文字：
{
  "aapl_news": [{"summary": "...", "source": "...", "url": "...", "ticker": "AAPL"}],
  "supply_chain_news": [{"summary": "...", "source": "...", "url": "...", "ticker": "TSM"}],
  "today_focus": "..."
}
"""


def fallback_summary(aapl_news: list, supply_chain_news: list) -> dict:
    def dedupe_and_trim(items, limit):
        seen_titles = set()
        out = []
        for it in sorted(items, key=lambda x: x.get("published") or "", reverse=True):
            title = (it.get("title") or "").strip()
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)
            out.append({
                "summary": title[:60],
                "source": it.get("source"),
                "url": it.get("url"),
                "ticker": it.get("ticker"),
            })
            if len(out) >= limit:
                break
        return out

    return {
        "aapl_news": dedupe_and_trim(aapl_news, 8),
        "supply_chain_news": dedupe_and_trim(supply_chain_news, 6),
        "today_focus": "（AI摘要暂不可用，以上为按时间排序的原始新闻标题）",
    }


def summarize_digest(aapl_news: list, supply_chain_news: list, context: dict, api_key: str, model: str) -> dict:
    if not api_key:
        return fallback_summary(aapl_news, supply_chain_news)

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        user_payload = {
            "aapl_news": [
                {"title": n.get("title"), "url": n.get("url"), "source": n.get("source"),
                 "ticker": n.get("ticker"), "published": n.get("published")}
                for n in aapl_news
            ],
            "supply_chain_news": [
                {"title": n.get("title"), "url": n.get("url"), "source": n.get("source"),
                 "ticker": n.get("ticker"), "published": n.get("published")}
                for n in supply_chain_news
            ],
            "context": context,
        }
        message = client.messages.create(
            model=model,
            max_tokens=2000,
            temperature=0,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)}],
        )
        text = "".join(block.text for block in message.content if hasattr(block, "text"))
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
        result = json.loads(text)
        result.setdefault("aapl_news", [])
        result.setdefault("supply_chain_news", [])
        result.setdefault("today_focus", "")
        return result
    except Exception as e:
        print(f"[summarize] Claude summarization failed, falling back to raw headlines: {e}")
        return fallback_summary(aapl_news, supply_chain_news)
