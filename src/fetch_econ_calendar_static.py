"""美股宏观日历：FOMC 利率决议、CPI、PPI、非农就业(NFP)等对大盘影响最大的几类事件。

Finnhub 免费层的 /calendar/economic 接口实测 403（见 fetch_economic_calendar.py，已弃用），
这里改用静态/规则数据源，不依赖任何需要付费或申请 key 的 API：
- FOMC 会议日期：美联储官网公布的年度日程，提前一年以上确定，基本不变。
- CPI / PPI 发布日期：BLS(美国劳工统计局) 提前公布的年度日程，只收录了公开搜索能确认到的月份，
  没查到确切日期的月份就不猜，宁可少显示也不要显示错日期。
- 非农就业(NFP)：BLS 惯例是每月第一个周五发布，用规则计算，不需要硬编码。

每年年初需要人工核对/更新一次 FOMC_MEETINGS_2026 / CPI_RELEASES_2026 / PPI_RELEASES_2026。
"""
from datetime import date, timedelta

LOOKAHEAD_DAYS = 3  # 今天 + 未来2天，早上发的时候能提前看到"这两天有什么大事"

# 每场 FOMC 会议是两天，(第一天, 第二天/公布决议当天)。来源：federalreserve.gov/monetarypolicy/fomccalendars.htm
FOMC_MEETINGS_2026 = [
    ("2026-01-27", "2026-01-28"),
    ("2026-03-17", "2026-03-18"),
    ("2026-04-28", "2026-04-29"),
    ("2026-06-16", "2026-06-17"),
    ("2026-07-28", "2026-07-29"),
    ("2026-09-15", "2026-09-16"),
    ("2026-10-27", "2026-10-28"),
    ("2026-12-08", "2026-12-09"),
]

# 来源：bls.gov 公布的 CPI 发布日程，只收录了确认到的月份
CPI_RELEASES_2026 = {
    "2026-01-13": "Dec 2025",
    "2026-02-13": "Jan 2026",
    "2026-03-11": "Feb 2026",
    "2026-04-10": "Mar 2026",
    "2026-05-12": "Apr 2026",
    "2026-07-14": "Jun 2026",
    "2026-08-12": "Jul 2026",
}

# 来源：bls.gov 公布的 PPI 发布日程
PPI_RELEASES_2026 = {
    "2026-01-14": "Dec 2025",
    "2026-01-30": "Jan 2026 (提前)",
    "2026-02-27": "Jan 2026",
    "2026-03-18": "Feb 2026",
    "2026-04-14": "Mar 2026",
    "2026-06-11": "May 2026",
    "2026-07-15": "Jun 2026",
    "2026-08-13": "Jul 2026",
    "2026-09-10": "Aug 2026",
    "2026-10-15": "Sep 2026",
    "2026-11-13": "Oct 2026",
    "2026-12-15": "Nov 2026",
}


def _first_friday(year: int, month: int) -> date:
    d = date(year, month, 1)
    offset = (4 - d.weekday()) % 7  # weekday(): 星期一=0 ... 星期五=4
    return d + timedelta(days=offset)


def _nfp_dates_near(today: date) -> list:
    """非农就业报告：每月第一个周五。只算今天所在月和下个月，够覆盖跨月的 lookahead 窗口。"""
    dates = []
    for month_offset in (0, 1):
        month = today.month + month_offset
        year = today.year + (1 if month > 12 else 0)
        month = ((month - 1) % 12) + 1
        dates.append(_first_friday(year, month))
    return dates


def get_upcoming_events(today: date = None) -> dict:
    today = today or date.today()
    window_end = today + timedelta(days=LOOKAHEAD_DAYS - 1)

    events = []

    for day1, day2 in FOMC_MEETINGS_2026:
        d1, d2 = date.fromisoformat(day1), date.fromisoformat(day2)
        if today <= d2 <= window_end or today <= d1 <= window_end:
            if today <= d1 <= window_end:
                events.append({"date": day1, "label_zh": "FOMC 会议第一天", "label_en": "FOMC Meeting Day 1"})
            events.append({"date": day2, "label_zh": "FOMC 利率决议公布", "label_en": "FOMC Rate Decision"})

    for day, ref_month in CPI_RELEASES_2026.items():
        d = date.fromisoformat(day)
        if today <= d <= window_end:
            events.append({"date": day, "label_zh": f"CPI 数据公布（{ref_month}）", "label_en": f"CPI Release ({ref_month})"})

    for day, ref_month in PPI_RELEASES_2026.items():
        d = date.fromisoformat(day)
        if today <= d <= window_end:
            events.append({"date": day, "label_zh": f"PPI 数据公布（{ref_month}）", "label_en": f"PPI Release ({ref_month})"})

    for d in _nfp_dates_near(today):
        if today <= d <= window_end:
            day = d.isoformat()
            events.append({"date": day, "label_zh": "非农就业报告(NFP)公布", "label_en": "Nonfarm Payrolls (NFP) Release"})

    events.sort(key=lambda e: e["date"])
    return {"available": True, "events": events}
