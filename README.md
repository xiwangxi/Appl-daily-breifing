# Daily Telegram Digests 🍎🌎

每天美股开盘前，自动推送两条结构化 Telegram 消息：

1. **US Market Daily**（慕尼黑本地时间约 6:30）—— 美股大盘速览、隔夜全球市场、经济日历、
   宏观新闻、今日市场关注点，中英双语（先发中文，再发英文），可以同时发给多个接收人。
2. **AAPL Daily Brief**（慕尼黑本地时间约 7:00）—— AAPL 个股的股价、公司新闻、供应链/生态
   动态、分析师评级与目标价、期权市场信号，只发给你自己。

5 分钟内看完，建立当天的交易判断依据。

**不构成投资建议，仅为个人信息整理工具。不做自动交易，只做信息聚合，只做每日一次定时推送。**

## 项目结构

```
config/
  tickers.yaml          # AAPL Daily 用的关联公司列表、新闻窗口、去重保留天数
  secrets.env.example   # 本地开发用的 key 模板，复制成 secrets.env 填真实值（已 gitignore）
src/
  fetch_price.py            # AAPL 股价速览（yfinance）
  fetch_news.py             # AAPL + 供应链新闻（Finnhub company-news + Google News RSS）
  fetch_analyst.py          # AAPL 分析师评级/目标价（yfinance）
  fetch_options.py          # AAPL 期权链/PCR/IV/max pain/异常大单（yfinance，免费）
  fetch_market_indices.py   # 大盘：标普/纳指/道指 + 期货 + 隔夜全球市场（yfinance）
  fetch_market_news.py      # 宏观新闻（Finnhub general news + Google News RSS 宏观关键词）
  fetch_economic_calendar.py # 经济日历，CPI/非农/FOMC等（Finnhub，可能不可用，不阻塞）
  summarize.py               # Claude API 摘要（AAPL 中文版 + 大盘中英双语版）
  build_message.py           # AAPL 消息拼装，HTML + 自动分段
  build_message_market.py    # 大盘消息拼装，中英双语 + 自动分段
  send_telegram.py           # 调 Telegram Bot API 发送
  cache.py                   # 通用新闻去重缓存（AAPL/大盘分别用不同文件）
  last_sent.py                # 记录每个 digest 今天发过没有，防止外部定时服务重复触发
main.py                       # AAPL Daily 入口
main_market.py                 # US Market Daily 入口
.github/workflows/daily_digest.yml   # 一个 workflow 里跑两个 digest（只走 workflow_dispatch，见下方「外部定时触发配置」）
data/seen_news.json           # AAPL 新闻去重缓存
data/seen_market_news.json    # 大盘新闻去重缓存
data/iv_history.json          # AAPL 期权 IV 历史，用于计算百分位
data/last_sent.json           # 每个 digest 最后发送日期，防重复
```

## 一、准备工作（需要你提供的东西）

### 1. Telegram Bot Token + 收件人 Chat ID（至少1个，最多2个）
1. Telegram 里搜索 `@BotFather`，发送 `/newbot`，按提示起名字，拿到形如
   `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` 的 Token。
2. 每个要接收消息的人都要**先给这个机器人发一条 `/start`**（让机器人"认识"他）。
3. 浏览器打开 `https://api.telegram.org/bot<TOKEN>/getUpdates`，从返回 JSON 里每个人
   对应的 `message.chat.id` 拿到各自的 Chat ID。
4. 你自己的 chat_id 填 `TELEGRAM_CHAT_ID`（AAPL Daily 和大盘 Daily 都会发给这个人，大盘
   Daily 中英文都发）；第二个人的 chat_id 填 `TELEGRAM_CHAT_ID_2`（**可选**，只有大盘 Daily
   会发给这个人，且**只发英文版**，不填就没有第二个接收人）。语言分配写死在
   `main_market.py` 的 `load_config()` 里，想改成别的组合直接改那几行代码即可。

### 2. 数据源 API Key
- **Finnhub**（新闻，免费额度够用）：https://finnhub.io/register
  （AAPL 的分析师评级/目标价/期权数据都用 yfinance 免费拿，经济日历用 Finnhub 的
  `/calendar/economic` 接口，如果这个接口在免费层不可用，大盘 Daily 那部分会显示
  "数据源暂不可用"，不影响其它板块）
- **Anthropic Claude API**（摘要，两个 digest 共用）：https://console.anthropic.com/settings/keys

### 3. 配置到 GitHub（推荐，免运维）
在仓库 **Settings → Secrets and variables → Actions → New repository secret**，添加：

| Secret 名 | 值 | 必填 |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | 第1步拿到的 token | 是 |
| `TELEGRAM_CHAT_ID` | 你自己的 chat id | 是 |
| `TELEGRAM_CHAT_ID_2` | 第二个接收人的 chat id | 否，只影响大盘 Daily 是否多发一份 |
| `FINNHUB_API_KEY` | Finnhub key | 是 |
| `ANTHROPIC_API_KEY` | Claude API key | 是 |

可选：在 **Variables** 里加 `CLAUDE_MODEL` 覆盖默认模型（默认 `claude-haiku-4-5-20251001`，
想要更强的归纳质量可以改成 Opus）。

### 4. 外部定时触发配置（必须，替代 GitHub 自带的 schedule）

GitHub Actions 自带的 `schedule` 定时触发在实测中完全不可靠——这个仓库上线后跨了好几个
工作日、cron 配置也确认没问题，但一次都没自动触发过，只有手动/API 触发（`workflow_dispatch`）
每次都成功。怀疑是 GitHub 对新账号/低活跃度仓库的定时任务有反滥用限制。所以改成用**外部免费
定时服务**在正确的本地时间，调用 GitHub API 触发 `workflow_dispatch`。

**Step 1：创建一个 GitHub Personal Access Token（PAT）**
1. 打开 `https://github.com/settings/personal-access-tokens/new`（fine-grained token）
2. Repository access 选 **Only select repositories** → 选这个仓库
3. Permissions 里找 **Actions**，设成 **Read and write**
4. 生成后复制 token（形如 `github_pat_xxxx`），这个只在外部定时服务里配置，**不要**提交到仓库

**Step 2：注册一个免费定时服务**，比如 https://cron-job.org（免费额度够用），创建两个 cron job：

| | 大盘 Daily | AAPL Daily |
|---|---|---|
| 触发时间 | 每个工作日 06:30，时区选 Europe/Berlin | 每个工作日 07:00，时区选 Europe/Berlin |
| 请求方式 | POST | POST |
| URL | `https://api.github.com/repos/xiwangxi/Appl-daily-breifing/actions/workflows/daily_digest.yml/dispatches` | 同左 |
| Headers | `Authorization: Bearer <你的PAT>`<br>`Accept: application/vnd.github+json`<br>`Content-Type: application/json` | 同左 |
| Body (raw JSON) | `{"ref":"main","inputs":{"digest":"market","scheduled":"true"}}` | `{"ref":"main","inputs":{"digest":"aapl","scheduled":"true"}}` |

注意 `inputs` 里的值必须是**字符串** `"true"`，不是 JSON 布尔值 `true`——这是 GitHub API 对
`workflow_dispatch` 输入参数的要求。选 Europe/Berlin 时区后，定时服务自己处理夏令时/冬令时切换，
不需要像原来那样手动算 UTC 偏移。

配置完用定时服务自带的"立即执行一次"功能测一下，去 GitHub 仓库的 Actions 页面确认有没有跑起来。

**手动测试**：仍然可以在 Actions 页面点 **Run workflow**，`digest` 默认 `both`（两个都跑），
`scheduled` 默认 `false`（跳过周末检查和去重，随时能跑，方便调试）。

## 二、本地测试

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp config/secrets.env.example config/secrets.env   # 填入真实 key，TELEGRAM_CHAT_ID_2 可留空
python main_market.py   # 大盘 Daily
python main.py           # AAPL Daily
```

本地运行时 `RUN_MODE` 默认是 `manual`，不受"是否到点"限制，随时跑随时发。

## 三、推送时间是怎么定的

大盘 Daily 目标是**慕尼黑本地时间 6:30**，AAPL Daily 是**7:00**（先看大盘宏观，再看个股），
由外部定时服务（见上面「外部定时触发配置」）在准确的本地时间调用 API 触发，不依赖 GitHub 自带
的 `schedule`。每个脚本自己只做一个兜底检查：`RUN_MODE=scheduled` 时跳过周末（美股不开盘）；
`data/last_sent.json` 记录每个 digest 今天发过没有，防止外部服务意外重复触发导致重复推送。
如果你想改成别的城市/时间，直接改外部定时服务里两个 cron job 的时区和时刻，代码不用动。

## 四、消息模板

**US Market Daily**（中文版 + English version，各自独立成一条或多条消息）：
```
🌎 US Market Daily — {date}

【一、大盘速览】标普/纳指/道指昨收+涨跌幅，盘前期货方向
【二、隔夜全球市场】日经/恒生/上证/DAX/富时 涨跌幅
【三、经济日历 & 重要事件（未来7天）】CPI/非农/FOMC等高影响力美国经济数据
【四、宏观新闻】Claude按重要性排序+中英文摘要+来源链接
【五、今日市场关注点】Claude基于以上信息生成的一句话总结
```

**AAPL Daily Brief**：
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

- **期权数据**：用 yfinance 抓 Yahoo Finance 的期权链，完全免费、不需要注册任何账号，但数据
  不是逐笔实时的，对开盘前晨报够用。
- **异常期权大单**：用启发式规则近似（单张合约当日成交量 ≥ 3倍未平仓量），不是 Unusual Whales
  那种基于逐笔成交方向判断的专业数据。
- **IV 历史百分位**：数据从项目上线那天开始每天积累到 `data/iv_history.json`，积累不满10个
  交易日之前，消息里会显示"历史数据积累中"。
- **经济日历**：用 Finnhub 的 `/calendar/economic` 接口，免费层是否包含这个接口不确定
  （其它几个"专属"接口之前实测被限制成付费），拿不到就整块标注"数据源暂不可用"，不阻塞
  大盘 Daily 的其它板块。
- **新闻摘要**：Claude 会基于标题+原始简介做真正的归纳整理，不是简单翻译标题——但如果
  Claude API 调用失败会降级成"按时间排序的原始英文标题"，这种情况"今日关注点"会明确
  提示"AI摘要暂不可用"。
- **去重**：AAPL 新闻和大盘宏观新闻分别用 `data/seen_news.json` / `data/seen_market_news.json`
  两个独立文件去重，保留天数由各自代码里的 `dedup_retention_days` 控制（默认7天），每次
  workflow 运行后自动 commit 回仓库。

## 六、调整关联公司列表 / 宏观关键词

- AAPL Daily 的关联公司：直接改 `config/tickers.yaml`，不用碰代码。非美股上市公司（比如
  富士康、大立光、华为）设置 `ticker: null` + `name_only: true` + `news_keywords: [...]`，
  只用于新闻关键词搜索。
- 大盘 Daily 的宏观新闻关键词：改 `src/fetch_market_news.py` 里的 `MACRO_KEYWORDS` 列表。
- 大盘 Daily 关注的指数：改 `src/fetch_market_indices.py` 里的 `US_INDICES` / `US_FUTURES` /
  `GLOBAL_INDICES` 列表。

## 七、后续可加的功能（不阻塞当前版本）

- 双向交互：回复消息触发机器人重新拉取某项数据
- 更精细的 Unusual Options Activity（接入付费数据源）
- 供应链公司也接入期权数据（目前期权模块只做 AAPL 本身）
- 经济日历如果 Finnhub 免费层不可用，可以换成 FRED API（美联储官方数据，免费但需要单独申请
  API key）
