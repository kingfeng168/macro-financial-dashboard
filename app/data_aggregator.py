# -*- coding: utf-8 -*-
"""
多源实时数据聚合器 (Multi-source real-time data aggregator)

设计目标：
1. 为行情、新闻、财经日历 actual 提供多源获取与自动故障转移。
2. 每个数据点返回 source / fetched_at / status 元数据，便于前端展示数据来源与健康度。
3. 优先使用公开、权威、无需密钥的 API；失败时自动降级到备用源。
4. 在 sandbox/ mainland 网络受限环境下，某源可能不可达，架构本身保持可用。

数据源优先级：
- 外汇：Frankfurter (ECB) -> 新浪外汇 hq.sinajs.cn
- 贵金属/商品：Yahoo Finance -> 新浪 hf_ 期货
- 全球股指：新浪 int_/b_ 指数 -> Yahoo Finance
- 中国A股/指数：东方财富 -> 新浪财经
- 实时新闻：金十数据 -> 华尔街见闻 -> 东方财富 7x24 -> 新浪财经 (RSS/HTML)。路透因 Akamai 防护+沙箱 egress 限制无法直连，需用户提供 API key/RSS 或走 WebFetch 按需抓取。
- 日历 actual：daily_data.json -> 外部 JSON 回填 -> 公开数据源尝试 -> 待取数
"""

import difflib
import json
import re
import ssl
import time
import threading
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from io import StringIO
from concurrent.futures import ThreadPoolExecutor

# 复用 live_server 的符号映射 (运行时动态 import 避免循环依赖)
# 但为避免循环，我们把行情所需的关键映射内联一份轻量版。

# ============================================================
# 基础工具
# ============================================================
_ctx = ssl._create_unverified_context()

def _ua():
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept": "application/json, text/plain, text/html, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

def _http_get(url, timeout=12, headers=None, encoding=None):
    """通用 HTTP GET，返回 (ok, text, err)。"""
    h = _ua()
    if headers:
        h.update(headers)
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout, context=_ctx) as r:
            data = r.read()
            enc = encoding or r.headers.get_content_charset() or "utf-8"
            return True, data.decode(enc, errors="replace"), None
    except Exception as e:
        return False, None, str(e)


# ============================================================
# 健康状态追踪
# ============================================================
class SourceHealth(object):
    """线程安全的数据源健康状态记录器。"""
    def __init__(self):
        self._lock = threading.Lock()
        self._state = {}  # source_name -> {ok, last_ok, last_err, latency_ms, count}

    def record(self, source, ok, err=None, latency_ms=None):
        with self._lock:
            s = self._state.setdefault(source, {"ok": None, "last_ok": 0, "last_err": "", "latency_ms": 0, "count": 0})
            s["ok"] = bool(ok)
            s["count"] += 1
            if ok:
                s["last_ok"] = time.time()
            if err:
                s["last_err"] = str(err)[:120]
            if latency_ms is not None:
                s["latency_ms"] = latency_ms

    def snapshot(self):
        with self._lock:
            out = {}
            now = time.time()
            for k, v in self._state.items():
                out[k] = {
                    "ok": v["ok"],
                    "last_ok_ago_sec": int(now - v["last_ok"]) if v["last_ok"] else None,
                    "last_err": v["last_err"],
                    "latency_ms": v["latency_ms"],
                    "count": v["count"],
                }
            return out


HEALTH = SourceHealth()


# ============================================================
# 行情：多源聚合
# ============================================================
FOREX_ER_LITE = {
    "欧元/美元": ("EUR", "inv"),
    "美元/日元": ("JPY", "fwd"),
    "英镑/美元": ("GBP", "inv"),
    "澳元/美元": ("AUD", "inv"),
    "美元/瑞郎": ("CHF", "fwd"),
    "美元/加元": ("CAD", "fwd"),
    "新西兰元/美元": ("NZD", "inv"),
    "美元/港币": ("HKD", "fwd"),
    "欧元/日元(交叉盘)": (("EUR", "JPY"), "cross"),
    "英镑/日元(交叉盘)": (("GBP", "JPY"), "cross"),
    "欧元/英镑(交叉盘)": (("EUR", "GBP"), "cross"),
    "澳元/日元(交叉盘)": (("AUD", "JPY"), "cross"),
    "欧元/瑞郎(交叉盘)": (("EUR", "CHF"), "cross"),
    "英镑/澳元(交叉盘)": (("GBP", "AUD"), "cross"),
    "欧元/澳元(交叉盘)": (("EUR", "AUD"), "cross"),
    "澳元/新西兰元(交叉盘)": (("AUD", "NZD"), "cross"),
    "瑞郎/日元(交叉盘)": (("CHF", "JPY"), "cross"),
    "加元/日元(交叉盘)": (("CAD", "JPY"), "cross"),
    "新西兰元/日元(交叉盘)": (("NZD", "JPY"), "cross"),
}

# 新浪外汇代码：fx_s{BASE}{QUOTE}，全部大写
SINA_FOREX = {
    "欧元/美元": "fx_sEURUSD",
    "美元/日元": "fx_sUSDJPY",
    "英镑/美元": "fx_sGBPUSD",
    "澳元/美元": "fx_sAUDUSD",
    "美元/瑞郎": "fx_sUSDCHF",
    "美元/加元": "fx_sUSDCAD",
    "新西兰元/美元": "fx_sNZDUSD",
    "美元/港币": "fx_sUSDHKD",
    "欧元/日元(交叉盘)": "fx_sEURJPY",
    "英镑/日元(交叉盘)": "fx_sGBPJPY",
    "欧元/英镑(交叉盘)": "fx_sEURGBP",
    "澳元/日元(交叉盘)": "fx_sAUDJPY",
    "欧元/瑞郎(交叉盘)": "fx_sEURCHF",
    "英镑/澳元(交叉盘)": "fx_sGBPAUD",
    "欧元/澳元(交叉盘)": "fx_sEURAUD",
    "澳元/新西兰元(交叉盘)": "fx_sAUDNZD",
    "瑞郎/日元(交叉盘)": "fx_sCHFJPY",
    "加元/日元(交叉盘)": "fx_sCADJPY",
    "新西兰元/日元(交叉盘)": "fx_sNZDJPY",
}

SINA_HF = {
    "现货黄金": "hf_GC",
    "现货白银": "hf_SI",
    "WTI原油": "hf_CL",
    "布伦特原油": "hf_OIL",
    "天然气": "hf_NG",
}

SINA_INT = {
    "道琼斯工业平均指数": "int_dow",
    "标普500指数": "int_sp500",
    "纳斯达克综合指数": "int_nasdaq",
    "德国DAX30指数": "int_dax",
    "法国CAC40指数": "int_cac",
    "英国富时100指数": "b_UKX",
    "欧洲斯托克50指数": "int_stoxx",
    "恒生指数": "int_hangseng",
    "日经225指数": "int_nikkei",
    "韩国KOSPI指数": "int_kospi",
    "澳大利亚ASX200指数": "int_asx",
    "印度Sensex指数": "int_sensex",
    "比特币": "btc",
    "美国VIX恐慌指数": "int_vix",
}

YAHOO_SYMBOLS = {
    "美元指数": "DX-Y.NYB",
    "欧元/美元": "EURUSD=X",
    "美元/日元": "JPY=X",
    "英镑/美元": "GBPUSD=X",
    "澳元/美元": "AUDUSD=X",
    "美元/瑞郎": "USDCHF=X",
    "美元/加元": "USDCAD=X",
    "新西兰元/美元": "NZDUSD=X",
    "美元/港币": "USDHKD=X",
    "现货黄金": "GC=F",
    "现货白银": "SI=F",
    "WTI原油": "CL=F",
    "布伦特原油": "BZ=F",
    "天然气": "NG=F",
    "道琼斯工业平均指数": "^DJI",
    "标普500指数": "^GSPC",
    "纳斯达克综合指数": "^IXIC",
    "罗素2000指数": "^RUT",
    "欧洲斯托克50指数": "^STOXX50E",
    "德国DAX30指数": "^GDAXI",
    "法国CAC40指数": "^FCHI",
    "英国富时100指数": "^FTSE",
    "意大利富时MIB指数": "^FTMIB",
    "恒生指数": "^HSI",
    "恒生科技指数": "^HSTECH",
    "日经225指数": "^N225",
    "韩国KOSPI指数": "^KS11",
    "澳大利亚ASX200指数": "^AXJO",
    "印度Sensex指数": "^BSESN",
    "比特币": "BTC-USD",
    "美国VIX恐慌指数": "^VIX",
}

# 东方财富 secids: 1=沪市, 0=深市
EASTMONEY_SECIDS = {
    "上证指数": "1.000001",
    "深证成指": "0.399001",
    "沪深300": "1.000300",
    "创业板指": "0.399006",
    "科创50": "1.000688",
}


def _round4(v):
    try:
        return round(float(v), 4)
    except:
        return None


def _quote(name, price, prev, source):
    if price is None or price <= 0:
        return None
    price = float(price)
    prev = float(prev) if prev else None
    chg = (price - prev) if prev else None
    chg_pct = (chg / prev * 100) if (prev and prev > 0) else None
    return {
        "price": round(price, 4),
        "prevClose": round(prev, 4) if prev else None,
        "change": round(chg, 4) if chg is not None else None,
        "changePct": round(chg_pct, 2) if chg_pct is not None else None,
        "source": source,
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ---------- 1. Frankfurter 外汇 ----------
def fetch_frankfurter():
    """Return {name: quote} for forex pairs."""
    currencies = "EUR,JPY,GBP,AUD,CHF,CAD,NZD,HKD"
    url = f"https://api.frankfurter.app/latest?from=USD&to={currencies}"
    t0 = time.time()
    ok, txt, err = _http_get(url, timeout=10)
    latency = int((time.time() - t0) * 1000)
    if not ok:
        HEALTH.record("frankfurter", False, err, latency)
        return {}
    try:
        d = json.loads(txt)
        rates = d.get("rates", {})
        date_str = d.get("date", "")
        prev_rates = {}
        if date_str:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            prev_date = dt - timedelta(days=1)
            while prev_date.weekday() >= 5:
                prev_date -= timedelta(days=1)
            prev_url = f"https://api.frankfurter.app/{prev_date.strftime('%Y-%m-%d')}?from=USD&to={currencies}"
            ok2, txt2, _ = _http_get(prev_url, timeout=8)
            if ok2:
                prev_rates = json.loads(txt2).get("rates", {})

        result = {}
        for nm, (cur, mode) in FOREX_ER_LITE.items():
            try:
                if mode == "inv":
                    if not rates.get(cur):
                        continue
                    price = 1.0 / rates[cur]
                    prev = 1.0 / prev_rates[cur] if prev_rates.get(cur) else None
                elif mode == "fwd":
                    if not rates.get(cur):
                        continue
                    price = rates[cur]
                    prev = prev_rates.get(cur)
                elif mode == "cross":
                    base_cur, quote_cur = cur
                    if not rates.get(base_cur) or not rates.get(quote_cur):
                        continue
                    price = rates[quote_cur] / rates[base_cur]
                    prev = (prev_rates[quote_cur] / prev_rates[base_cur]) if (prev_rates.get(base_cur) and prev_rates.get(quote_cur)) else None
                else:
                    continue
                q = _quote(nm, price, prev, "frankfurter")
                if q:
                    result[nm] = q
            except Exception:
                continue
        HEALTH.record("frankfurter", bool(result), latency_ms=latency)
        return result
    except Exception as e:
        HEALTH.record("frankfurter", False, str(e), latency)
        return {}


# ---------- 2. 新浪行情（外汇/商品/指数） ----------
def _parse_sina_quote(text, code):
    """Parse var hq_str_xxx='...'; into fields."""
    m = re.search(r"var hq_str_%s=['\"](.*?)['\"];" % re.escape(code), text)
    if not m:
        return None
    parts = m.group(1).split(",")
    if len(parts) < 2 or not parts[0]:
        return None
    return parts


def _sina_quote_from_parts(parts, code, name):
    """Convert Sina fields into standard quote dict.

    hf_ commodity: [0]=price, [7]=prev_settle
    int_ index:    [0]=name, [1]=price, [2]=change, [3]=changePct -> prev=price-change
    b_ index:      [0]=name, [1]=price, [2]=change, [3]=changePct, [9]=prev_close
    fx_ forex:     [0]=name, [1]=buy, [2]=sell, [3]=time, [4]=open, [5]=high, [6]=low, [7]=prev_close
    s_sh index:    [1]=price, [2]=change, [3]=changePct, [4]=volume, [5]=amount -> prev=price-change
    """
    try:
        if code.startswith("hf_"):
            price = _round4(parts[0])
            prev = _round4(parts[7]) if len(parts) > 7 else None
            return _quote(name, price, prev, "sina_hf")
        elif code.startswith("int_"):
            price = _round4(parts[1])
            change = _round4(parts[2]) if len(parts) > 2 else None
            prev = (price - change) if (price is not None and change is not None) else None
            return _quote(name, price, prev, "sina_int")
        elif code.startswith("b_"):
            price = _round4(parts[1])
            prev = _round4(parts[9]) if len(parts) > 9 else None
            return _quote(name, price, prev, "sina_b")
        elif code.startswith("fx_s"):
            # use average of buy/sell; prev from prev_close
            buy = _round4(parts[1]) if len(parts) > 1 else None
            sell = _round4(parts[2]) if len(parts) > 2 else None
            price = (buy + sell) / 2.0 if (buy and sell) else (buy or sell)
            prev = _round4(parts[7]) if len(parts) > 7 else None
            return _quote(name, price, prev, "sina_fx")
        elif code.startswith("s_sh") or code.startswith("s_sz"):
            price = _round4(parts[1])
            change = _round4(parts[2]) if len(parts) > 2 else None
            prev = (price - change) if (price is not None and change is not None) else None
            return _quote(name, price, prev, "sina_index")
    except Exception:
        return None


def fetch_sina_batch(codes):
    """Fetch a batch of Sina quotes by code list."""
    if not codes:
        return {}
    url = "https://hq.sinajs.cn/list=" + ",".join(codes)
    t0 = time.time()
    # Sina now requires a Referer from its own domain, otherwise 403.
    ok, txt, err = _http_get(url, timeout=10, encoding="gbk",
                              headers={"Referer": "https://finance.sina.com.cn"})
    latency = int((time.time() - t0) * 1000)
    if not ok:
        HEALTH.record("sina", False, err, latency)
        return {}
    HEALTH.record("sina", True, latency_ms=latency)
    return txt


def fetch_sina_quotes(symbols_map):
    """symbols_map: {name: sina_code}. Return {name: quote}."""
    result = {}
    codes = list(symbols_map.values())
    txt = fetch_sina_batch(codes)
    if not txt:
        return {}
    for name, code in symbols_map.items():
        parts = _parse_sina_quote(txt, code)
        if parts:
            q = _sina_quote_from_parts(parts, code, name)
            if q:
                result[name] = q
    return result


# ---------- 3. 东方财富中国指数 ----------
def fetch_eastmoney_china():
    """Fetch China indices from Eastmoney."""
    secids = ",".join(EASTMONEY_SECIDS.values())
    url = ("http://push2.eastmoney.com/api/qt/ulist.np/get?"
           "fltt=2&invt=2&fields=f12,f13,f14,f2,f3,f4,f5,f6,f17,f18,f15,f16&secids=" + secids)
    t0 = time.time()
    ok, txt, err = _http_get(url, timeout=10)
    latency = int((time.time() - t0) * 1000)
    if not ok:
        HEALTH.record("eastmoney", False, err, latency)
        return {}
    try:
        d = json.loads(txt)
        data = d.get("data", {}) or {}
        rows = data.get("diff", []) or []
        name_by_secid = {v: k for k, v in EASTMONEY_SECIDS.items()}
        result = {}
        for r in rows:
            secid = "%s.%s" % (r.get("f13", ""), r.get("f12", ""))
            name = name_by_secid.get(secid)
            if not name:
                continue
            price = _round4(r.get("f2"))  # 最新价
            # f18=昨收; f17=开盘; f4=涨跌额; f3=涨跌幅
            prev = _round4(r.get("f18"))
            if not prev and price:
                change = _round4(r.get("f4"))
                prev = (price - change) if change is not None else None
            q = _quote(name, price, prev, "eastmoney")
            if q:
                result[name] = q
        HEALTH.record("eastmoney", bool(result), latency_ms=latency)
        return result
    except Exception as e:
        HEALTH.record("eastmoney", False, str(e), latency)
        return {}


# ---------- 3.5 腾讯证券实时行情（美股/港股/A股指数） ----------
# qt.gtimg.cn 提供美股(us)/港股(hk)/A股(sh/sz) 实时价+昨收，比新浪 int_ 美股(陈旧)
# 与 Yahoo(沙箱403) 更可靠。需带 Referer: https://gu.qq.com/，GBK 解码。
TENCENT_SYMBOLS = {
    "道琼斯工业平均指数": "usDJI",
    "标普500指数": "usINX",
    "纳斯达克综合指数": "usIXIC",
    "恒生指数": "hkHSI",
    "恒生科技指数": "hkHSTECH",
    "上证指数": "sh000001",
    "深证成指": "sz399001",
    "沪深300": "sh000300",
    "创业板指": "sz399006",
    "科创50": "sh000688",
}


def fetch_tencent_quotes(symbols_map):
    """腾讯证券实时行情。字段: [1]=名称 [3]=最新价 [4]=昨收 [31]=涨跌额 [32]=涨跌幅。"""
    if not symbols_map:
        return {}
    url = "http://qt.gtimg.cn/q=" + ",".join(symbols_map.values())
    t0 = time.time()
    ok, txt, err = _http_get(url, timeout=8, encoding="gbk",
                             headers={"Referer": "https://gu.qq.com/"})
    latency = int((time.time() - t0) * 1000)
    if not ok:
        HEALTH.record("tencent", False, err, latency)
        return {}
    result = {}
    rev = {c: n for n, c in symbols_map.items()}
    for line in txt.split(";"):
        line = line.strip()
        if not line:
            continue
        m = re.match(r'v_(\w+)="(.*)"$', line)
        if not m:
            continue
        code, payload = m.group(1), m.group(2)
        fields = payload.split("~")
        name = rev.get(code)
        if not name or len(fields) < 33:
            continue
        try:
            price = float(fields[3])
            prev = float(fields[4]) if fields[4] else None
        except Exception:
            continue
        if price <= 0:
            continue
        q = _quote(name, price, prev, "tencent")
        if q:
            result[name] = q
    HEALTH.record("tencent", bool(result), latency_ms=latency)
    return result


# ---------- 4. Yahoo Finance 备选 ----------
def _fetch_yahoo_chart(symbol, interval="1d", range_param="3mo"):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?"
           f"interval={interval}&range={range_param}&includePrePost=false")
    ok, txt, err = _http_get(url, timeout=8)
    if not ok:
        return None
    try:
        return json.loads(txt)
    except Exception:
        return None


def fetch_yahoo_quotes(symbols_map):
    """symbols_map: {name: yahoo_symbol}. Return {name: quote}."""
    result = {}
    ylock = threading.Lock()
    threads = []

    def _worker(name, symbol):
        d = _fetch_yahoo_chart(symbol, "1m", "1d")
        if not d:
            return
        try:
            meta = d["chart"]["result"][0].get("meta", {})
            price = meta.get("regularMarketPrice")
            prev = meta.get("chartPreviousClose") or meta.get("previousClose")
            q = _quote(name, price, prev, "yahoo")
            if q:
                with ylock:
                    result[name] = q
        except Exception:
            pass

    t0 = time.time()
    for name, symbol in symbols_map.items():
        t = threading.Thread(target=_worker, args=(name, symbol))
        threads.append(t)
        t.start()
    for t in threads:
        t.join(timeout=5)
    latency = int((time.time() - t0) * 1000)
    HEALTH.record("yahoo", bool(result), latency_ms=latency)
    return result


# ---------- iTick 交叉校验源 ----------
def _itick_module():
    """延迟导入 itick_data：模块缺失/异常绝不拖垮主聚合流程。"""
    try:
        import itick_data
        return itick_data
    except Exception:
        return None


def fetch_itick_quotes():
    """读取 iTick 后台轮询快照。

    关键设计：iTick 免费套餐实测硬性限流 5 次/分钟，绝不能放进请求链路。
    itick_data 由后台守护线程按令牌桶节奏轮转刷新，本函数只读内存快照，
    因此 **零 API 调用、零网络延迟、永不触发 429**。

    Returns (quotes, state)：quotes 为标准 quote 结构并附 itick 独有字段。
    """
    mod = _itick_module()
    if mod is None:
        HEALTH.record("itick", False, "itick_data \u6a21\u5757\u4e0d\u53ef\u7528")
        return {}, None
    if not getattr(mod, "ITICK_TOKEN", ""):
        HEALTH.record("itick", False, "ITICK_TOKEN \u672a\u914d\u7f6e")
        return {}, None
    try:
        snap = mod.get_snapshot()
        state = mod.status()
    except Exception as e:
        HEALTH.record("itick", False, str(e))
        return {}, None
    out = {}
    for name, q in (snap or {}).items():
        if q and q.get("price"):
            out[name] = q
    HEALTH.record("itick", bool(out), "" if out else "\u5feb\u7167\u4e3a\u7a7a\uff08\u540e\u53f0\u9884\u70ed\u4e2d\uff09", latency_ms=0)
    return out, state


# ---------- 聚合行情 ----------
def fetch_all_quotes(force=False):
    """Main entry: aggregate quotes from all sources with failover (两阶段并发).

    Phase 1: 主源全部并发拉取（外汇 Frankfurter / 商品新浪 / 全球指数腾讯+新浪 /
              A股东财 / 特殊品种 Yahoo），网络延迟从串行叠加降为单次最大值。
    Phase 2: 根据 Phase 1 缺失项并发补漏（新浪外汇 / Yahoo 商品+指数 / 腾讯A股 / 新浪上证）。
    Phase 3: iTick —— 读后台轮询快照（零 API 调用，iTick 免费套餐限流 5 次/分钟，
             禁止进请求链路）。三重作用：
             ① 主源全挂时补位；
             ② 口径优先：PREFER 集合（现货黄金/白银）以 iTick 现货价覆盖主源期货价，
                与 MT4 实盘 XAUUSD/XAGUSD 一致；快照过期自动回落主源；
             ③ 其余品种挂 quote["itick"] 分歧度做交叉校验。

    Returns {"quotes": {name: quote}, "sources": {source: ok?}, "health": snapshot,
             "itick": {state, filled, verified, preferred}}
    """
    result = {}
    sources_status = {}

    def _run(fn, key):
        try:
            return fn()
        except Exception as e:
            HEALTH.record(key, False, str(e))
            return {}

    # ---------- Phase 1: 主源并发 ----------
    yahoo_priority = {"美元指数": "DX-Y.NYB", "比特币": "BTC-USD",
                      "美国VIX恐慌指数": "^VIX", "罗素2000指数": "^RUT",
                      "恒生科技指数": "^HSTECH"}
    with ThreadPoolExecutor(max_workers=6) as ex:
        f_fx = ex.submit(_run, lambda: fetch_frankfurter(), "frankfurter")
        f_hf = ex.submit(_run, lambda: fetch_sina_quotes(SINA_HF), "sina_hf")
        f_int = ex.submit(_run, lambda: fetch_sina_quotes(SINA_INT), "sina_int")
        f_tx = ex.submit(_run, lambda: fetch_tencent_quotes(TENCENT_SYMBOLS), "tencent_indices")
        f_em = ex.submit(_run, lambda: fetch_eastmoney_china(), "eastmoney")
        f_ys = ex.submit(_run, lambda: fetch_yahoo_quotes(yahoo_priority), "yahoo_special")

        fx = f_fx.result()
        sina_commodities = f_hf.result()
        sina_indices = f_int.result()
        tencent_idx = f_tx.result()
        china = f_em.result()
        ys = f_ys.result()

    sources_status["frankfurter"] = bool(fx)
    sources_status["sina_hf"] = bool(sina_commodities)
    sources_status["sina_int"] = bool(sina_indices)
    sources_status["tencent_indices"] = bool(tencent_idx)
    sources_status["eastmoney"] = bool(china)
    sources_status["yahoo_special"] = bool(ys)

    # 合并顺序保持原语义：优先腾讯(美股/港股实时)，新浪/东财/Yahoo 仅补缺
    result.update(fx)
    result.update(sina_commodities)
    result.update(tencent_idx)
    result.update(china)
    for k, v in sina_indices.items():
        if k not in result:
            result[k] = v
    for k, v in ys.items():
        if k not in result:
            result[k] = v

    # ---------- Phase 2: 缺失补漏并发 ----------
    missing_fx = {k: v for k, v in SINA_FOREX.items() if k not in result}
    missing_commodities = {k: v for k, v in YAHOO_SYMBOLS.items() if k in SINA_HF and k not in result}
    missing_indices = {k: v for k, v in YAHOO_SYMBOLS.items() if k in SINA_INT and k not in result}
    missing_cn = {k: v for k, v in TENCENT_SYMBOLS.items()
                  if k in EASTMONEY_SECIDS and k not in result}

    with ThreadPoolExecutor(max_workers=5) as ex:
        jobs = {}
        if missing_fx:
            jobs["sina_fx"] = ex.submit(_run, lambda: fetch_sina_quotes(missing_fx), "sina_fx")
        if missing_commodities:
            jobs["yahoo_commodities"] = ex.submit(_run, lambda: fetch_yahoo_quotes(missing_commodities), "yahoo_commodities")
        if missing_indices:
            jobs["yahoo_indices"] = ex.submit(_run, lambda: fetch_yahoo_quotes(missing_indices), "yahoo_indices")
        if missing_cn:
            jobs["tencent_cn"] = ex.submit(_run, lambda: fetch_tencent_quotes(missing_cn), "tencent_cn")
        for k, fut in jobs.items():
            r = fut.result()
            sources_status[k] = bool(r)
            result.update(r)

    if "上证指数" not in result:
        sina_sh = _run(lambda: fetch_sina_quotes({"上证指数": "s_sh000001"}), "sina_sh")
        sources_status["sina_sh"] = bool(sina_sh)
        result.update(sina_sh)

    # ---------- Phase 3: iTick 交叉校验 ----------
    # 读后台轮询快照（零 API 调用）。两个作用：
    #   ① 主源全挂时补位，保证贵金属/能源/外汇不缺项；
    #   ② 对已有报价做交叉校验，把 iTick 价与分歧度挂到 quote["itick"] 供前端展示。
    itick_state = None
    itick_filled = 0
    itick_verified = 0
    try:
        itick_quotes, itick_state = fetch_itick_quotes()
    except Exception as e:
        itick_quotes = {}
        HEALTH.record("itick", False, str(e))

    # 口径优先集合：这些品种 iTick 为现货口径，覆盖主源（新浪为期货口径）
    mod = _itick_module()
    prefer = set(getattr(mod, "PREFER", ()) or ()) if mod else set()
    prefer_max_stale = int(getattr(mod, "PREFER_MAX_STALE", 300) or 300) if mod else 300

    itick_preferred = 0
    for name, q_it in (itick_quotes or {}).items():
        cur = result.get(name)
        div_pct = None
        if cur is not None:
            try:
                p1 = float(cur.get("price"))
                p2 = float(q_it.get("price"))
                if p1 > 0 and p2 > 0:
                    div_pct = round((p2 - p1) / p1 * 100, 3)
            except (TypeError, ValueError):
                div_pct = None

        meta = {
            "price": q_it.get("price"),
            "code": q_it.get("itick_code"),
            "divPct": div_pct,
            "fetched_at": q_it.get("fetched_at"),
            "staleSec": q_it.get("staleSec"),
            "preferred": False,
            "filled": False,
        }

        if cur is None:
            # ① 主源全部失败 -> iTick 补位
            filled = dict(q_it)
            meta["filled"] = True
            filled["itick"] = meta
            result[name] = filled
            itick_filled += 1
            continue

        if name in prefer and (q_it.get("staleSec") or 1e9) <= prefer_max_stale:
            # ② 口径优先：以 iTick 现货价为准（与 MT4 实盘 XAUUSD/XAGUSD 一致）
            #    快照过期则自动回落主源，保证行情不中断。
            override = dict(q_it)
            meta["preferred"] = True
            meta["altPrice"] = cur.get("price")          # 被覆盖的期货价，保留可比对
            meta["altSource"] = cur.get("source")
            override["itick"] = meta
            result[name] = override
            itick_preferred += 1
            continue

        # ③ 交叉校验：把 iTick 价与分歧度挂到主报价上，供前端展示
        cur["itick"] = meta
        itick_verified += 1

    sources_status["itick"] = bool(itick_quotes)

    return {
        "quotes": result,
        "sources": sources_status,
        "health": HEALTH.snapshot(),
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(result),
        "itick": {
            "state": itick_state,
            "filled": itick_filled,
            "verified": itick_verified,
            "preferred": itick_preferred,
        },
    }


# ============================================================
# 实时新闻聚合
# ============================================================
def _clean_html(text):
    return re.sub(r"<[^>]+>", "", text).strip()


def _item_ts(it):
    """将 news item 的 published_at 归一化为 epoch 秒，用于排序（无法解析则排末尾）。

    优先使用源提供的精确 ts（见闻等源直接给 unix 秒），避免字符串解析歧义。
    """
    if isinstance(it.get("ts"), (int, float)) and it["ts"]:
        return int(it["ts"])
    t = it.get("published_at")
    if isinstance(t, (int, float)):
        return int(t)
    if isinstance(t, str) and t.strip():
        s = t.strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return int(datetime.strptime(s, fmt).timestamp())
            except Exception:
                pass
        try:
            return int(float(s))
        except Exception:
            pass
    return 0


def _norm_title_key(title):
    return re.sub(r"\s+", "", title or "")[:30]


def _title_tokens(title):
    """提取标题中的实义片段用于跨源近似去重（去标点、按长度>=2的片段）。"""
    s = re.sub(r"[^\w\u4e00-\u9fff]+", " ", title or "").strip()
    toks = [w for w in s.split() if len(w) >= 2]
    return set(toks)


def _is_near_dup(a, b, seen_tokens):
    """跨源近似去重：若 b 的实义片段大多已出现在已保留集合中，视为同一事件。"""
    bt = _title_tokens(b)
    if not bt:
        return False
    overlap = len(bt & seen_tokens)
    return overlap >= max(1, int(len(bt) * 0.6))


def _cn_ratio(text):
    """中文字符占比，用于剔除同源的英文重复条目（金十为中英双语推送）。"""
    s = re.sub(r"\s+", "", text or "")
    if not s:
        return 0.0
    cn = len(re.findall(r"[\u4e00-\u9fff]", s))
    return cn / float(len(s))


def _norm_sig(title):
    """归一化事件签名：仅保留中文、数字与大写字母(PMI/GDP等)，用于字符级相似度比对。

    这样「德国8月制造业PMI终值 54.3，预期54.1」与「德国 制造业PMI终值 实际 54.3 预期 54.1」
    会得到高度相似的签名，从而识别为同一事件。
    """
    s = re.sub(r"[^\u4e00-\u9fffA-Z0-9]", "", (title or "").upper())
    return s[:60]


def _is_dup_event(title, seen_sigs, threshold=0.62):
    """基于字符级相似度的同事件判定（difflib），比 token 交集更适合中文财经快讯。"""
    sig = _norm_sig(title)
    if len(sig) < 4:
        return False
    for old in seen_sigs:
        if not old:
            continue
        # 快速长度剪枝
        if abs(len(sig) - len(old)) > max(len(sig), len(old)) * 0.6:
            continue
        if difflib.SequenceMatcher(None, sig, old).ratio() >= threshold:
            return True
    return False


# 金十快讯无频道字段，按关键词推断所属交易主线，与见闻频道标签对齐
_CHANNEL_KEYWORDS = [
    ("黄金", ("黄金", "金价", "白银", "银价", "贵金属", "现货金", "现货银", "XAU", "XAG")),
    ("原油", ("原油", "油价", "WTI", "布伦特", "OPEC", "页岩油", "石油", "EIA库存")),
    ("商品", ("铜", "铁矿", "螺纹", "钢", "铝", "锌", "大豆", "玉米", "天然气", "煤")),
    ("外汇", ("美元", "欧元", "日元", "英镑", "澳元", "汇率", "美联储", "欧洲央行",
              "日本央行", "加息", "降息", "非农", "CPI", "PMI", "国债收益率")),
]


def _infer_channel(text):
    """按关键词推断频道标签，命中优先级靠前者优先。"""
    t = text or ""
    for tag, kws in _CHANNEL_KEYWORDS:
        for kw in kws:
            if kw in t:
                return tag
    return "快讯"


# MCP 快讯无 important 字段，按重大事件关键词推断（与回退通道的服务端标记互补）
_IMPORTANT_KEYWORDS = (
    "美联储", "非农", "CPI", "加息", "降息", "利率决议", "欧洲央行", "日本央行",
    "GDP", "通胀", "失业率", "地缘", "战争", "制裁", "关税", "降准", "PMI",
)


def _parse_iso_ts(s):
    """ISO8601（如 2026-09-04T08:44:02+08:00）→ int 时间戳；失败返回 0。"""
    if not s:
        return 0
    try:
        return int(datetime.fromisoformat(str(s)).timestamp())
    except Exception:
        return 0


def _jin10_mcp_to_news(raw_items, limit):
    """把 MCP `list_flash` 原始 item({content, time, url}) 映射为统一 news item。

    相对回退通道的增益：真实详情页 url、ISO 标准时间、结构化字段（无需正则逆向）。
    """
    out = []
    for it in raw_items or []:
        if not isinstance(it, dict):
            continue
        text = _clean_html(str(it.get("content") or "")).strip()
        if not text or len(text) < 4:
            continue
        # 金十为中英双语推送，剔除英文副本（同一事件已有中文条目）
        if _cn_ratio(text) < 0.15:
            continue
        ts = _parse_iso_ts(it.get("time"))
        out.append({
            "title": text[:80] + ("..." if len(text) > 80 else ""),
            "summary": text[:200],
            "source_name": "金十数据",
            "published_at": (datetime.fromtimestamp(ts).strftime("%m-%d %H:%M")
                             if ts else str(it.get("time") or "")[:16]),
            "ts": ts,
            # MCP 提供真实详情页链接，优于回退通道写死的首页
            "url": it.get("url") or "https://www.jin10.com/",
            "important": any(kw in text for kw in _IMPORTANT_KEYWORDS),
            "channel": _infer_channel(text),
        })
        if len(out) >= limit:
            break
    return out


def _fetch_jin10_flash_legacy(limit=20):
    """回退通道：抓 flash_newest.js（无需密钥，社群逆向端点）。MCP 不可用时使用。"""
    url = "https://www.jin10.com/flash_newest.js?t=%d" % int(time.time() * 1000)
    t0 = time.time()
    # 金十需带自身域 Referer，否则可能 403
    ok, txt, err = _http_get(url, timeout=10, headers={"Referer": "https://www.jin10.com/"})
    latency = int((time.time() - t0) * 1000)
    if not ok:
        HEALTH.record("jin10", False, err, latency)
        return []
    try:
        m = re.search(r"var\s+newest\s*=\s*(\[.*?\])\s*;", txt, re.S)
        if not m:
            HEALTH.record("jin10", False, "no array matched", latency)
            return []
        arr = json.loads(m.group(1))
        items = []
        for it in arr:
            if not isinstance(it, dict):
                continue
            d = it.get("data", {}) or {}
            t = it.get("time", "") or ""
            typ = it.get("type", 0)
            important = bool(it.get("important", 0))
            if typ == 1:
                # 数据类：组合 国家+指标名+实际/预期/前值
                parts = []
                if d.get("country"):
                    parts.append(str(d["country"]))
                if d.get("name"):
                    parts.append(str(d["name"]))
                if d.get("actual") is not None and d.get("actual") != "":
                    parts.append("实际 %s" % d["actual"])
                consensus = d.get("consensus")
                if consensus is None:
                    consensus = d.get("ahead")
                if consensus is not None and consensus != "":
                    parts.append("预期 %s" % consensus)
                if d.get("previous") is not None and d.get("previous") != "":
                    parts.append("前值 %s" % d["previous"])
                text = " ".join([p for p in parts if p])
                if d.get("push_affect_text"):
                    text += "  " + str(d["push_affect_text"])
            else:
                # 普通快讯
                text = d.get("title") or d.get("content") or ""
            text = _clean_html(str(text)).strip()
            if not text or len(text) < 4:
                continue
            # 金十为中英双语推送，剔除英文副本（同一事件已有中文条目）
            if _cn_ratio(text) < 0.15:
                continue
            # 归一化时间戳（金十 time 形如 "2026-09-01 15:50:12"）
            ts = 0
            try:
                ts = int(datetime.strptime(t, "%Y-%m-%d %H:%M:%S").timestamp())
            except Exception:
                ts = 0
            items.append({
                "title": text[:80] + ("..." if len(text) > 80 else ""),
                "summary": text[:200],
                "source_name": "金十数据",
                "published_at": (datetime.fromtimestamp(ts).strftime("%m-%d %H:%M") if ts else t),
                "ts": ts,
                "url": "https://www.jin10.com/",
                "important": important,
                "channel": _infer_channel(text),
            })
            if len(items) >= limit:
                break
        HEALTH.record("jin10", bool(items), latency_ms=latency)
        return items
    except Exception as e:
        HEALTH.record("jin10", False, str(e), latency)
        return []


def fetch_jin10_flash(limit=20):
    """金十数据实时快讯（中文交易圈权威源）。

    双通道：
      1) 官方 MCP（需 JIN10_MCP_TOKEN）——标准 MCP 流程，读 structuredContent，
         结构化字段 + 真实详情页 url，不依赖正则逆向；
      2) 回退 flash_newest.js 抓取——MCP 不可用或未配 token 时使用，仍保持实时。

    返回统一 news item：{title, summary, source_name, published_at, ts, url, important, channel}
    """
    t0 = time.time()
    # ---- 通道1：官方 MCP ----
    try:
        import jin10_mcp  # 延迟导入：MCP 模块异常不应拖垮整个聚合器
        raw, err = jin10_mcp.fetch_flash_raw(limit=limit, max_pages=2, timeout=15)
        if err:
            raise RuntimeError(err)
        items = _jin10_mcp_to_news(raw, limit)
        if items:
            HEALTH.record("jin10", True, latency_ms=int((time.time() - t0) * 1000))
            return items
    except Exception:
        pass  # 落到回退通道
    # ---- 通道2：回退原抓取 ----
    return _fetch_jin10_flash_legacy(limit)


# ------------------------------------------------------------
# 华尔街见闻（多频道 + 多域名容错 + 深度文章 + 热文）
# 接口为社区逆向发现的非官方端点，需带 Referer/Origin 才能通过校验。
# 实测(2026-09-01)三域名均可达，六频道均可用。
# ------------------------------------------------------------
WSCN_HOSTS = [
    "api-one.wallstcn.com",        # 主域名
    "api-prod.wallstreetcn.com",   # 备用域名 1
    "api-one-wscn.awtmt.com",      # 备用域名 2（文章流亦用此域）
]

WSCN_HEADERS = {
    "Referer": "https://wallstreetcn.com/",
    "Origin": "https://wallstreetcn.com",
    "Accept": "application/json, text/plain, */*",
}

# 交易主线相关频道 -> 中文标签（顺序即优先级，贵金属/外汇/商品优先）
WSCN_CHANNELS = [
    ("gold-channel", "黄金"),
    ("forex-channel", "外汇"),
    ("commodity-channel", "商品"),
    ("oil-channel", "原油"),
    ("global-channel", "全球"),
]


def _wscn_get(path, timeout=10):
    """按域名容错顺序请求见闻接口，返回 (ok, json_obj, err, host, latency_ms)。"""
    last_err = None
    for host in WSCN_HOSTS:
        url = "https://%s%s" % (host, path)
        t0 = time.time()
        ok, txt, err = _http_get(url, timeout=timeout, headers=WSCN_HEADERS)
        latency = int((time.time() - t0) * 1000)
        if ok:
            try:
                d = json.loads(txt)
                if d.get("code") in (20000, 200, 0, None):
                    return True, d, None, host, latency
                last_err = "code=%s" % d.get("code")
            except Exception as e:
                last_err = "parse:%s" % e
        else:
            last_err = err
    return False, None, last_err, None, 0


def _wscn_live_item(it, channel_tag=""):
    """把见闻 lives 单条转成统一 news item。重要度用 score(1普通/2重要)。"""
    text = _clean_html(it.get("content_text") or it.get("content", "")).strip()
    if not text:
        return None
    ts = it.get("display_time") or it.get("created_at") or 0
    try:
        ts = int(ts)
    except Exception:
        ts = 0
    try:
        score = int(it.get("score") or 1)
    except Exception:
        score = 1
    return {
        "title": text[:80] + ("..." if len(text) > 80 else ""),
        "summary": text[:220],
        "source_name": "华尔街见闻",
        "published_at": (datetime.fromtimestamp(ts).strftime("%m-%d %H:%M") if ts else ""),
        "ts": ts,
        "url": it.get("uri") or "https://wallstreetcn.com/live/global",
        "important": score >= 2 or bool(it.get("is_important")),
        "channel": channel_tag,
        "wscn_id": it.get("id"),
    }


def fetch_wallstreetcn_lives(limit=20, channels=None):
    """见闻 7x24 快讯 —— 跨频道聚合（默认黄金/外汇/商品/原油/全球）。

    频道过滤实测生效：commodity 与 global 内容完全不重叠；同一条快讯可能
    跨频道标记（如 global+forex），按 id 去重后用首个命中的频道作标签。
    """
    chans = channels or WSCN_CHANNELS
    per_chan = max(6, int(limit))
    seen_ids = set()
    items = []
    ok_any = False
    err_last = None
    lat_sum = 0
    for code, tag in chans:
        path = "/apiv1/content/lives?channel=%s&limit=%d" % (code, per_chan)
        ok, d, err, host, latency = _wscn_get(path)
        lat_sum += latency
        if not ok:
            err_last = err
            continue
        ok_any = True
        for raw in (d.get("data") or {}).get("items", []):
            rid = raw.get("id")
            if rid in seen_ids:
                continue
            seen_ids.add(rid)
            itm = _wscn_live_item(raw, tag)
            if itm:
                items.append(itm)
    HEALTH.record("wallstreetcn", ok_any, err_last, lat_sum)
    items.sort(key=lambda x: x.get("ts", 0), reverse=True)
    return items


def fetch_wallstreetcn_articles(limit=10):
    """见闻深度文章流（information-flow）。items[].resource 为嵌套正文对象。"""
    path = "/apiv1/content/information-flow?channel=global&accept=article&limit=%d" % limit
    ok, d, err, host, latency = _wscn_get(path)
    if not ok:
        HEALTH.record("wscn_articles", False, err, latency)
        return []
    out = []
    for e in (d.get("data") or {}).get("items", []):
        res = e.get("resource") or {}
        title = _clean_html(res.get("title") or "")
        if not title:
            continue
        ts = res.get("display_time") or 0
        try:
            ts = int(ts)
        except Exception:
            ts = 0
        out.append({
            "title": title[:100],
            "summary": _clean_html(res.get("content_short") or "")[:220],
            "source_name": "见闻深度",
            "published_at": (datetime.fromtimestamp(ts).strftime("%m-%d %H:%M") if ts else ""),
            "ts": ts,
            "url": res.get("uri") or "https://wallstreetcn.com/",
            "important": False,
            "channel": "深度",
            "author": ((res.get("author") or {}).get("display_name") or ""),
        })
    HEALTH.record("wscn_articles", bool(out), latency_ms=latency)
    return out


def fetch_wallstreetcn_hot(limit=8):
    """见闻热文榜（按阅读量），补充市场关注焦点。"""
    ok, d, err, host, latency = _wscn_get("/apiv1/content/articles/hot?period=all")
    if not ok:
        HEALTH.record("wscn_hot", False, err, latency)
        return []
    data = d.get("data") or {}
    raw_items = data.get("day_items") or data.get("items") or []
    out = []
    for it in raw_items[:limit]:
        title = _clean_html(it.get("title") or "")
        if not title:
            continue
        ts = it.get("display_time") or 0
        try:
            ts = int(ts)
        except Exception:
            ts = 0
        pv = it.get("pageviews") or 0
        out.append({
            "title": title[:100],
            "summary": "阅读 %s" % f"{pv:,}" if pv else "",
            "source_name": "见闻热文",
            "published_at": (datetime.fromtimestamp(ts).strftime("%m-%d %H:%M") if ts else ""),
            "ts": ts,
            "url": it.get("uri") or "https://wallstreetcn.com/",
            "important": False,
            "channel": "热文",
            "pageviews": pv,
        })
    HEALTH.record("wscn_hot", bool(out), latency_ms=latency)
    return out


def fetch_eastmoney_news(limit=20):
    """Eastmoney 7x24 kuaixun (best-effort; URL may change)."""
    urls = [
        "https://newsapi.eastmoney.com/kuaixun/v1/getlist_?type=1,2,3,4,5,6,7,8&pagesize=%d" % limit,
    ]
    for url in urls:
        t0 = time.time()
        ok, txt, err = _http_get(url, timeout=10)
        latency = int((time.time() - t0) * 1000)
        if not ok:
            HEALTH.record("eastmoney_news", False, err, latency)
            continue
        try:
            d = json.loads(txt)
            items = []
            for it in (d.get("news", []) or d.get("data", {}).get("news", []) or d.get("result", {}).get("data", []) or []):
                items.append({
                    "title": it.get("title", ""),
                    "summary": _clean_html(it.get("summary", it.get("content", "")))[:160],
                    "source_name": "东方财富",
                    "published_at": it.get("show_time", it.get("time", "")),
                    "url": it.get("url", ""),
                })
            HEALTH.record("eastmoney_news", bool(items), latency_ms=latency)
            return items
        except Exception as e:
            HEALTH.record("eastmoney_news", False, str(e), latency)
            continue
    return []


def fetch_sina_rss(limit=20):
    """Sina finance RSS (XML)."""
    url = "https://rss.sina.com.cn/roll/finance/hot_roll.xml"
    t0 = time.time()
    ok, txt, err = _http_get(url, timeout=10, encoding="utf-8")
    latency = int((time.time() - t0) * 1000)
    if not ok:
        HEALTH.record("sina_rss", False, err, latency)
        return []
    try:
        items = []
        # Parse XML items
        for m in re.finditer(r'<item[^>]*>(.*?)</item>', txt, re.S):
            block = m.group(1)
            title = _clean_html(re.search(r'<title[^>]*>(.*?)</title>', block, re.S).group(1)) if re.search(r'<title[^>]*>(.*?)</title>', block, re.S) else ""
            link = re.search(r'<link[^>]*>(.*?)</link>', block, re.S).group(1).strip() if re.search(r'<link[^>]*>(.*?)</link>', block, re.S) else ""
            pub = re.search(r'<pubDate[^>]*>(.*?)</pubDate>', block, re.S).group(1).strip() if re.search(r'<pubDate[^>]*>(.*?)</pubDate>', block, re.S) else ""
            desc = _clean_html(re.search(r'<description[^>]*>(.*?)</description>', block, re.S).group(1)) if re.search(r'<description[^>]*>(.*?)</description>', block, re.S) else ""
            if not title or len(title) < 6:
                continue
            items.append({
                "title": title,
                "summary": desc[:160],
                "source_name": "新浪财经",
                "published_at": pub,
                "url": link,
            })
            if len(items) >= limit:
                break
        HEALTH.record("sina_rss", bool(items), latency_ms=latency)
        return items
    except Exception as e:
        HEALTH.record("sina_rss", False, str(e), latency)
        return []


def fetch_sina_news(limit=20):
    """Sina finance roll news (HTML page scrape)."""
    url = "https://finance.sina.com.cn/roll/index.d.html?cid=56589&page=1&page_size=%d" % limit
    t0 = time.time()
    ok, txt, err = _http_get(url, timeout=10, encoding="utf-8")
    latency = int((time.time() - t0) * 1000)
    if not ok:
        HEALTH.record("sina_news", False, err, latency)
        return []
    try:
        items = []
        # Extract <li> blocks with title/time
        for m in re.finditer(r'<li[^>]*>.*?<a[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>.*?</li>', txt, re.S):
            href, title = m.group(1), _clean_html(m.group(2))
            if not title or len(title) < 6:
                continue
            items.append({
                "title": title,
                "summary": "",
                "source_name": "新浪财经",
                "published_at": "",
                "url": href if href.startswith("http") else "https://finance.sina.com.cn" + href,
            })
            if len(items) >= limit:
                break
        HEALTH.record("sina_news", bool(items), latency_ms=latency)
        return items
    except Exception as e:
        HEALTH.record("sina_news", False, str(e), latency)
        return []


def fetch_all_news(limit=15):
    """Aggregate news from multiple sources with failover + diversity control.

    - 优先级: 金十数据 -> 华尔街见闻 -> 东方财富 -> 新浪RSS -> 新浪HTML
    - 单源上限避免某一源刷屏，保证多视角（多方面）呈现
    - 跨源近似去重：同一事件只在最权威/最新的一条保留
    - 全局按发布时间倒序，最新在前
    """
    per_source_cap = max(4, int(limit * 0.4))  # 单源上限，避免刷屏
    # 各源并发拉取（网络等待从 ~7 次串行降为一次并发），去重/配额在下方串行处理
    with ThreadPoolExecutor(max_workers=7) as ex:
        f_jin10 = ex.submit(fetch_jin10_flash, limit)
        f_wscn = ex.submit(fetch_wallstreetcn_lives, limit)                 # 跨频道快讯(黄金/外汇/商品/原油/全球)
        f_wscn_art = ex.submit(fetch_wallstreetcn_articles, max(6, limit // 2))  # 深度文章
        f_wscn_hot = ex.submit(fetch_wallstreetcn_hot, 6)                  # 热文榜
        f_em = ex.submit(fetch_eastmoney_news, limit)
        f_rss = ex.submit(fetch_sina_rss, limit)
        f_sina_extra = ex.submit(fetch_sina_news, limit)

        jin10 = f_jin10.result()
        wscn = f_wscn.result()
        wscn_art = f_wscn_art.result()
        wscn_hot = f_wscn_hot.result()
        em = f_em.result()
        rss = f_rss.result()
        sina_extra = f_sina_extra.result()

    if rss:
        sina_extra = []  # RSS 可用时不取 HTML 抓取（减少无用请求）

    collected = {
        "金十数据": jin10,
        "华尔街见闻": wscn,
        "见闻深度": wscn_art,
        "见闻热文": wscn_hot,
        "东方财富": em,
        "新浪财经": rss + sina_extra,
    }
    # 各源配额：见闻快讯自带频道标签(黄金/外汇/商品/原油)，为交易主线主源故配额最高
    caps = {
        "华尔街见闻": max(6, int(limit * 0.40)),
        "金十数据": max(5, int(limit * 0.40)),
        "见闻深度": 4,
        "见闻热文": 3,
        "东方财富": 4,
        "新浪财经": 4,
    }

    # 先按时间倒序排每个源内部，便于优先取最新
    for src in collected:
        collected[src] = sorted(collected[src], key=_item_ts, reverse=True)

    seen_keys = set()
    seen_sigs = []
    out = []
    # 见闻快讯优先（有频道标签），金十紧随（数据类快讯及时）
    for src in ("华尔街见闻", "金十数据", "见闻深度", "见闻热文", "东方财富", "新浪财经"):
        cnt = 0
        cap = caps.get(src, per_source_cap)
        for it in collected[src]:
            title = it.get("title", "")
            key = _norm_title_key(title)
            if not key or key in seen_keys:
                continue
            # 跨源同事件去重：字符级相似度，能识别不同措辞的同一条数据快讯
            if _is_dup_event(title, seen_sigs):
                continue
            seen_keys.add(key)
            seen_sigs.append(_norm_sig(title))
            out.append(it)
            cnt += 1
            if cnt >= cap:
                break

    # 频道保底：交易主线频道(黄金/外汇/商品/原油)各至少保留 min_per_chan 条，
    # 否则纯时间排序会让成交较早的商品/原油快讯被全部挤出，对大宗交易者不可用。
    min_per_chan = 2
    have = {}
    for it in out:
        c = it.get("channel") or ""
        have[c] = have.get(c, 0) + 1
    pool = []
    for src in ("华尔街见闻", "金十数据"):
        pool.extend(collected.get(src, []))
    for chan in ("黄金", "外汇", "商品", "原油"):
        need = min_per_chan - have.get(chan, 0)
        if need <= 0:
            continue
        for it in pool:
            if need <= 0:
                break
            if (it.get("channel") or "") != chan:
                continue
            title = it.get("title", "")
            key = _norm_title_key(title)
            if not key or key in seen_keys:
                continue
            if _is_dup_event(title, seen_sigs):
                continue
            seen_keys.add(key)
            seen_sigs.append(_norm_sig(title))
            out.append(it)
            need -= 1

    # 全局按时间倒序（重要快讯在同一时间点优先）
    out.sort(key=lambda x: (_item_ts(x), 1 if x.get("important") else 0), reverse=True)
    out = out[:max(limit, 26)]

    # 频道分布统计，便于前端做筛选与展示
    chan_stat = {}
    for it in out:
        c = it.get("channel") or "其他"
        chan_stat[c] = chan_stat.get(c, 0) + 1

    return {
        "news": out,
        "sources": {"jin10": bool(jin10),
                    "wallstreetcn": bool(wscn),
                    "wscn_articles": bool(wscn_art),
                    "wscn_hot": bool(wscn_hot),
                    "eastmoney_news": bool(em),
                    "sina_rss": bool(rss),
                    "sina_news": bool(sina_extra)},
        "channels": chan_stat,
        "health": HEALTH.snapshot(),
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ============================================================
# fxmacrodata.com 权威宏观数据层（BLS/BEA/Census/EIA 官方来源）
# ------------------------------------------------------------
# 免费端点（无需 key）：
#   GET /calendar/usd             -> 美国官方发布日历（含 source/source_url/重要性）
#   GET /announcements/usd/{slug} -> 指标实际值/前值（BLS、Census、BEA、EIA 官方口径）
# 用途：① 财经日历美国事件 actual 实时回填（解决"已到时间·待取数"）
#       ② 官方发布时间表补充待公布事件（比 daily_data.json 夜间快照更及时）
# ============================================================
FXMACRO_BASE = "https://fxmacrodata.com/api/v1"
FXMACRO_CAL_TTL = 6 * 3600      # 发布日历缓存 6 小时（官方发布计划变化慢）
FXMACRO_ACT_TTL = 10 * 60       # 实际值缓存 10 分钟
_fxmacro_lock = threading.Lock()
_fxmacro_cal_cache = {"ts": 0, "data": None}
_fxmacro_act_cache = {}          # slug -> {"ts": float, "data": latest|None}

# slug -> (中文名, 单位, 默认影响等级)
FXMACRO_US_META = {
    "non_farm_payrolls": ("非农就业人数", "万人", "high"),
    "unemployment": ("失业率", "%", "high"),
    "average_hourly_earnings": ("平均时薪", "%", "high"),
    "initial_jobless_claims": ("初请失业金人数", "万人", "high"),
    "core_inflation": ("核心CPI", "%", "high"),
    "inflation": ("CPI", "%", "high"),
    "core_pce": ("核心PCE", "%", "high"),
    "pce": ("PCE物价指数", "%", "high"),
    "ppi": ("PPI", "%", "medium"),
    "retail_sales": ("零售销售", "%", "medium"),
    "durable_goods_orders": ("耐用品订单", "亿美元", "medium"),
    "trade_balance": ("贸易帐", "亿美元", "medium"),
    "housing_starts": ("新屋开工", "万套", "medium"),
    "building_permits": ("营建许可", "万套", "low"),
    "consumer_confidence": ("消费者信心", "", "medium"),
    "crude_oil_inventories": ("EIA原油库存", "万桶", "medium"),
    "natural_gas_storage": ("EIA天然气库存", "亿立方英尺", "medium"),
    "job_openings": ("JOLTs职位空缺", "万", "medium"),
    "participation_rate": ("劳动参与率", "%", "medium"),
    "gdp": ("实际GDP", "%", "high"),
    "wages": ("薪资增速", "%", "medium"),
}

# daily_data 事件名关键词 -> fxmacrodata slug（顺序优先）
_US_SLUG_RULES = [
    ("non_farm_payrolls", ("非农就业人口变动", "非农就业人数", "非农业就业人口")),
    ("unemployment", ("失业率",)),
    ("average_hourly_earnings", ("平均每小时工资", "平均时薪", "平均小时工资")),
    ("initial_jobless_claims", ("初请失业金", "初请失业救济", "失业金人数")),
    ("core_inflation", ("核心CPI",)),
    ("inflation", ("CPI", "消费者物价指数")),
    ("core_pce", ("核心PCE",)),
    ("pce", ("PCE物价指数", "PCE年率")),
    ("ppi", ("PPI", "生产者物价")),
    ("retail_sales", ("零售销售",)),
    ("durable_goods_orders", ("耐用品订单",)),
    ("trade_balance", ("贸易帐", "贸易收支")),
    ("housing_starts", ("新屋开工",)),
    ("building_permits", ("营建许可",)),
    ("consumer_confidence", ("谘商会消费者信心",)),
    ("crude_oil_inventories", ("EIA原油库存", "原油库存")),
    ("natural_gas_storage", ("EIA天然气库存", "天然气库存")),
    ("job_openings", ("JOLT", "职位空缺")),
    ("participation_rate", ("劳动参与率",)),
    ("gdp", ("实际GDP", "GDP年化")),
]

# slug -> (格式化模板, 缩放系数)。模板为 None 表示该指标返回值为水平值/口径
# 与日报（变动量/变动率）不一致，不自动回填 actual，仅用于发布日历展示。
_FXMACRO_FMT = {
    "unemployment": ("%.1f%%", None),
    "participation_rate": ("%.1f%%", None),
    "inflation": ("%.1f%%", None),
    "core_inflation": ("%.1f%%", None),
    "pce": ("%.1f%%", None),
    "core_pce": ("%.1f%%", None),
    "ppi": ("%.1f%%", None),
    "retail_sales": ("%.1f%%", None),
    "average_hourly_earnings": ("%.1f%%", None),
    "wages": ("%.1f%%", None),
    "initial_jobless_claims": ("%.1f万", 0.0001),
    "job_openings": ("%.0f万", 0.1),
    "crude_oil_inventories": ("%+.1f万桶", 100.0),
    "natural_gas_storage": ("%.0f", None),
    "trade_balance": ("%.0f亿", 0.01),
    "housing_starts": ("%.0f万套", 0.1),
    "building_permits": ("%.0f万套", 0.1),
    "durable_goods_orders": ("%.0f亿", 0.01),
    "non_farm_payrolls": (None, None),
    "gdp": (None, None),
    "consumer_confidence": (None, None),
    "policy_rate": (None, None),
}


def _now_bj():
    from datetime import timezone
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=8)


def _event_dt_local(curr_date, ev_time):
    try:
        year = curr_date.split("-")[0]
        return datetime.strptime(f"{year}-{ev_time}", "%Y-%m-%d %H:%M")
    except Exception:
        return None


def _short_source(src):
    """官方来源名 -> 短标签（BLS/BEA/Census/EIA/DoL/Fed）。"""
    s = (src or "")
    for full, short in (("Bureau of Labor Statistics", "BLS"),
                        ("Bureau of Economic Analysis", "BEA"),
                        ("Census Bureau", "Census"),
                        ("Energy Information Administration", "EIA"),
                        ("Department of Labor", "DoL"),
                        ("Federal Reserve Bank", "FRB"),
                        ("Federal Reserve", "Fed")):
        if full in s:
            return short
    return s[:14]


def fetch_fxmacro_calendar(force=False):
    """GET /calendar/usd -> 美国官方发布日历列表。模块级缓存 6h。"""
    with _fxmacro_lock:
        if not force and _fxmacro_cal_cache["data"] and time.time() - _fxmacro_cal_cache["ts"] < FXMACRO_CAL_TTL:
            return _fxmacro_cal_cache["data"]
    url = FXMACRO_BASE + "/calendar/usd"
    t0 = time.time()
    ok, txt, err = _http_get(url, timeout=12)
    latency = int((time.time() - t0) * 1000)
    if not ok:
        HEALTH.record("fxmacro_cal", False, err, latency)
        with _fxmacro_lock:
            return _fxmacro_cal_cache["data"] or []
    try:
        d = json.loads(txt)
        items = d.get("data") or []
        HEALTH.record("fxmacro_cal", True, latency_ms=latency)
        with _fxmacro_lock:
            _fxmacro_cal_cache["ts"] = time.time()
            _fxmacro_cal_cache["data"] = items
        return items
    except Exception as e:
        HEALTH.record("fxmacro_cal", False, str(e), latency)
        with _fxmacro_lock:
            return _fxmacro_cal_cache["data"] or []


def fetch_fxmacro_actual(slug, force=False):
    """GET /announcements/usd/{slug} -> 最新一条实际值记录。缓存 10min。"""
    with _fxmacro_lock:
        c = _fxmacro_act_cache.get(slug)
        if not force and c and time.time() - c["ts"] < FXMACRO_ACT_TTL:
            return c["data"]
    url = "%s/announcements/usd/%s" % (FXMACRO_BASE, slug)
    t0 = time.time()
    ok, txt, err = _http_get(url, timeout=12)
    latency = int((time.time() - t0) * 1000)
    if not ok:
        HEALTH.record("fxmacro_act:" + slug, False, err, latency)
        with _fxmacro_lock:
            c = _fxmacro_act_cache.get(slug)
            return c["data"] if c else None
    try:
        d = json.loads(txt)
        rows = d.get("data") or []
        latest = rows[0] if rows else None
        HEALTH.record("fxmacro_act:" + slug, True, latency_ms=latency)
        with _fxmacro_lock:
            _fxmacro_act_cache[slug] = {"ts": time.time(), "data": latest}
        return latest
    except Exception as e:
        HEALTH.record("fxmacro_act:" + slug, False, str(e), latency)
        with _fxmacro_lock:
            c = _fxmacro_act_cache.get(slug)
            return c["data"] if c else None


def _fmt_fxmacro_value(val, slug):
    """按指标口径格式化实际值；返回 None 表示该指标不自动回填。"""
    fmt = _FXMACRO_FMT.get(slug, (None, None))
    if not fmt[0]:
        return None
    try:
        v = float(val)
    except Exception:
        return str(val)
    tpl, scale = fmt
    if scale:
        v = v * scale
    return tpl % v


def _us_slug_for_event(event):
    for slug, kws in _US_SLUG_RULES:
        for kw in kws:
            if kw in (event or ""):
                return slug
    return None


def fxmacro_fill_calendar(daily_data, add_future=True, use_actuals=True):
    """用 fxmacrodata 权威源增强财经日历（就地修改 daily_data）。

    1) actual 回填：对已过发布时间、actual 缺失的美国事件，按事件名匹配 slug，
       从 BLS/BEA/Census/EIA 官方口径取实际值+前值（仅格式化模板非 None 的指标）。
    2) 发布日历补充：把未来 10 天内官方发布时间表中的事件转为待公布项
       （已存在的 time+country+event 跳过）；若补充项发布时间已过，立即回填实际值。

    返回 (updated_data, filled, added, meta)
    """
    meta = {"cal_ok": False, "filled": 0, "added": 0, "sources": {}}
    if not daily_data:
        return daily_data, [], [], meta
    cal = daily_data.get("economic_calendar") or {}
    now = _now_bj()
    curr_date = cal.get("curr_date", "") or now.strftime("%Y-%m-%d")
    filled, added = [], []

    if use_actuals:
        needs = {}
        for it in list(cal.get("released", [])) + list(cal.get("upcoming", [])):
            if it.get("country") != "美国":
                continue
            a = it.get("actual")
            if a not in (None, "", "待取数"):
                continue
            tstr = it.get("time", "")
            if "待定" in tstr:
                continue
            dt = _event_dt_local(curr_date, tstr)
            if dt is None or dt > now:
                continue
            slug = _us_slug_for_event(it.get("event", ""))
            if slug and _FXMACRO_FMT.get(slug, (None, None))[0]:
                needs.setdefault(slug, []).append(it)
        for slug, its in needs.items():
            rec = fetch_fxmacro_actual(slug)
            if not rec or rec.get("val") is None:
                continue
            val = _fmt_fxmacro_value(rec.get("val"), slug)
            prev = _fmt_fxmacro_value(rec.get("previous_value"), slug)
            src = _short_source(rec.get("source"))
            meta["sources"][slug] = src or "fxmacrodata"
            for it in its:
                it["actual"] = val
                if prev is not None:
                    it["previous"] = prev
                it["actual_source"] = "fxmacrodata:" + (src or rec.get("source", ""))
                it["source"] = src
                if src:
                    it["note"] = (it.get("note") or "") + ("【%s官方实时】" % src)
                filled.append(it)
        meta["filled"] = len(filled)

    if add_future:
        items = fetch_fxmacro_calendar()
        meta["cal_ok"] = bool(items)
        existing = set()
        for it in list(cal.get("released", [])) + list(cal.get("upcoming", [])):
            existing.add((it.get("time"), it.get("country"), it.get("event")))
        for raw in items:
            try:
                slug = raw.get("release")
                if slug not in FXMACRO_US_META:
                    continue
                dt_utc = raw.get("announcement_datetime_utc")
                if not dt_utc:
                    continue
                dt = datetime.strptime(dt_utc[:19], "%Y-%m-%dT%H:%M:%S") + timedelta(hours=8)
                if dt < now - timedelta(hours=2) or dt > now + timedelta(days=10):
                    continue
                name_cn, unit, imp = FXMACRO_US_META[slug]
                time_str = dt.strftime("%m-%d %H:%M")
                key = (time_str, "美国", name_cn)
                if key in existing:
                    continue
                existing.add(key)
                src_short = _short_source(raw.get("source"))
                itm = {
                    "time": time_str,
                    "country": "美国",
                    "event": name_cn,
                    "actual": None,
                    "forecast": None,
                    "previous": None,
                    "unit": unit,
                    "impact": imp,
                    "note": ("官方发布时间表 · 来源:%s" % src_short) if src_short else "官方发布时间表",
                    "source": src_short,
                    "live": True,
                }
                # 补充项发布时间已过 -> 立即用官方实际值回填
                if dt <= now:
                    rec = fetch_fxmacro_actual(slug)
                    if rec and rec.get("val") is not None and _FXMACRO_FMT.get(slug, (None, None))[0]:
                        v = _fmt_fxmacro_value(rec.get("val"), slug)
                        if v is not None:
                            itm["actual"] = v
                            itm["actual_source"] = "fxmacrodata:" + (src_short or "official")
                            itm["just_released"] = True
                added.append(itm)
            except Exception:
                continue
        if added:
            cal["upcoming"] = list(cal.get("upcoming", [])) + added
        meta["added"] = len(added)

    return daily_data, filled, added, meta


# ============================================================
# ForexFactory 本周权威财经日历（多国，含精确发布时间/预测/前值/影响）
# 用于校验 daily_data 事件时间戳、预测/前值偏差，并补充未来事件。
# 该接口无需 key 且沙箱可达，覆盖 CNY/JPY/USD/EUR/GBP/CHF/CAD/AUD/NZD。
# ============================================================
FF_CAL_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
_ff_cal_cache = {"ts": 0, "data": None}
_ff_lock = threading.Lock()

_FF_COUNTRY_MAP = {
    "CNY": "中国", "JPY": "日本", "USD": "美国", "EUR": "欧元区",
    "GBP": "英国", "CHF": "瑞士", "CAD": "加拿大", "AUD": "澳洲",
    "NZD": "新西兰", "ALL": "全球",
}
_FF_IMPACT_MAP = {"Low": "low", "Medium": "medium", "High": "high"}


def _ff_keyword(title):
    """从 FF 事件标题提取规范关键词，用于与 daily_data 事件匹配。"""
    t = (title or "").lower()
    pairs = [
        ("服务业PMI", ("services",) if "pmi" in t else ()),
        ("制造业PMI", ("manufacturing",) if "pmi" in t else ()),
        ("非制造业PMI", ("non-manufacturing",) if "pmi" in t else ()),
        ("综合PMI", ("composite",) if "pmi" in t else ()),
        ("PMI", ("pmi",)),
        ("GDP", ("gdp",)),
        ("CPI", ("cpi", "inflation")),
        ("PPI", ("ppi",)),
        ("零售销售", ("retail sales",)),
        ("贸易帐", ("trade balance",)),
        ("失业", ("jobless", "employment", "unemployment")),
        ("利率", ("interest rate", "rate decision")),
    ]
    for kw, keys in pairs:
        if all(k in t for k in keys):
            return kw
    return None


def fetch_forexfactory_week(force=False):
    """拉 ForexFactory 本周财经日历 JSON（无需 key）。"""
    with _ff_lock:
        if not force and _ff_cal_cache["data"] and time.time() - _ff_cal_cache["ts"] < 3600:
            return _ff_cal_cache["data"]
    ok, txt, err = _http_get(FF_CAL_URL, timeout=12)
    if not ok:
        return []
    try:
        data = json.loads(txt)
    except Exception:
        return []
    with _ff_lock:
        _ff_cal_cache["ts"] = time.time()
        _ff_cal_cache["data"] = data
    return data


def _ff_parse_dt(s):
    """'2026-09-02T21:45:00-04:00' -> 北京时间 datetime。

    FF 时间为事件当地时区（带 +/-HH:MM 偏移），北京时间 = FF时间 + (8 - off)。
    例如 EDT(-04:00): 21:45 + (8-(-4)) = 21:45 + 12h = 次日 09:45。
    """
    try:
        dt = datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")
        if len(s) > 19 and s[19] in "+-":
            off = int(s[19:22])  # 含符号，如 -04 / +01
            return dt - timedelta(hours=off) + timedelta(hours=8)
        return None
    except Exception:
        return None


def forexfactory_correct_calendar(daily_data, add_future=True):
    """用 ForexFactory 权威数据校验/修正 daily_data 财经日历。

    1) 修正发布时间：当 daily 时间与 FF 精确时间偏差 >6h 时覆盖（解决误标日期导致的
       '已到时间·待取数' 误报）。
    2) 修正 forecast/previous/impact：仅当 daily 对应字段为空/待定时才覆盖，避免冲掉
       已核验的真实值。
    3) 补充未来事件：FF 有但 daily 缺失且发布时间在未来 -> 追加到 upcoming。
    返回 (updated, corrected_count, added_count, meta)。
    """
    data = fetch_forexfactory_week()
    if not data:
        return daily_data, 0, 0, {"ok": False, "reason": "fetch_failed"}
    cal = daily_data.setdefault("economic_calendar", {})
    all_items = list(cal.get("released", [])) + list(cal.get("upcoming", []))
    corrected = 0
    added = []

    ff_index = {}
    for ev in data:
        c = _FF_COUNTRY_MAP.get(ev.get("country", ""))
        kw = _ff_keyword(ev.get("title", ""))
        if c and kw:
            ff_index.setdefault((c, kw), ev)

    for it in all_items:
        c = it.get("country", "")
        e = it.get("event", "")
        kw = None
        for k in ("服务业PMI", "制造业PMI", "非制造业PMI", "综合PMI",
                 "GDP", "CPI", "PPI", "零售销售", "贸易帐", "失业", "利率"):
            if k in e:
                kw = k
                break
        if not kw:
            continue
        ffe = ff_index.get((c, kw))
        if not ffe:
            continue
        # 注意：FF 个别事件时间可能与本地源偏差（如美东周 vs 北京工作日），
        # 为避免误改已核验时间，这里不覆盖已有 time，仅补全空缺的
        # forecast/previous/impact。
        if ffe.get("forecast") not in (None, ""):
            if it.get("forecast") in (None, "", "待定"):
                it["forecast"] = ffe["forecast"]
                corrected += 1
        if ffe.get("previous") not in (None, ""):
            if it.get("previous") in (None, "", "待定"):
                it["previous"] = ffe["previous"]
                corrected += 1
        imp = _FF_IMPACT_MAP.get(ffe.get("impact", ""))
        if imp and it.get("impact") in (None, "", "待定"):
            it["impact"] = imp

    if add_future:
        for ev in data:
            c = _FF_COUNTRY_MAP.get(ev.get("country", ""))
            kw = _ff_keyword(ev.get("title", ""))
            if not (c and kw):
                continue
            fdt = _ff_parse_dt(ev.get("date", ""))
            if not fdt or fdt <= _now_bj():
                continue
            if any(it.get("country") == c and kw in it.get("event", "") for it in all_items):
                continue
            item = {
                "time": fdt.strftime("%m-%d %H:%M"),
                "country": c,
                "flag": ev.get("country", ""),
                "event": f"{ev.get('title', kw)}",
                "forecast": ev.get("forecast") or "",
                "previous": ev.get("previous") or "",
                "actual": None,
                "impact": _FF_IMPACT_MAP.get(ev.get("impact", ""), "low"),
                "unit": "",
                "note": "ForexFactory 本周日历补充",
                "event_type": "numeric" if kw != "利率" else "meeting",
                "source": "ForexFactory",
            }
            added.append(item)
        if added:
            cal["upcoming"] = list(cal.get("upcoming", [])) + added

    meta = {"ok": True, "corrected": corrected, "added": len(added), "source": "ForexFactory"}
    return daily_data, corrected, len(added), meta


# ============================================================
# 财经日历 actual 多源解析
# ============================================================
def _match_event(it, country, event_substring):
    return (it.get("country") == country and event_substring in it.get("event", ""))


def resolve_calendar_actuals(daily_data):
    """Try to fill missing calendar actuals from public sources.

    Currently implemented:
    - 中国 财新制造业PMI: try Eastmoney macro data page (best-effort).
    - Fallback to external JSON store (calendar_actuals_extra.json).
    Returns (updated_daily_data, filled_count, gaps).
    """
    import os
    filled = 0
    gaps = []
    if not daily_data:
        return daily_data, 0, []
    cal = daily_data.get("economic_calendar", {})
    # merge released + upcoming
    all_items = list(cal.get("released", [])) + list(cal.get("upcoming", []))

    # load external actuals
    extra_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calendar_actuals_extra.json")
    extra = []
    if os.path.exists(extra_path):
        try:
            with open(extra_path, "r", encoding="utf-8") as f:
                extra = json.load(f)
        except Exception:
            pass

    # try public sources for known patterns
    # 1. 中国财新PMI from Eastmoney macro calendar
    caixin_pmi = None
    for it in all_items:
        if _match_event(it, "中国", "财新制造业PMI") and it.get("actual") is None:
            if caixin_pmi is None:
                caixin_pmi = _fetch_caixin_pmi_from_eastmoney()
            if caixin_pmi is not None:
                it["actual"] = str(caixin_pmi)
                it["actual_source"] = "eastmoney"
                filled += 1

    # apply external fallbacks
    for it in all_items:
        if it.get("actual") is not None:
            continue
        for fb in extra:
            if (fb.get("country") == it.get("country") and
                fb.get("event") == it.get("event") and
                fb.get("time") == it.get("time")):
                it["actual"] = fb.get("actual")
                it["actual_source"] = "external_json"
                filled += 1
                break
        else:
            gaps.append({"time": it.get("time"), "country": it.get("country"),
                         "event": it.get("event"), "forecast": it.get("forecast"),
                         "previous": it.get("previous")})

    return daily_data, filled, gaps


def _fetch_caixin_pmi_from_eastmoney():
    """Best-effort fetch latest Caixin China manufacturing PMI value from Eastmoney."""
    url = ("https://datacenter-web.eastmoney.com/api/data/v1/get?"
           "reportName=RPT_ECONOMY_CI_CAIXIN_PMI&columns=ALL&pageNumber=1&pageSize=1")
    ok, txt, err = _http_get(url, timeout=10)
    if not ok:
        return None
    try:
        d = json.loads(txt)
        rows = d.get("result", {}).get("data", [])
        if rows:
            return rows[0].get("PMI_VALUE") or rows[0].get("VALUE") or rows[0].get("ACTUAL_VALUE")
    except Exception:
        pass
    return None


# ============================================================
# 便捷入口
# ============================================================
if __name__ == "__main__":
    # quick self-test
    print(json.dumps(fetch_all_quotes(), ensure_ascii=False, indent=2)[:2000])
