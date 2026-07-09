# AAPL Daily Telegram Digest 🍎

每天美股开盘前，自动把 AAPL 的股价、公司新闻、供应链/生态动态、分析师评级与目标价、期权市场信号
拼成一条结构化消息推送到 Telegram，5 分钟内看完建立当天的交易判断依据。

**不构成投资建议，仅为个人信息整理工具。不做自动交易，只做信息聚合，只做每日一次定时推送。**

## 项目结构

```
config/
  tickers.yaml          # 关联公司列表、新闻窗口、去重保留天数——改这个文件不用碰代码
  secrets.env.example   # 本地开发用的 key 模板，复制成 secrets.env 填真实值（已 gitignore）
src/
  fetch_price.py        # 股价速览（yfinance）
  fetch_news.py         # 新闻（Finnhub company-news + Google News RSS）
  fetch_analyst.py      # 分析师评级/目标价（Finnhub）
  fetch_options.py      # 期权链/PCR/IV/max pain/异常大单启发式检测（Polygon.io）
  summarize.py          # Claude API 做新闻去重/排序/摘要 + 生成"今日关注点"
  build_message.py      # 拼 Telegram HTML 消息，超长自动按板块分段
  send_telegram.py      # 调 Telegram Bot API 发送
  cache.py               # 已推送新闻去重缓存
main.py                  # 串联以上所有模块的入口
.github/workflows/daily_digest.yml   # 定时触发（GitHub Actions cron）
data/seen_news.json      # 去重缓存（workflow 每次运行后自动 commit 回仓库）
data/iv_history.json     # IV 历史，用于计算隐含波动率的百分位
```

## 一、准备工作（需要你提供的东西）

### 1. Telegram Bot Token + Chat ID
1. Telegram 里搜索 `@BotFather`，发送 `/newbot`，按提示起名字，拿到形如
   `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` 的 Token。
2. 用你自己的账号给这个机器人发一条 `/start`（让它"认识"你）。
3. 浏览器打开 `https://api.telegram.org/bot<TOKEN>/getUpdates`，从返回 JSON 的
   `message.chat.id` 里拿到你的 Chat ID。

### 2. 数据源 API Key（都有免费额度）
- **Finnhub**（新闻 + 分析师数据）：https://finnhub.io/register
- **Polygon.io**（期权链/IV/PCR，Options Starter 免费套餐即可，数据约15分钟延迟）：
  https://polygon.io/dashboard/signup
- **Anthropic Claude API**（新闻摘要）：https://console.anthropic.com/settings/keys

### 3. 配置到 GitHub（推荐，免运维）
在仓库 **Settings → Secrets and variables → Actions → New repository secret**，添加：

| Secret 名 | 值 |
|---|---|
| `TELEGRAM_BOT_TOKEN` | 第1步拿到的 token |
| `TELEGRAM_CHAT_ID` | 第1步拿到的 chat id |
| `FINNHUB_API_KEY` | Finnhub key |
| `POLYGON_API_KEY` | Polygon key |
| `ANTHROPIC_API_KEY` | Claude API key |

可选：在 **Variables** 里加 `CLAUDE_MODEL` 覆盖默认模型（默认 `claude-haiku-4-5-20251001`，
想要更强的新闻归纳质量可以改成 Opus）。

**重要**：GitHub Actions 的 `schedule` 定时触发只在仓库的**默认分支**上生效。这个 workflow
文件合并到默认分支之前，定时推送不会自动运行（但你可以在 Actions 页面手动点 "Run workflow" 测试）。

## 二、本地测试

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp config/secrets.env.example config/secrets.env   # 填入真实 key
python main.py
```

本地运行时 `RUN_MODE` 默认是 `manual`，不受"是否到点"限制，随时跑随时发。

## 三、推送时间是怎么定的

你要的是**慕尼黑本地时间早上 7 点**醒来看到消息。欧盟和美国的夏令时切换日期不完全一致，
为了不用每年手动改 cron，`daily_digest.yml` 里设了两个 UTC 触发点（工作日 5:00 和 6:00 UTC），
`main.py` 在 `RUN_MODE=scheduled` 时会检查当前是否真的是 `Europe/Berlin` 时区的 7 点，
不是的话直接跳过退出——所以虽然 workflow 每天触发两次，实际只会真正发送一次。
如果你想改成别的城市/时间，改 `main.py` 里的 `TARGET_LOCAL_TZ` 和 `TARGET_LOCAL_HOUR` 即可。

## 四、消息模板

```
🍎 AAPL Daily Brief — {date}

【一、股价速览】昨收/涨跌幅/盘前盘后/近5日走势/支撑阻力/P-E/临近事件倒计时
【二、苹果公司自身新闻】近48小时，Claude按重要性排序+一句话摘要+来源链接
【三、供应链 & 生态相关公司动态】同上，覆盖 config/tickers.yaml 里配置的公司
【四、分析师观点 & 估值】评级变化/目标价均值-最高-最低/买卖评级分布
【五、期权市场异动】Put/Call Ratio/IV及历史百分位/Max Pain/异常大单（启发式）
【六、今日关注点】Claude基于以上信息生成的一句话总结
```

单条消息超过 Telegram 的 ~4096 字符限制时会自动按板块拆成多条依次发送，不会硬切断句子。

## 五、已知限制 / MVP 说明

- **期权数据**：Polygon.io 免费/基础套餐约有15分钟延迟，对开盘前晨报够用，但不是实时的。
- **异常期权大单**：用启发式规则近似（单张合约当日成交量 ≥ 3倍未平仓量），不是 Unusual Whales
  那种基于逐笔成交方向判断的专业数据。如果之后想接入 Unusual Whales API，只需要在
  `src/fetch_options.py` 里加一个新的数据源函数，`build_message.py` 的展示逻辑不用改。
- **IV 历史百分位**：数据从项目上线那天开始每天积累到 `data/iv_history.json`，积累不满10个
  交易日之前，消息里会显示"历史数据积累中"。
- **分析师目标价/评级**：依赖 Finnhub 免费额度，个别接口在免费层可能不稳定，拿不到时消息里
  会标注"数据源暂不可用"，不影响其它板块正常发送。
- **去重**：`data/seen_news.json` 记录已推送过的新闻链接，保留天数由 `config/tickers.yaml`
  的 `dedup_retention_days` 控制（默认7天），每次 workflow 运行后自动 commit 回仓库。

## 六、调整关联公司列表

直接改 `config/tickers.yaml`，不用碰代码。非美股上市公司（比如富士康、大立光、华为）设置
`ticker: null` + `name_only: true` + `news_keywords: [...]`，只用于新闻关键词搜索。

## 七、后续可加的功能（不阻塞当前版本）

- 双向交互：回复消息触发机器人重新拉取某项数据
- 更精细的 Unusual Options Activity（接入付费数据源）
- 供应链公司也接入期权数据（目前期权模块只做 AAPL 本身）
