# -*- coding: utf-8 -*-
"""
iTick 行情源 (itick_data.py) — 全球金融日报系统

============================================================
为什么单独成模块 + 后台轮询
============================================================
iTick 免费套餐实测硬性限流 **5 次/分钟**（第 6 次起 429 request limit exceeded，
按分钟窗口重置；付费套餐 120~1200 次/分钟，可用 ITICK_RPM 环境变量调高）。
若把 iTick 放进 /api/quotes 的请求链路，每次刷新都会被限流击穿、且拖慢整体响应。

因此本模块采用 **后台常驻轮询 + 内存快照** 架构：
  - 守护线程按令牌桶节奏（默认 5 次/分钟）轮转刷新品种，结果写入内存缓存；
  - 请求路径只读快照 get_snapshot()，**零 API 调用、零网络延迟、永不触发限流**；
  - 主源（Frankfurter/新浪/腾讯/东财）照常提供全量行情，iTick 负责
    ① 缺项补位 ② 关键品种交叉校验（价格分歧告警）③ K 线备用源。

============================================================
API 契约（2026-09-04 实测）
============================================================
- 认证域名：https://api-free.itick.org（**免费版专用**）
             付费版为 https://api.itick.org，免费 Token 打后者会返回
             401 {"message":"Invalid API key in request"}
- 认证方式：请求头 token: <API_KEY>  +  accept: application/json
- 实时报价：GET /forex/quote?region=GB&code=XAUUSD
             region 固定 "GB"（外汇/贵金属/能源合约均在此市场下）
  - 不支持批量：code=EURUSD,GBPUSD 返回 data:null，必须一品种一次调用
- 逐笔成交：GET /forex/tick?region=GB&code=XAUUSD
- 历史K线 ：GET /forex/kline?region=GB&code=XAUUSD&kType=8&limit=100
             kType: 1=1分 2=5分 3=15分 4=30分 5=1时 6=2时 7=4时 8=日 9=周 10=月
- 品种清单：GET /symbol/list?type=forex&region=GB  （330 个，键为 c）
- 响应结构：{"code":0,"msg":null,"data":{...}}   code=0 为业务成功
  data 字段：s 代码 / ld 最新价 / p 前收 / o 开 / h 高 / l 低 /
             ch 涨跌 / chp 涨跌% / v 成交量 / tu 成交额 / t 毫秒时间戳 / r 市场

============================================================
配置（环境变量，均可不设）
============================================================
ITICK_TOKEN  API Key。缺省使用内置免费 Key。
ITICK_BASE   API 域名，默认 https://api-free.itick.org
ITICK_RPM    每分钟调用上限，默认 5（免费套餐）。付费可设 120/600/1200
"""

import json
import os
import ssl
import threading
import time
import urllib.request
from datetime import datetime

# ------------------------------------------------------------
# 配置
# ------------------------------------------------------------
ITICK_TOKEN = os.environ.get("ITICK_TOKEN") or ""
ITICK_BASE = os.environ.get("ITICK_BASE") or "https://api-free.itick.org"
try:
    ITICK_RPM = max(1, int(os.environ.get("ITICK_RPM") or 5))
except ValueError:
    ITICK_RPM = 5

REGION = "GB"          # 外汇/贵金属/能源统一市场代码
DEFAULT_TIMEOUT = 12

# ------------------------------------------------------------
# 品种映射：日报显示名 -> (iTick 代码, 轮询权重)
# 权重 2 = 核心品种（贵金属/能源），刷新频率加倍。
# 代码均已对照 /symbol/list?type=forex&region=GB 核实存在。
# 注意：按项目约定剔除人民币相关品种（无 USDCNH / XAUCNY 等）。
# ------------------------------------------------------------
SYMBOLS = {
    # ---- 贵金属（用户核心交易品种，权重 2）----
    "\u73b0\u8d27\u9ec4\u91d1":       ("XAUUSD", 2),   # 现货黄金
    "\u73b0\u8d27\u767d\u94f6":       ("XAGUSD", 2),   # 现货白银
    # ---- 能源（权重 2）----
    "WTI\u539f\u6cb9":                ("USOIL", 2),
    "\u5e03\u4f26\u7279\u539f\u6cb9": ("UKOIL", 2),
    "\u5929\u7136\u6c14":             ("XNGUSD", 2),
    # ---- 直盘 ----
    "\u6b27\u5143/\u7f8e\u5143":      ("EURUSD", 1),   # 欧元/美元
    "\u82f1\u9551/\u7f8e\u5143":      ("GBPUSD", 1),   # 英镑/美元
    "\u7f8e\u5143/\u65e5\u5143":      ("USDJPY", 1),   # 美元/日元
    "\u6fb3\u5143/\u7f8e\u5143":      ("AUDUSD", 1),   # 澳元/美元
    "\u7f8e\u5143/\u745e\u90ce":      ("USDCHF", 1),   # 美元/瑞郎
    "\u7f8e\u5143/\u52a0\u5143":      ("USDCAD", 1),   # 美元/加元
    "\u65b0\u897f\u5170\u5143/\u7f8e\u5143": ("NZDUSD", 1),  # 新西兰元/美元
    "\u7f8e\u5143/\u6e2f\u5e01":      ("USDHKD", 1),   # 美元/港币
    # ---- 交叉盘 ----
    "\u6b27\u5143/\u65e5\u5143(\u4ea4\u53c9\u76d8)": ("EURJPY", 1),
    "\u82f1\u9551/\u65e5\u5143(\u4ea4\u53c9\u76d8)": ("GBPJPY", 1),
    "\u6b27\u5143/\u82f1\u9551(\u4ea4\u53c9\u76d8)": ("EURGBP", 1),
    "\u6fb3\u5143/\u65e5\u5143(\u4ea4\u53c9\u76d8)": ("AUDJPY", 1),
    "\u6b27\u5143/\u745e\u90ce(\u4ea4\u53c9\u76d8)": ("EURCHF", 1),
    "\u82f1\u9551/\u6fb3\u5143(\u4ea4\u53c9\u76d8)": ("GBPAUD", 1),
    "\u6fb3\u5143/\u65b0\u897f\u5170\u5143(\u4ea4\u53c9\u76d8)": ("AUDNZD", 1),
    "\u745e\u90ce/\u65e5\u5143(\u4ea4\u53c9\u76d8)": ("CHFJPY", 1),
    "\u52a0\u5143/\u65e5\u5143(\u4ea4\u53c9\u76d8)": ("CADJPY", 1),
    "\u65b0\u897f\u5170\u5143/\u65e5\u5143(\u4ea4\u53c9\u76d8)": ("NZDJPY", 1),
}

# kType 映射：日报前端周期 -> iTick kType
KTYPE = {"1m": 1, "5m": 2, "15m": 3, "30m": 4, "1h": 5, "2h": 6, "4h": 7,
         "1d": 8, "daily": 8, "1w": 9, "1M": 10}

# ------------------------------------------------------------
# 口径优先：这些品种以 iTick 为准，覆盖主源
# ------------------------------------------------------------
# 背景：日报里「现货黄金」「现货白银」标注为现货，但新浪 hf_GC / hf_SI 实际取的是
# COMEX 期货合约价，两者存在约 1% 口径差（2026-09-04 实测：黄金期货 4519.59 vs
# 现货 4474.28）。用户为现货交易者，MT4 实盘报价为 XAUUSD / XAGUSD 现货 CFD，
# 因此贵金属改用 iTick 现货口径，与实盘一致。
#
# 原油/天然气保持新浪期货（WTI/布伦特期货本身就是国际基准价，且日报未标注"现货"）。
#
# 安全兜底：仅当 iTick 快照新鲜度 <= PREFER_MAX_STALE 秒时才覆盖，
# 否则自动回落主源，保证 iTick 限流/故障时行情不中断。
PREFER = {
    "\u73b0\u8d27\u9ec4\u91d1",   # 现货黄金 -> XAUUSD 现货
    "\u73b0\u8d27\u767d\u94f6",   # 现货白银 -> XAGUSD 现货
}
# 秒。核心品种实测平均陈旧 ~95s，但 23 个品种按 5 次/分钟轮转时，
# 个别时刻会拉长到 300s 以上（实测最旧曾达 341s）。
# 阈值若卡 300s，贵金属会在「现货价」与「期货价」之间来回跳变 —— 那会造成约 1% 的价格闪跳，
# 比「显示 10 分钟前的现货价」更糟：两者根本不是同一标的，回落并不会得到"更新鲜的现货价"。
# 因此对现货交易者而言，宁可要稍旧的现货价，也不要实时的期货价。定 600s 留足余量。
PREFER_MAX_STALE = 600

# ------------------------------------------------------------
# 运行状态
# ------------------------------------------------------------
_ctx = ssl._create_unverified_context()
_lock = threading.RLock()

# 快照持久化：重启后立即可用，避免贵金属闪回期货价。
# 场景：桌面 bat 每次启动都会重启进程；若此时上一实例刚用掉当分钟额度，
# bootstrap 会拿到 429，缓存为空 -> 现货黄金短暂显示新浪 COMEX 期货价（约 1% 闪跳）。
# 落盘后重启能立刻读到上次快照，只要未超过 PREFER_MAX_STALE 就继续用现货价。
_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.environ.get("WORKBUDDY_DATA_DIR") or _DIR
CACHE_FILE = os.path.join(_DATA_DIR, "itick_cache.json")

_cache = {}          # name -> {price, prevClose, ..., _ts, _code}
_calls = []          # 滑动窗口内的调用时间戳
_worker = None       # 后台线程
_state = {
    "enabled": bool(ITICK_TOKEN),
    "running": False,
    "ok": 0,          # 累计成功
    "fail": 0,        # 累计失败
    "throttled": 0,   # 累计被限流次数
    "last_error": "",
    "last_ok_at": "",
    "started_at": "",
}
_backoff_until = 0.0  # 被限流/连续失败后的退避截止时间


def _now():
    return time.time()


def _stamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ------------------------------------------------------------
# 快照持久化
# ------------------------------------------------------------
def _load_cache():
    """启动时从磁盘恢复上次快照。仅恢复结构完整的条目，任何异常都不影响主流程。"""
    global _cache
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return 0
        items = raw.get("quotes") if isinstance(raw.get("quotes"), dict) else raw
        n = 0
        with _lock:
            for name, q in items.items():
                if not isinstance(q, dict):
                    continue
                if name not in SYMBOLS:
                    continue          # 映射已变更的旧条目直接丢弃
                try:
                    price = float(q.get("price"))
                except (TypeError, ValueError):
                    continue
                if price <= 0:
                    continue
                # 恢复的 _ts 保留原值，staleSec 才会如实反映真实年龄；
                # 超过 PREFER_MAX_STALE 的条目自然不会被用于口径覆盖。
                q["_ts"] = float(q.get("_ts") or 0)
                _cache[name] = q
                n += 1
        return n
    except Exception:
        return 0


def _save_cache():
    """写盘。文件很小（23 条），每次更新直接写；失败静默忽略。"""
    try:
        with _lock:
            payload = {
                "saved_at": _stamp(),
                "quotes": {k: v for k, v in _cache.items()},
            }
        tmp = CACHE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, CACHE_FILE)
        return True
    except Exception:
        return False


_load_cache()


# ------------------------------------------------------------
# 令牌桶限流：滑动窗口，窗口内最多 ITICK_RPM 次
# ------------------------------------------------------------
def _limiter_acquire(block=True, timeout=90.0):
    """返回 True 表示获得调用配额。block=True 时最多等待 timeout 秒。"""
    t0 = _now()
    while True:
        with _lock:
            now = _now()
            # 丢弃窗口外的记录（窗口 62s，留 2s 时钟/网络余量）
            while _calls and now - _calls[0] > 62.0:
                _calls.pop(0)
            if len(_calls) < ITICK_RPM:
                _calls.append(now)
                return True
            wait = 62.0 - (now - _calls[0]) + 0.25
        if not block:
            return False
        if _now() - t0 > timeout:
            return False
        time.sleep(min(wait, 2.0))


def _note_throttle():
    """被 429 命中：退避到下一分钟窗口，避免继续浪费调用。"""
    global _backoff_until
    with _lock:
        _state["throttled"] += 1
    _backoff_until = _now() + 62.0


# ------------------------------------------------------------
# HTTP
# ------------------------------------------------------------
def _get(path, timeout=DEFAULT_TIMEOUT):
    """调用 iTick API。返回 (ok, payload, err)。payload 为已解包的 data。"""
    if not ITICK_TOKEN:
        return False, None, "ITICK_TOKEN \u672a\u914d\u7f6e"
    url = "%s%s%s" % (ITICK_BASE, path, "&" if "?" in path else "?")
    url = url.rstrip("&?")
    req = urllib.request.Request(url, headers={
        "token": ITICK_TOKEN,
        "accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ctx) as r:
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        txt = ""
        try:
            txt = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        if e.code == 429:
            _note_throttle()
            return False, None, "429 \u89e6\u53d1\u9650\u6d41 (\u514d\u8d39\u5957\u9910 %d \u6b21/\u5206\u949f)" % ITICK_RPM
        if e.code in (401, 403):
            return False, None, "%d \u8ba4\u8bc1\u5931\u8d25\uff1aToken \u65e0\u6548\u6216\u5957\u9910\u4e0d\u542b\u8be5\u6570\u636e %s" % (e.code, txt)
        return False, None, "HTTP %d %s" % (e.code, txt)
    except Exception as e:
        return False, None, "%s: %s" % (type(e).__name__, e)

    try:
        j = json.loads(body)
    except Exception:
        return False, None, "\u54cd\u5e94\u975e JSON: %s" % body[:120]
    if j.get("code") != 0:
        return False, None, "\u4e1a\u52a1\u9519\u8bef code=%s msg=%s" % (j.get("code"), j.get("msg"))
    return True, j.get("data"), None


def _request(path, timeout=DEFAULT_TIMEOUT, block=True):
    """限流 + 退避 + 统计包装。"""
    if _now() < _backoff_until:
        if not block:
            return False, None, "\u9000\u907f\u4e2d"
        time.sleep(min(_backoff_until - _now(), 62.0))
    if not _limiter_acquire(block=block):
        return False, None, "\u914d\u989d\u7b49\u5f85\u8d85\u65f6"
    ok, data, err = _get(path, timeout=timeout)
    with _lock:
        if ok:
            _state["ok"] += 1
            _state["last_ok_at"] = _stamp()
        else:
            _state["fail"] += 1
            _state["last_error"] = err or ""
    return ok, data, err


# ------------------------------------------------------------
# 报价获取与归一化
# ------------------------------------------------------------
def fetch_quote(name, block=True):
    """拉取单个日报品种的报价并写入缓存。返回归一化 quote 或 None。"""
    mapping = SYMBOLS.get(name)
    if not mapping:
        return None
    code = mapping[0]
    ok, d, err = _request("/forex/quote?region=%s&code=%s" % (REGION, code), block=block)
    if not ok or not d:
        return None

    price = d.get("ld")
    prev = d.get("p")
    try:
        price = float(price)
    except (TypeError, ValueError):
        return None
    if price <= 0:
        return None
    try:
        prev = float(prev) if prev not in (None, "") else None
    except (TypeError, ValueError):
        prev = None

    chg = (price - prev) if prev else d.get("ch")
    pct = d.get("chp")
    if pct is None and prev and prev > 0:
        pct = (price - prev) / prev * 100
    try:
        chg = float(chg) if chg is not None else None
    except (TypeError, ValueError):
        chg = None
    try:
        pct = float(pct) if pct is not None else None
    except (TypeError, ValueError):
        pct = None

    q = {
        "price": round(price, 4),
        "prevClose": round(prev, 4) if prev else None,
        "change": round(chg, 4) if chg is not None else None,
        "changePct": round(pct, 2) if pct is not None else None,
        "source": "itick",
        "fetched_at": _stamp(),
        # iTick 独有字段，供前端/校验使用
        "itick_code": code,
        "itick_high": d.get("h"),
        "itick_low": d.get("l"),
        "itick_open": d.get("o"),
        "itick_volume": d.get("v"),
        "itick_ts": d.get("t"),
    }
    with _lock:
        q["_ts"] = _now()
        _cache[name] = q
    _save_cache()
    return q


def fetch_kline(name, tf="1d", limit=100):
    """按需拉取 K 线（消耗 1 次调用额度，用于 /api/kline 兜底）。
    返回 [{t, o, h, l, c, v}] 按时间升序，或 None。"""
    mapping = SYMBOLS.get(name)
    if not mapping:
        return None
    code = mapping[0]
    ktype = KTYPE.get(tf, 8)
    ok, d, err = _request(
        "/forex/kline?region=%s&code=%s&kType=%d&limit=%d" % (REGION, code, ktype, limit),
        block=False)
    if not ok or not isinstance(d, list):
        return None
    out = []
    for k in d:
        try:
            out.append({
                "t": int(k.get("t")),
                "o": float(k.get("o")),
                "h": float(k.get("h")),
                "l": float(k.get("l")),
                "c": float(k.get("c")),
                "v": float(k.get("v") or 0),
            })
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda x: x["t"])
    return out or None


# ------------------------------------------------------------
# 后台轮询
# ------------------------------------------------------------
def _pick_next():
    """选择下一个待刷新品种：得分 = 距上次刷新秒数 × 权重，取最大。
    未取到过数据的品种视为无限陈旧，优先填充。"""
    now = _now()
    best, best_score = None, -1.0
    with _lock:
        items = list(SYMBOLS.items())
        cached = dict(_cache)
    for name, (code, weight) in items:
        c = cached.get(name)
        age = (now - c["_ts"]) if c and c.get("_ts") else 1e9
        score = age * weight
        if score > best_score:
            best, best_score = name, score
    return best


def _worker_loop():
    _state["running"] = True
    _state["started_at"] = _stamp()
    consecutive_fail = 0
    while True:
        if not ITICK_TOKEN:
            time.sleep(60)
            continue
        name = _pick_next()
        if not name:
            time.sleep(5)
            continue
        q = fetch_quote(name, block=True)
        if q:
            consecutive_fail = 0
            # 正常节奏：让限流器自然分配调用，避免空转
            time.sleep(0.4)
        else:
            consecutive_fail += 1
            with _lock:
                last_err = _state.get("last_error", "")
            if "429" in last_err:
                # 限流已在 _note_throttle 里退避，等待窗口重置
                time.sleep(5)
            else:
                # 连续失败（网络/鉴权）：指数退避，上限 10 分钟
                delay = min(60 * (2 ** min(consecutive_fail, 4)), 600)
                time.sleep(delay)


def start_background():
    """启动后台轮询守护线程（幂等）。"""
    global _worker
    if not ITICK_TOKEN:
        _state["enabled"] = False
        return False
    with _lock:
        if _worker is not None and _worker.is_alive():
            return True
        _state["enabled"] = True
        _worker = threading.Thread(target=_worker_loop, name="itick-poller")
        _worker.daemon = True       # 不阻塞进程退出
        _worker.start()
        return True


def bootstrap(max_calls=None):
    """启动时同步预热，保证首屏就有数据。默认消耗 1 分钟额度（5 次）。
    按权重优先：贵金属/能源先取。"""
    if not ITICK_TOKEN:
        return 0
    budget = max_calls if max_calls is not None else ITICK_RPM
    ordered = sorted(SYMBOLS.items(), key=lambda kv: -kv[1][1])
    got = 0
    for name, _ in ordered[:budget]:
        if fetch_quote(name, block=False):
            got += 1
    return got


# ------------------------------------------------------------
# 对外接口
# ------------------------------------------------------------
def get_snapshot():
    """返回 {name: quote} 缓存快照（去掉内部字段 _ts）。请求路径零 API 调用。"""
    with _lock:
        out = {}
        for k, v in _cache.items():
            d = {kk: vv for kk, vv in v.items() if kk != "_ts"}
            d["staleSec"] = int(_now() - v.get("_ts", 0))
            out[k] = d
        return out


def status():
    """健康检查，供 /api/status 展示。"""
    with _lock:
        snap = dict(_state)
        cached = len(_cache)
        newest = max([v.get("_ts", 0) for v in _cache.values()] or [0])
        oldest = min([v.get("_ts", 0) for v in _cache.values()] or [0])
    return {
        "enabled": snap.get("enabled", False),
        "running": snap.get("running", False),
        "base": ITICK_BASE,
        "rpm": ITICK_RPM,
        "symbols": len(SYMBOLS),
        "cached": cached,
        "persisted": os.path.exists(CACHE_FILE),
        "ok": snap.get("ok", 0),
        "fail": snap.get("fail", 0),
        "throttled": snap.get("throttled", 0),
        "last_error": snap.get("last_error", ""),
        "last_ok_at": snap.get("last_ok_at", ""),
        "started_at": snap.get("started_at", ""),
        "newest_age_sec": int(_now() - newest) if newest else None,
        "oldest_age_sec": int(_now() - oldest) if oldest else None,
    }


# ------------------------------------------------------------
# 自测
# ------------------------------------------------------------
if __name__ == "__main__":
    print("iTick \u6570\u636e\u6e90\u81ea\u6d4b")
    print("base :", ITICK_BASE)
    print("rpm  :", ITICK_RPM)
    print("token:", (ITICK_TOKEN[:8] + "..." + ITICK_TOKEN[-4:]) if ITICK_TOKEN else "\u672a\u914d\u7f6e")
    print("-" * 60)
    got = bootstrap()
    print("\u9884\u70ed\u5b8c\u6210: %d \u4e2a\u54c1\u79cd" % got)
    snap = get_snapshot()
    for name, q in snap.items():
        print("  %-22s %-9s %12.4f  chg%%=%6s  src=%s" % (
            name, q["itick_code"], q["price"], q.get("changePct"), q["source"]))
    print("-" * 60)
    print(json.dumps(status(), ensure_ascii=False, indent=2))
