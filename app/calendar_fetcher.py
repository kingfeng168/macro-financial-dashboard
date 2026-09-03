# -*- coding: utf-8 -*-
"""Calendar actual-value fetcher.

Provides pluggable, source-aware fetching of economic calendar actual values.
Supports two event types:
  - numeric:    macro data releases (CPI, retail sales, claims, etc.)
  - speech:     central-bank official speeches (no single numeric actual)

Usage:
    from calendar_fetcher import fetch_calendar_actuals
    updated = fetch_calendar_actuals(daily_data_dict)
    # updated["economic_calendar"]["upcoming"][i]["actual"] may now hold a value

The module is intentionally stdlib-only; external search is delegated to the
report-generation phase (or an offline script) so that live_server.py stays
fast and does not block HTTP requests with network calls.
"""
import json, os, re, time
from datetime import datetime, timezone, timedelta

DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.environ.get("WORKBUDDY_DATA_DIR", DIR)
CACHE_FILE = os.path.join(CACHE_DIR, ".calendar_fetcher_cache.json")
CACHE_TTL_SECONDS = 600  # 10 minutes

# Event type hints used when actual is null after publish time.
EVENT_TYPES = {"numeric", "speech", "meeting", "report"}

# Hard-coded fallback actuals for the current reporting window.
# These are verified by external search and refreshed nightly.
_FALLBACK_ACTUALS = [
    {
        "match": {"country": "日本", "event": "7月核心CPI年率", "time": "08-21 07:30"},
        "actual": "1.8%",
        "previous": "1.6%",
        "note": "日本总务省8/21公布；剔除生鲜食品后核心CPI同比1.8%，符合预期，前值由统计口径显示1.6%",
        "type": "numeric",
    },
    {
        "match": {"country": "英国", "event": "7月零售销售月率", "time": "08-21 14:00"},
        "actual": "-0.5%",
        "previous": "0.7%",  # revised from 1.0%
        "note": "英国国家统计局8/21公布；7月季调后零售销售月率-0.5%符合预期，前值由1.0%修正为0.7%",
        "type": "numeric",
    },
    {
        "match": {"country": "澳洲", "event": "澳洲联储主席Bullock讲话", "time": "08-21 07:00"},
        "actual": "讲话事件",
        "note": "Bullock最新公开表态强调通胀仍高于2-3%目标，必要时准备好再次加息；政策路径取决于数据",
        "type": "speech",
    },
    {
        "match": {"country": "欧洲央行", "event": "管委Sleijpen讲话", "time": "08-21 07:30"},
        "actual": "讲话事件",
        "note": "Sleijpen近期强调需密切监测通胀预期，防范中东冲突引发的第二轮效应，政策将取决于整体通胀前景",
        "type": "speech",
    },
    {
        "match": {"country": "法国", "event": "8月制造业PMI初值", "time": "08-21 15:15"},
        "actual": "51.5",
        "forecast": "50.0",
        "previous": "49.8",
        "note": "法国8月制造业PMI初值51.5，高于预期的50.0与前值49.8，重返扩张区间；服务业PMI降至48.4，综合PMI降至48.8",
        "type": "numeric",
    },
    {
        "match": {"country": "德国", "event": "8月制造业PMI初值", "time": "08-21 15:30"},
        "actual": "54.1",
        "forecast": "52.0",
        "previous": "52.2",
        "note": "德国8月制造业PMI初值54.1，远超预期的52.0，创2022年5月以来最高；服务业PMI降至48.5，综合PMI降至51.0",
        "type": "numeric",
    },
    {
        "match": {"country": "欧元区", "event": "8月综合PMI初值", "time": "08-21 16:00"},
        "actual": "52.1",
        "forecast": "51.7",
        "previous": "52.0",
        "note": "欧元区8月综合PMI初值52.1，高于预期的51.7与前值52.0，为2025年11月以来最高；制造业PMI 52.8，服务业PMI 51.7",
        "type": "numeric",
    },
    {
        "match": {"country": "英国", "event": "8月制造业/服务业PMI初值", "time": "08-21 16:30"},
        "actual": "制造业51.5 / 服务业52.8 / 综合52.5",
        "forecast": "制造业51.5 / 服务业51.8 / 综合51.6",
        "previous": "制造业51.9 / 服务业52.1 / 综合52.2",
        "note": "英国8月制造业PMI初值51.5符合预期，服务业PMI初值52.8高于预期51.8，综合PMI初值52.5创4个月新高",
        "type": "numeric",
    },
{
    "match": {
        "country": "德国",
        "event": "8月IFO商业景气指数",
        "time": "08-24 16:00"
    },
    "actual": "88.8",
    "forecast": "87.2",
    "previous": "86.7",
    "note": "Ifo 8/25公布：商业景气指数88.8（预期87.2，前值86.7，为2025年8月以来最高），连续第四个月回升；现况分项88.5、预期分项89.1",
    "type": "numeric"
},
{
    "match": {
        "country": "欧元区",
        "event": "8月消费者信心指数终值",
        "time": "08-24 17:00"
    },
    "actual": "-15.5",
    "forecast": "-16.3",
    "previous": "-15.9",
    "note": "欧盟委员会8/21闪估：欧元区8月消费者信心-15.5（预期-16.3，前值7月-15.9）；终值将于08-28公布，此处取已发布的8月闪估值",
    "type": "numeric"
},
{
    "match": {
        "country": "美国",
        "event": "7月芝加哥联储全国活动指数",
        "time": "08-24 20:30"
    },
    "actual": "-0.08",
    "forecast": "0.05",
    "previous": "0.06",
    "note": "芝加哥联储8/24公布：CFNAI 7月-0.08（前值6月+0.06，预期0.05）；负值表明经济低于趋势增长，生产与个人消费分项转负",
    "type": "numeric"
},
{
    "match": {
        "country": "美国",
        "event": "7月耐用品订单月率",
        "time": "08-25 20:30"
    },
    "actual": "-2.8%",
    "forecast": "-3.8%",
    "previous": "0.3%",
    "note": "美国普查局8/25公布：7月耐用品订单月率-2.8%（预期-3.8%，前值6月+0.3%）；扣除运输+1.1%，非国防飞机及零件-32.7%，制造业订单-4%",
    "type": "numeric"
},
{
    "match": {
        "country": "美国",
        "event": "6月FHFA房价指数月率",
        "time": "08-25 21:00"
    },
    "actual": "0.0%",
    "forecast": "0.1%",
    "previous": "0.3%",
    "note": "FHFA 8/25公布：6月房价指数环比持平0.0%（预期+0.1%，前值5月+0.3%）；同比+2.3%",
    "type": "numeric"
},
{
    "match": {
        "country": "美国",
        "event": "6月S&P/CS20座大城市房价年率",
        "time": "08-25 21:00"
    },
    "actual": "2.1%",
    "forecast": "1.7%",
    "previous": "1.6%",
    "note": "S&P/Cotality 8/25公布：20城综合房价同比+2.1%（预期+1.7%，前值5月+1.6%）；全国指数+1.5%，芝加哥+6.9%领涨，西雅图-2.0%领跌",
    "type": "numeric"
},
{
    "match": {
        "country": "美国",
        "event": "8月谘商会消费者信心指数",
        "time": "08-25 22:00"
    },
    "actual": "89.4",
    "forecast": "90.2",
    "previous": "90.2",
    "note": "谘商会8/25公布：消费者信心指数89.4（预期90.2，前值7月由90.8下修至90.2），连续第二月下滑创7个月新低；现况分项121.2(+6.8)，预期分项68.2(-5.8)",
    "type": "numeric"
},
{
    "match": {
        "country": "澳大利亚",
        "event": "7月加权CPI年率",
        "time": "08-26 09:30"
    },
    "actual": "3.5%",
    "forecast": "3.3%",
    "previous": "3.8%",
        "note": "ABS 8/26公布：7月CPI同比+3.5%（预期+3.3%，前值6月+3.8%），环比+1.0%；截尾均值同比+3.6%（前值3.6%，预期3.5%），高于预期，澳央行9月加息概率上升",
        "type": "numeric"
}
]

# External, machine-maintained fallback store. Populated by the nightly backfill
# automation (via WebSearch + add_calendar_actual.py). Kept as a separate JSON so
# the curated list above is NEVER regex-edited -- that was the cause of the
# historic '},,' SyntaxError that only surfaced on process restart.
def _load_extra_fallback():
    path = os.path.join(DIR, "calendar_actuals_extra.json")
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []

_EXTRA_FALLBACKS = _load_extra_fallback()
_ALL_FALLBACKS = _FALLBACK_ACTUALS + _EXTRA_FALLBACKS



def _now_bj():
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=8)


def _event_dt(curr_date, ev_time):
    """Parse 'MM-DD HH:MM' into datetime using curr_date's year."""
    try:
        year = curr_date.split("-")[0]
        return datetime.strptime(f"{year}-{ev_time}", "%Y-%m-%d %H:%M")
    except Exception:
        return None


def _matches(item, pattern):
    """Check if calendar item matches a fallback pattern."""
    for k, v in pattern.items():
        if item.get(k) != v:
            return False
    return True


def _load_cache():
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
            if cache.get("ts", 0) + CACHE_TTL_SECONDS > time.time():
                return cache.get("data", {})
    except Exception:
        pass
    return {}


def _save_cache(data):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "data": data}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _apply_fallback(item, cache):
    """Apply hard-coded fallback actuals and cached values."""
    key = (item.get("time", ""), item.get("country", ""), item.get("event", ""))
    if key in cache:
        cached = cache[key]
        item["actual"] = cached.get("actual")
        if cached.get("previous"):
            item["previous"] = cached["previous"]
        if cached.get("forecast"):   # 2026-09-02: 外部核实条目可能含修正后预期值
            item["forecast"] = cached["forecast"]
        if cached.get("note"):
            item["note"] = cached["note"]
        if cached.get("type"):
            item["event_type"] = cached["type"]
        return True

    for fb in _ALL_FALLBACKS:
        if _matches(item, fb["match"]):
            item["actual"] = fb["actual"]
            item["actual_source"] = "external_verified"
            if fb.get("previous"):
                item["previous"] = fb["previous"]
            if fb.get("forecast"):   # 2026-09-02: 传播修正后预期值(如 ISM 55.2)
                item["forecast"] = fb["forecast"]
            item["note"] = fb.get("note", item.get("note", ""))
            item["event_type"] = fb.get("type", "numeric")
            cache[key] = fb
            return True
    return False


def fetch_calendar_actuals(data, use_cache=True):
    """Return a new data dict with calendar actuals filled from fallback/cache.

    Only fills items whose publish time has already passed and whose actual is
    still null/missing. Speech-type events receive a descriptive '讲话事件' tag
    instead of a numeric value.
    """
    data = json.loads(json.dumps(data))  # deep copy
    cal = data.get("economic_calendar", {})
    curr_date = cal.get("curr_date", "") or _now_bj().strftime("%Y-%m-%d")
    cache = _load_cache() if use_cache else {}
    now = _now_bj()
    touched = False

    for it in cal.get("released", []) + cal.get("upcoming", []):
        tstr = it.get("time", "")
        # 待定 or unparseable: cannot fetch a numeric actual
        if "待定" in tstr:
            continue
        dt = _event_dt(curr_date, tstr)
        if dt is None:
            continue
        # Only try to backfill already-published events
        if dt > now:
            continue
        actual = it.get("actual")
        if actual is None or actual == "" or "待取数" in str(actual) or "讲话事件" in str(actual):
            if _apply_fallback(it, cache):
                touched = True
            continue
        # 2026-09-02: actual 已存在的事件, 仍用外部人工核实条目的权威 forecast/previous
        # 做一致性校正(原逻辑只补 actual 导致 ISM/英欧PMI 等显示旧错预期值)
        for fb in _EXTRA_FALLBACKS:
            if not _matches(it, fb["match"]):
                continue
            for k in ("forecast", "previous"):
                if fb.get(k) and it.get(k) != fb[k]:
                    it[k] = fb[k]
                    touched = True
            break

    if touched and use_cache:
        _save_cache(cache)
    return data


def classify_event_type(item):
    """Heuristically classify an event as numeric/speech/meeting/report."""
    event = item.get("event", "")
    lower = event.lower()
    if any(k in lower for k in ("讲话", "speech", "致辞", "address", "remarks")):
        return "speech"
    if any(k in lower for k in ("会议纪要", "minutes", "meeting minutes")):
        return "report"
    if any(k in lower for k in ("决议", "利率决议", "rate decision", "fomc", "ecb meeting")):
        return "meeting"
    return "numeric"


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(DIR, "daily_data.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    updated = fetch_calendar_actuals(data)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(updated, f, ensure_ascii=False, indent=2)
    print(f"Calendar actuals updated in {path}")
