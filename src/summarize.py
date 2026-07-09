"""用 Claude API 对当天抓到的新闻做去重、按重要性排序、压缩成一句话摘要，并生成"今日关注点"。

如果 Claude API 调用失败（没配 key / 网络问题 / 超时），降级为「按标题去重 + 按时间排序」
的朴素规则，保证推送流程不因为这一步失败而完全发不出去。
"""
import json
import os

# 发给 Claude 去重/排序前的原始条数上限（按最近发布时间截取），
# 防止关联公司一多、每条新闻都带简介时把 prompt 撑爆。
MAX_RAW_ITEMS_PER_SECTION = 40


def _cap_recent(items: list, limit: int) -> list:
    return sorted(items, key=lambda x: x.get("published") or "", reverse=True)[:limit]

SYSTEM_PROMPT = """你是一名苹果(AAPL)股票/期权交易员的助理。给你一批新闻条目(JSON数组，每条含
id/title/summary/ticker/published，summary 是原始报道的简介，可能为空)，请完成：
1. 去重：同一事件的多篇报道只保留信息量最大/来源最权威的一条。
2. 按对 AAPL 股价/期权交易的重要性从高到低排序。
3. 每条写一句**中文**摘要（40-70字），要提炼出具体信息（谁、做了什么、影响是什么），
   让读者不点链接也能看懂发生了什么事——不是把英文标题直译一遍，而是基于 title 和 summary
   综合归纳出实质内容。客观陈述事实，不要加你自己的推测或投资建议。
4. 最多保留 aapl_news 8 条、supply_chain_news 6 条。
5. 基于这些新闻 + 我给你的股价/期权/分析师数据，生成一句"今日关注点"（不超过50字中文），
   点出今天开盘前最值得注意的1-2件事。
6. 全部输出必须是中文，包括 summary 和 today_focus。

重要：输出里只带 id 和 summary，不要照抄 url/source/ticker（我会用 id 在我这边查回原始数据）。
严格只输出如下 JSON，不要有多余文字：
{
  "aapl_news": [{"id": "a0", "summary": "..."}],
  "supply_chain_news": [{"id": "s3", "summary": "..."}],
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

        aapl_capped = _cap_recent(aapl_news, MAX_RAW_ITEMS_PER_SECTION)
        supply_capped = _cap_recent(supply_chain_news, MAX_RAW_ITEMS_PER_SECTION)
        id_lookup = {}
        for i, n in enumerate(aapl_capped):
            id_lookup[f"a{i}"] = n
        for i, n in enumerate(supply_capped):
            id_lookup[f"s{i}"] = n

        client = anthropic.Anthropic(api_key=api_key)
        user_payload = {
            "aapl_news": [
                {"id": f"a{i}", "title": n.get("title"), "summary": n.get("summary"),
                 "ticker": n.get("ticker"), "published": n.get("published")}
                for i, n in enumerate(aapl_capped)
            ],
            "supply_chain_news": [
                {"id": f"s{i}", "title": n.get("title"), "summary": n.get("summary"),
                 "ticker": n.get("ticker"), "published": n.get("published")}
                for i, n in enumerate(supply_capped)
            ],
            "context": context,
        }
        message = client.messages.create(
            model=model,
            max_tokens=3000,
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
        raw_result = json.loads(text)

        def _resolve(entries):
            resolved = []
            for e in entries or []:
                original = id_lookup.get(e.get("id"))
                if not original:
                    continue
                resolved.append({
                    "summary": e.get("summary"),
                    "source": original.get("source"),
                    "url": original.get("url"),
                    "ticker": original.get("ticker"),
                })
            return resolved

        return {
            "aapl_news": _resolve(raw_result.get("aapl_news")),
            "supply_chain_news": _resolve(raw_result.get("supply_chain_news")),
            "today_focus": raw_result.get("today_focus", ""),
        }
    except Exception as e:
        print(f"[summarize] Claude summarization failed, falling back to raw headlines: {e}")
        return fallback_summary(aapl_news, supply_chain_news)
