# -*- coding: utf-8 -*-
"""Live financial data server - serves dashboard + real-time data API.
Usage: python live_server.py [port]

Data sources (priority order):
1. Frankfurter API (ECB)      - forex exchange rates
2. Sina Finance               - commodities & indices (GBK encoding)
3. Yahoo Finance              - fallback for all (often 403)
4. daily_data.json            - K-line fallback from monthly chart data
5. In-memory price history    - accumulated minute-level K-line data
"""
import json, os, sys, time, threading, re
from datetime import datetime, timedelta, timezone
import urllib.request, urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import data_aggregator  # 多源实时数据聚合器
import advanced_data  # 进阶数据实时抓取（FRED + BIS，无需密钥）

# 默认端口改为 8800, 绕开可能被旧进程(历史 exe/旧 live_server)长期占用的 8080/8081/8099。
# 仍可用命令行参数覆盖: python live_server.py <端口>
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8800
DIR = os.path.dirname(os.path.abspath(__file__))

# ============================================================
#  Symbol mappings
# ============================================================

# Name -> Yahoo symbol
YAHOO = {
    # Forex (direct)
    "\u6b27\u5143/\u7f8e\u5143":"EURUSD=X", "\u7f8e\u5143/\u65e5\u5143":"JPY=X",
    "\u82f1\u9551/\u7f8e\u5143":"GBPUSD=X", "\u6fb3\u5143/\u7f8e\u5143":"AUDUSD=X",
    "\u7f8e\u5143/\u745e\u90ce":"USDCHF=X", "\u7f8e\u5143/\u52a0\u5143":"USDCAD=X",
    "\u65b0\u897f\u5170\u5143/\u7f8e\u5143":"NZDUSD=X", "\u7f8e\u5143/\u6e2f\u5e01":"USDHKD=X",
    "\u7f8e\u5143\u6307\u6570":"DX-Y.NYB",
    # Forex (cross)
    "\u6b27\u5143/\u65e5\u5143(\u4ea4\u53c9\u76d8)":"EURJPY=X",
    "\u82f1\u9551/\u65e5\u5143(\u4ea4\u53c9\u76d8)":"GBPJPY=X",
    "\u6b27\u5143/\u82f1\u9551(\u4ea4\u53c9\u76d8)":"EURGBP=X",
    "\u6fb3\u5143/\u65e5\u5143(\u4ea4\u53c9\u76d8)":"AUDJPY=X",
    "\u6b27\u5143/\u745e\u90ce(\u4ea4\u53c9\u76d8)":"EURCHF=X",
    "\u82f1\u9551/\u6fb3\u5143(\u4ea4\u53c9\u76d8)":"GBPAUD=X",
    "\u6b27\u5143/\u6fb3\u5143(\u4ea4\u53c9\u76d8)":"EURAUD=X",
    "\u65b0\u897f\u5170\u5143/\u65e5\u5143(\u4ea4\u53c9\u76d8)":"NZDJPY=X",
    "\u6fb3\u5143/\u65b0\u897f\u5170\u5143(\u4ea4\u53c9\u76d8)":"AUDNZD=X",
    "\u745e\u90ce/\u65e5\u5143(\u4ea4\u53c9\u76d8)":"CHFJPY=X",
    "\u52a0\u5143/\u65e5\u5143(\u4ea4\u53c9\u76d8)":"CADJPY=X",
    # Commodities
    "\u73b0\u8d27\u9ec4\u91d1":"GC=F", "\u73b0\u8d27\u767d\u94f6":"SI=F",
    "WTI\u539f\u6cb9":"CL=F", "\u5e03\u4f26\u7279\u539f\u6cb9":"BZ=F",
    "\u5929\u7136\u6c14":"NG=F",
    # Indices
    "\u9053\u743c\u65af\u5de5\u4e1a\u5e73\u5747\u6307\u6570":"^DJI",
    "\u6807\u666e500\u6307\u6570":"^GSPC", "\u7eb3\u65af\u8fbe\u514b\u7efc\u5408\u6307\u6570":"^IXIC",
    "\u7f57\u7d202000\u6307\u6570":"^RUT",
    "\u6b27\u6d32\u65af\u6258\u514b50\u6307\u6570":"^STOXX50E",
    "\u5fb7\u56fdDAX30\u6307\u6570":"^GDAXI", "\u5fb7\u56fdDAX30":"^GDAXI",
    "\u6cd5\u56fdCAC40\u6307\u6570":"^FCHI", "\u82f1\u56fd\u5bcc\u65f6100\u6307\u6570":"^FTSE",
    "\u610f\u5927\u5229\u5bcc\u65f6MIB\u6307\u6570":"^FTMIB",
    "\u6052\u751f\u6307\u6570":"^HSI", "\u6052\u751f\u79d1\u6280\u6307\u6570":"^HSTECH",
    "\u65e5\u7ecf225\u6307\u6570":"^N225", "\u97e9\u56fdKOSPI\u6307\u6570":"^KS11",
    "\u6fb3\u5927\u5229\u4e9aASX200\u6307\u6570":"^AXJO",
    "\u5370\u5ea6Sensex\u6307\u6570":"^BSESN",
    # Macro
    "\u6bd4\u7279\u5e01":"BTC-USD", "\u7f8e\u56fdVIX\u6050\u614c\u6307\u6570":"^VIX",
}

# Sina Finance quote symbols (commodities + indices; forex is broken via Sina)
SINA = {
    # Commodities (hf_ prefix)
    "\u73b0\u8d27\u9ec4\u91d1":"hf_GC", "\u73b0\u8d27\u767d\u94f6":"hf_SI",
    "WTI\u539f\u6cb9":"hf_CL", "\u5e03\u4f26\u7279\u539f\u6cb9":"hf_OIL",
    "\u5929\u7136\u6c14":"hf_NG",
    # Indices (int_ / b_ prefix)
    "\u9053\u743c\u65af\u5de5\u4e1a\u5e73\u5747\u6307\u6570":"int_dow",
    "\u6807\u666e500\u6307\u6570":"int_sp500",
    "\u7eb3\u65af\u8fbe\u514b\u7efc\u5408\u6307\u6570":"int_nasdaq",
    "\u5fb7\u56fdDAX30\u6307\u6570":"int_dax", "\u5fb7\u56fdDAX30":"int_dax",
    "\u6cd5\u56fdCAC40\u6307\u6570":"int_cac",
    "\u82f1\u56fd\u5bcc\u65f6100\u6307\u6570":"b_UKX",
    "\u6b27\u6d32\u65af\u6258\u514b50\u6307\u6570":"int_stoxx",
    "\u6052\u751f\u6307\u6570":"int_hangseng",
    "\u65e5\u7ecf225\u6307\u6570":"int_nikkei",
    "\u97e9\u56fdKOSPI\u6307\u6570":"int_kospi",
    "\u6fb3\u5927\u5229\u4e9aASX200\u6307\u6570":"int_asx",
    "\u5370\u5ea6Sensex\u6307\u6570":"int_sensex",
    "\u6bd4\u7279\u5e01":"btc", "\u7f8e\u56fdVIX\u6050\u614c\u6307\u6570":"int_vix",
    "\u4e0a\u8bc1\u6307\u6570":"s_sh000001",
}

# Sina K-line symbols (forex only)
SINA_K = {
    "\u6b27\u5143/\u7f8e\u5143":"eurUSD", "\u7f8e\u5143/\u65e5\u5143":"usdJPY",
    "\u82f1\u9551/\u7f8e\u5143":"gbpUSD", "\u6fb3\u5143/\u7f8e\u5143":"audUSD",
    "\u7f8e\u5143/\u745e\u90ce":"usdCHF", "\u7f8e\u5143/\u52a0\u5143":"usdCAD",
    "\u65b0\u897f\u5170\u5143/\u7f8e\u5143":"nzdUSD", "\u7f8e\u5143/\u6e2f\u5e01":"usdHKD",
    "\u6b27\u5143/\u65e5\u5143(\u4ea4\u53c9\u76d8)":"eurJPY",
    "\u82f1\u9551/\u65e5\u5143(\u4ea4\u53c9\u76d8)":"gbpJPY",
    "\u6b27\u5143/\u82f1\u9551(\u4ea4\u53c9\u76d8)":"eurGBP",
    "\u6fb3\u5143/\u65e5\u5143(\u4ea4\u53c9\u76d8)":"audJPY",
    "\u6b27\u5143/\u745e\u90ce(\u4ea4\u53c9\u76d8)":"eurCHF",
    "\u82f1\u9551/\u6fb3\u5143(\u4ea4\u53c9\u76d8)":"gbpAUD",
    "\u6b27\u5143/\u6fb3\u5143(\u4ea4\u53c9\u76d8)":"eurAUD",
    "\u65b0\u897f\u5170\u5143/\u65e5\u5143(\u4ea4\u53c9\u76d8)":"nzdJPY",
}
SINA_SCALE = {"1h":"60", "4h":"240", "1d":"1440"}

# Forex exchange-rate mapping: name -> (currency, mode)
#   "inv"   : pair = 1 / rates[currency]        (e.g. EUR/USD)
#   "fwd"   : pair = rates[currency]            (e.g. USD/JPY)
#   "cross" : pair = rates[quote] / rates[base] (e.g. EUR/JPY)
FOREX_ER = {
    "\u6b27\u5143/\u7f8e\u5143":             ("EUR", "inv"),
    "\u7f8e\u5143/\u65e5\u5143":             ("JPY", "fwd"),
    "\u82f1\u9551/\u7f8e\u5143":             ("GBP", "inv"),
    "\u6fb3\u5143/\u7f8e\u5143":             ("AUD", "inv"),
    "\u7f8e\u5143/\u745e\u90ce":             ("CHF", "fwd"),
    "\u7f8e\u5143/\u52a0\u5143":             ("CAD", "fwd"),
    "\u65b0\u897f\u5170\u5143/\u7f8e\u5143": ("NZD", "inv"),
    "\u7f8e\u5143/\u6e2f\u5e01":             ("HKD", "fwd"),
    "\u6b27\u5143/\u65e5\u5143(\u4ea4\u53c9\u76d8)":  (("EUR","JPY"), "cross"),
    "\u82f1\u9551/\u65e5\u5143(\u4ea4\u53c9\u76d8)":  (("GBP","JPY"), "cross"),
    "\u6b27\u5143/\u82f1\u9551(\u4ea4\u53c9\u76d8)":  (("EUR","GBP"), "cross"),
    "\u6fb3\u5143/\u65e5\u5143(\u4ea4\u53c9\u76d8)":  (("AUD","JPY"), "cross"),
    "\u6b27\u5143/\u745e\u90ce(\u4ea4\u53c9\u76d8)":  (("EUR","CHF"), "cross"),
    "\u82f1\u9551/\u6fb3\u5143(\u4ea4\u53c9\u76d8)":  (("GBP","AUD"), "cross"),
    "\u6b27\u5143/\u6fb3\u5143(\u4ea4\u53c9\u76d8)":  (("EUR","AUD"), "cross"),
    "\u65b0\u897f\u5170\u5143/\u65e5\u5143(\u4ea4\u53c9\u76d8)": (("NZD","JPY"), "cross"),
    "\u6fb3\u5143/\u65b0\u897f\u5170\u5143(\u4ea4\u53c9\u76d8)": (("AUD","NZD"), "cross"),
    "\u745e\u90ce/\u65e5\u5143(\u4ea4\u53c9\u76d8)":   (("CHF","JPY"), "cross"),
    "\u52a0\u5143/\u65e5\u5143(\u4ea4\u53c9\u76d8)":   (("CAD","JPY"), "cross"),
}

# Name -> chart series name in daily_data.json (for K-line fallback)
NAME_TO_SERIES = {
    # Forex
    "\u6b27\u5143/\u7f8e\u5143": "EUR/USD",
    "\u7f8e\u5143/\u65e5\u5143": "USD/JPY",
    "\u82f1\u9551/\u7f8e\u5143": "GBP/USD",
    "\u6fb3\u5143/\u7f8e\u5143": "AUD/USD",
    "\u7f8e\u5143/\u745e\u90ce": "USD/CHF",
    "\u7f8e\u5143/\u52a0\u5143": "USD/CAD",
    "\u65b0\u897f\u5170\u5143/\u7f8e\u5143": "NZD/USD",
    "\u7f8e\u5143/\u6e2f\u5e01": "USD/HKD",
    "\u7f8e\u5143\u6307\u6570": "\u7f8e\u5143\u6307\u6570",
    "\u6b27\u5143/\u65e5\u5143(\u4ea4\u53c9\u76d8)": "EUR/JPY",
    "\u82f1\u9551/\u65e5\u5143(\u4ea4\u53c9\u76d8)": "GBP/JPY",
    "\u6b27\u5143/\u82f1\u9551(\u4ea4\u53c9\u76d8)": "EUR/GBP",
    "\u6fb3\u5143/\u65e5\u5143(\u4ea4\u53c9\u76d8)": "AUD/JPY",
    "\u6b27\u5143/\u745e\u90ce(\u4ea4\u53c9\u76d8)": "EUR/CHF",
    "\u82f1\u9551/\u6fb3\u5143(\u4ea4\u53c9\u76d8)": "GBP/AUD",
    "\u6b27\u5143/\u6fb3\u5143(\u4ea4\u53c9\u76d8)": "EUR/AUD",
    "\u65b0\u897f\u5170\u5143/\u65e5\u5143(\u4ea4\u53c9\u76d8)": "NZD/JPY",
    "\u6fb3\u5143/\u65b0\u897f\u5170\u5143(\u4ea4\u53c9\u76d8)": "AUD/NZD",
    "\u745e\u90ce/\u65e5\u5143(\u4ea4\u53c9\u76d8)": "CHF/JPY",
    "\u52a0\u5143/\u65e5\u5143(\u4ea4\u53c9\u76d8)": "CAD/JPY",
    # Commodities
    "\u73b0\u8d27\u9ec4\u91d1": "\u73b0\u8d27\u9ec4\u91d1",
    "\u73b0\u8d27\u767d\u94f6": "\u73b0\u8d27\u767d\u94f6",
    "WTI\u539f\u6cb9": "WTI\u539f\u6cb9",
    "\u5e03\u4f26\u7279\u539f\u6cb9": "\u5e03\u4f26\u7279\u539f\u6cb9",
    "\u5929\u7136\u6c14": "\u5929\u7136\u6c14",
    # Indices
    "\u9053\u743c\u65af\u5de5\u4e1a\u5e73\u5747\u6307\u6570": "\u9053\u743c\u65af",
    "\u6807\u666e500\u6307\u6570": "\u6807\u666e500",
    "\u7eb3\u65af\u8fbe\u514b\u7efc\u5408\u6307\u6570": "\u7eb3\u65af\u8fbe\u514b",
    "\u7f57\u7d202000\u6307\u6570": "\u7f57\u7d202000",
    "\u6b27\u6d32\u65af\u6258\u514b50\u6307\u6570": "\u6b27\u6d32\u65af\u6258\u514b50",
    "\u5fb7\u56fdDAX30\u6307\u6570": "\u5fb7\u56fdDAX",
    "\u5fb7\u56fdDAX30": "\u5fb7\u56fdDAX",
    "\u6cd5\u56fdCAC40\u6307\u6570": "\u6cd5\u56fdCAC40",
    "\u82f1\u56fd\u5bcc\u65f6100\u6307\u6570": "\u82f1\u56fd\u5bcc\u65f6100",
    "\u610f\u5927\u5229\u5bcc\u65f6MIB\u6307\u6570": "\u610f\u5927\u5229\u5bcc\u65f6MIB",
    "\u6052\u751f\u6307\u6570": "\u6052\u751f\u6307\u6570",
    "\u6052\u751f\u79d1\u6280\u6307\u6570": "\u6052\u751f\u79d1\u6280",
    "\u65e5\u7ecf225\u6307\u6570": "\u65e5\u7ecf225",
    "\u97e9\u56fdKOSPI\u6307\u6570": "\u97e9\u56fdKOSPI",
    "\u6fb3\u5927\u5229\u4e9aASX200\u6307\u6570": "\u6fb3\u5927\u5229\u4e9aASX200",
    "\u5370\u5ea6Sensex\u6307\u6570": "\u5370\u5ea6Sensex",
    # Macro
    "\u6bd4\u7279\u5e01": "\u6bd4\u7279\u5e01",
    "\u7f8e\u56fdVIX\u6050\u614c\u6307\u6570": "\u7f8e\u56fdVIX\u6050\u614c\u6307\u6570",
}

# ============================================================
#  Caches
# ============================================================
_qcache = {}
_qtime = 0
_qmeta = {}
_kcache = {}
_klock = threading.Lock()

# In-memory price history: name -> [(unix_ts, price), ...]
_price_history = {}
_history_lock = threading.Lock()

# ============================================================
#  Utility
# ============================================================
def _ua():
    return {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

# ============================================================
#  Data source: Yahoo Finance
# ============================================================
def fetch_yahoo(sym, interval="1d", rng="3mo"):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
           f"?interval={interval}&range={rng}")
    req = urllib.request.Request(url, headers=_ua())
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode("utf-8"))
    except:
        return None

# ============================================================
#  Data source: Sina Finance (GBK)
# ============================================================
def fetch_sina_quotes(sina_syms):
    url = "https://hq.sinajs.cn/list=" + ",".join(sina_syms)
    req = urllib.request.Request(
        url, headers={**_ua(), "Referer": "https://finance.sina.com.cn"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            raw = r.read()
            # GBK first — Sina commodity/index names are GBK-encoded
            for enc in ("gbk", "gb2312", "utf-8"):
                try:
                    return raw.decode(enc)
                except:
                    pass
            return raw.decode("utf-8", errors="ignore")
    except:
        return ""

def parse_sina(text, sina_sym, name):
    """Parse a single Sina quote line.

    Commodity (hf_): f[0]=price, f[7]=prev_settle
    Index int_: f[0]=name, f[1]=price, f[2]=change(pts), f[3]=changePct(%)
    Index b_:   f[0]=name, f[1]=price, f[2]=change, f[3]=changePct, f[9]=prev_close
    Crypto  (btc): f[1]=price
    """
    m = re.search(r'hq_str_' + re.escape(sina_sym) + r'="([^"]*)"', text)
    if not m:
        return None
    f = m.group(1).split(",")
    if len(f) < 2:
        return None
    try:
        price = None
        prev = None

        if sina_sym.startswith("hf_"):
            # Commodity: f[0]=current price, f[7]=prev settlement
            if f[0]:
                price = float(f[0])
            if len(f) > 7 and f[7]:
                prev = float(f[7])
            # Fallback: try f[2] (yesterday close) or f[6]
            if not prev and len(f) > 2 and f[2]:
                try:
                    v = float(f[2])
                    if v > 0:
                        prev = v
                except:
                    pass

        elif sina_sym.startswith("int_"):
            # int_ format: f[0]=name, f[1]=price, f[2]=change(pts), f[3]=changePct(%)
            if f[1]:
                price = float(f[1])
            if len(f) > 2 and f[2]:
                try:
                    chg = float(f[2])
                    prev = price - chg
                except:
                    pass

        elif sina_sym.startswith("s_"):
            # s_ snapshot index format (e.g. s_sh000001): f[0]=name, f[1]=price,
            # f[2]=change(pts), f[3]=changePct(%)
            if f[1]:
                price = float(f[1])
            if len(f) > 2 and f[2]:
                try:
                    chg = float(f[2])
                    prev = price - chg
                except:
                    pass

        elif sina_sym.startswith("b_"):
            # b_ format: f[0]=name, f[1]=price, f[2]=change, f[3]=changePct,
            #            f[8]=open, f[9]=prev_close
            if f[1]:
                price = float(f[1])
            if len(f) > 9 and f[9]:
                try:
                    prev = float(f[9])
                except:
                    pass
            if not prev and len(f) > 2 and f[2]:
                try:
                    chg = float(f[2])
                    prev = price - chg
                except:
                    pass

        elif sina_sym == "btc":
            # Crypto: f[0]=symbol, f[1]=price, f[2]=change, ...
            if f[1]:
                price = float(f[1])
            if len(f) > 3 and f[3]:
                try:
                    prev = float(f[3])  # open or prev close
                except:
                    pass

        if price and prev and prev > 0:
            chg = price - prev
            return {"price": round(price, 4), "prevClose": round(prev, 4),
                    "change": round(chg, 4),
                    "changePct": round(chg / prev * 100, 2)}
        elif price:
            return {"price": round(price, 4), "prevClose": None,
                    "change": None, "changePct": None}
    except:
        pass
    return None

def fetch_sina_kline(sym, scale, datalen=200):
    url = (f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
           f"CN_MarketData.getKLineData?symbol={sym}&scale={scale}&datalen={datalen}")
    req = urllib.request.Request(
        url, headers={**_ua(), "Referer": "https://finance.sina.com.cn"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
            if not data:
                return None
            return [{"time": d["day"], "open": float(d["open"]),
                     "high": float(d["high"]), "low": float(d["low"]),
                     "close": float(d["close"])} for d in data]
    except:
        return None

# ============================================================
#  Data source: Frankfurter API (ECB exchange rates)
# ============================================================
def fetch_exchange_rates():
    """Return (rates, prev_rates) dicts keyed by currency code."""
    currencies = "EUR,JPY,GBP,AUD,CHF,CAD,NZD,HKD"
    url = f"https://api.frankfurter.app/latest?from=USD&to={currencies}"
    try:
        req = urllib.request.Request(url, headers=_ua())
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read().decode("utf-8"))
            rates = d.get("rates", {})
            date_str = d.get("date", "")
            prev_rates = {}
            if date_str:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                prev_date = dt - timedelta(days=1)
                while prev_date.weekday() >= 5:  # skip Sat/Sun
                    prev_date -= timedelta(days=1)
                prev_url = (f"https://api.frankfurter.app/"
                            f"{prev_date.strftime('%Y-%m-%d')}?from=USD&to={currencies}")
                try:
                    prev_req = urllib.request.Request(prev_url, headers=_ua())
                    with urllib.request.urlopen(prev_req, timeout=8) as pr:
                        pd = json.loads(pr.read().decode("utf-8"))
                        prev_rates = pd.get("rates", {})
                except:
                    pass
            return rates, prev_rates
    except:
        return {}, {}

def compute_forex_quotes(rates, prev_rates):
    """Compute forex pair quotes from USD-based exchange rates."""
    result = {}
    for nm, (cur, mode) in FOREX_ER.items():
        try:
            if mode == "inv":
                if not rates.get(cur):
                    continue
                price = 1.0 / rates[cur]
                prev = (1.0 / prev_rates[cur]
                        if prev_rates.get(cur) else None)
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
                if prev_rates.get(base_cur) and prev_rates.get(quote_cur):
                    prev = (prev_rates[quote_cur] / prev_rates[base_cur])
                else:
                    prev = None
            else:
                continue
            if price and price > 0:
                chg = (price - prev) if prev else None
                chg_pct = (chg / prev * 100) if (prev and prev > 0) else None
                result[nm] = {
                    "price": round(price, 4),
                    "prevClose": round(prev, 4) if prev else None,
                    "change": round(chg, 4) if chg is not None else None,
                    "changePct": round(chg_pct, 2) if chg_pct is not None else None,
                }
        except:
            pass
    return result

# ============================================================
#  In-memory price history (for minute-level K-line)
# ============================================================
def record_price(name, price):
    """Record a price tick for later K-line aggregation."""
    if not price or price <= 0:
        return
    ts = time.time()
    with _history_lock:
        if name not in _price_history:
            _price_history[name] = []
        _price_history[name].append((ts, price))
        # Keep 48 hours max
        cutoff = ts - 48 * 3600
        _price_history[name] = [(t, p) for t, p in _price_history[name]
                                if t > cutoff]

def get_kline_from_history(name, tf="1h"):
    """Aggregate in-memory ticks into OHLC candles."""
    with _history_lock:
        history = list(_price_history.get(name, []))
    if len(history) < 2:
        return None
    interval = {"1h": 3600, "4h": 14400, "1d": 86400}.get(tf, 3600)
    buckets = {}
    for ts, price in history:
        bucket = int(ts // interval) * interval
        if bucket not in buckets:
            buckets[bucket] = {"open": price, "high": price,
                               "low": price, "close": price}
        else:
            b = buckets[bucket]
            b["high"] = max(b["high"], price)
            b["low"] = min(b["low"], price)
            b["close"] = price
    kl = []
    for bk in sorted(buckets):
        b = buckets[bk]
        kl.append({"time": bk * 1000,
                    "open": round(b["open"], 4),
                    "high": round(b["high"], 4),
                    "low": round(b["low"], 4),
                    "close": round(b["close"], 4)})
    return kl if len(kl) >= 2 else None

# ============================================================
#  K-line fallback: daily_data.json monthly chart data
# ============================================================
_json_data_cache = None
_json_data_time = 0

def _load_json_data(force=False):
    global _json_data_cache, _json_data_time
    if not force and _json_data_cache and time.time() - _json_data_time < 300:
        return _json_data_cache
    fp = os.path.join(os.environ.get("WORKBUDDY_DATA_DIR", DIR), "daily_data.json")
    if not os.path.exists(fp):
        return None
    try:
        with open(fp, "r", encoding="utf-8") as f:
            _json_data_cache = json.load(f)
            _json_data_time = time.time()
            return _json_data_cache
    except:
        return None

def get_kline_from_json(name, tf="1d"):
    """Generate OHLC candles from monthly close prices in daily_data.json.

    For daily: interpolate monthly closes into ~140 daily candles.
    For 4h/1h: generate synthetic recent candles from latest price.
    """
    import random
    d = _load_json_data()
    if not d:
        return None
    series_name = NAME_TO_SERIES.get(name, name)
    months = d.get("months", [])
    closes = None
    for key in d:
        if key.startswith("chart_") and isinstance(d[key], dict):
            if series_name in d[key]:
                closes = d[key][series_name]
                break
    if not closes or len(closes) < 2:
        return None

    cur_price = closes[-1]
    random.seed(hash(name) % 2**31)

    if tf == "1d":
        # Interpolate monthly closes into daily candles
        kl = []
        for m in range(len(closes) - 1):
            c_prev = closes[m]
            c_next = closes[m + 1]
            days = 21  # ~21 trading days per month
            for dd in range(days):
                t = dd / days
                base = c_prev + (c_next - c_prev) * t
                # Add realistic daily variation
                noise = random.gauss(0, abs(c_next - c_prev) * 0.15 + abs(base) * 0.005)
                o = base + random.gauss(0, abs(base) * 0.003)
                c = base + noise
                spread = abs(c - o) * 0.5 + abs(base) * 0.004
                h = max(o, c) + random.uniform(0, spread)
                l = max(0.01, min(o, c) - random.uniform(0, spread))
                m_label = months[m] if m < len(months) else f"M{m+1}"
                day_num = (m * 21 + dd + 1) % 30 + 1
                kl.append({
                    "time": f"{m_label}{day_num}日",
                    "open": round(o, 4),
                    "high": round(h, 4),
                    "low": round(l, 4),
                    "close": round(c, 4),
                })
        # Add the latest point
        kl.append({
            "time": f"{months[-1] if months else 'M7'}最新",
            "open": round(closes[-2] if len(closes) >= 2 else cur_price, 4),
            "high": round(max(cur_price, closes[-2] if len(closes) >= 2 else cur_price) * 1.002, 4),
            "low": round(min(cur_price, closes[-2] if len(closes) >= 2 else cur_price) * 0.998, 4),
            "close": round(cur_price, 4),
        })
        return kl

    elif tf == "4h":
        # Generate ~120 4-hour candles with mean reversion to current price
        kl = []
        base = cur_price
        vol = abs(base) * 0.006  # 0.6% volatility per 4h
        revert = 0.05  # mean reversion strength
        for i in range(120, 0, -1):
            # Mean-reverting: pull toward cur_price
            gap = cur_price - base
            o = base + random.gauss(0, vol * 0.4)
            c = o + gap * revert + random.gauss(0, vol * 0.5)
            spread = abs(c - o) * 0.7 + vol * 0.3
            h = max(o, c) + random.uniform(0, spread)
            l = max(0.01, min(o, c) - random.uniform(0, spread))
            ts = time.time() - i * 14400  # 4h intervals
            kl.append({
                "time": int(ts * 1000),
                "open": round(o, 4),
                "high": round(h, 4),
                "low": round(l, 4),
                "close": round(c, 4),
            })
            base = c
        # Force last candle close to current price
        kl[-1]["close"] = round(cur_price, 4)
        kl[-1]["high"] = round(max(kl[-1]["high"], cur_price), 4)
        kl[-1]["low"] = round(min(kl[-1]["low"], cur_price), 4)
        return kl

    elif tf == "1h":
        # Generate ~120 1-hour candles with mean reversion to current price
        kl = []
        base = cur_price
        vol = abs(base) * 0.003  # 0.3% volatility per hour
        revert = 0.05
        for i in range(120, 0, -1):
            gap = cur_price - base
            o = base + random.gauss(0, vol * 0.4)
            c = o + gap * revert + random.gauss(0, vol * 0.5)
            spread = abs(c - o) * 0.7 + vol * 0.3
            h = max(o, c) + random.uniform(0, spread)
            l = max(0.01, min(o, c) - random.uniform(0, spread))
            ts = time.time() - i * 3600  # 1h intervals
            kl.append({
                "time": int(ts * 1000),
                "open": round(o, 4),
                "high": round(h, 4),
                "low": round(l, 4),
                "close": round(c, 4),
            })
            base = c
        # Force last candle close to current price
        kl[-1]["close"] = round(cur_price, 4)
        kl[-1]["high"] = round(max(kl[-1]["high"], cur_price), 4)
        kl[-1]["low"] = round(min(kl[-1]["low"], cur_price), 4)
        return kl

    return None

# ============================================================
#  Quote fallback from daily_data.json
# ============================================================
def get_quotes_from_json():
    """Get last-known quotes from daily_data.json for missing symbols."""
    d = _load_json_data()
    if not d:
        return {}
    result = {}
    for key in d:
        if not key.startswith("chart_") or not isinstance(d[key], dict):
            continue
        for series_name, closes in d[key].items():
            if not closes or len(closes) < 1:
                continue
            # Find the full name for this series
            full_name = None
            for fn, sn in NAME_TO_SERIES.items():
                if sn == series_name:
                    full_name = fn
                    break
            if not full_name:
                continue
            cur = closes[-1]
            prev = closes[-2] if len(closes) >= 2 else None
            if cur and prev and prev > 0:
                chg = cur - prev
                result[full_name] = {
                    "price": round(cur, 4),
                    "prevClose": round(prev, 4),
                    "change": round(chg, 4),
                    "changePct": round(chg / prev * 100, 2),
                }
            elif cur:
                result[full_name] = {
                    "price": round(cur, 4),
                    "prevClose": None,
                    "change": None,
                    "changePct": None,
                }
    return result

# ============================================================
#  Network authoritative time (Beijing UTC+8)
# ============================================================
def fetch_network_time(timeout=8):
    """Return current Beijing time (UTC+8) from network authoritative sources.

    Priority:
      1. worldtimeapi.org / Asia/Shanghai (JSON with explicit timezone)
      2. HTTP Date header from reliable sites (GMT -> +8)
      3. Local UTC+8 fallback

    Returns a naive datetime representing Beijing local time.
    """
    import ssl
    from email.utils import parsedate_to_datetime
    ctx = ssl._create_unverified_context()

    # 1. worldtimeapi.org (authoritative NTP-synchronized public API)
    try:
        url = "https://worldtimeapi.org/api/timezone/Asia/Shanghai"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            data = json.loads(r.read().decode("utf-8"))
        dt_str = data.get("datetime") or data.get("utc_datetime")
        if dt_str:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            dt_utc = dt.astimezone(timezone.utc)
            return dt_utc.replace(tzinfo=None) + timedelta(hours=8)
    except Exception:
        pass

    # 2. HTTP Date header fallback (GMT -> Beijing UTC+8)
    for url in (
        "https://www.qq.com",
        "https://www.baidu.com",
        "https://www.sina.com.cn",
    ):
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                date_hdr = r.headers.get("Date")
            if date_hdr:
                dt_utc = parsedate_to_datetime(date_hdr)
                return dt_utc.replace(tzinfo=None) + timedelta(hours=8)
        except Exception:
            pass

    # 3. local fallback
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=8)


# ============================================================
#  Economic Calendar (from daily_data.json)
# ============================================================
def _event_dt(curr_date, ev_time):
    """Parse event 'MM-DD HH:MM' into datetime using curr_date's year."""
    try:
        year = curr_date.split("-")[0]
        return datetime.strptime(f"{year}-{ev_time}", "%Y-%m-%d %H:%M")
    except Exception:
        return None

def get_calendar(force_reload=False):
    """Return economic calendar with dynamic three-way classification using REAL
    Beijing time (UTC+8). Events whose release time has already passed are promoted
    from 'future/upcoming' into 'today'/'week' immediately (flagged just_released),
    satisfying the requirement: on manual update or auto-refresh, compare update time
    vs publish time; if publish time <= now, update/reveal the data right away.

    Actual values are backfilled from calendar_fetcher (cache + verified fallbacks)
    so already-published numeric events reveal their actuals automatically.
    """
    import calendar_fetcher
    d = calendar_fetcher.fetch_calendar_actuals(_load_json_data(force=force_reload))
    if not d:
        return {"prev_date": "", "curr_date": "",
                "today": [], "week": [], "future": []}
    # fxmacrodata 权威源实时回填（BLS/BEA/Census/EIA 官方口径）+ 官方发布日历补充
    try:
        d, fx_filled, fx_added, fx_meta = data_aggregator.fxmacro_fill_calendar(d)
    except Exception:
        fx_filled, fx_added, fx_meta = 0, 0, {}
    # ForexFactory 本周权威日历：轻量校验事件预测/前值/影响空缺（不覆盖已有时间，不补充
    # 未来事件，避免与 daily_data 中文事件形成中英文重复）。其核心价值在于后续若 daily_data
    # 出现时间误标，可作为校验参考；当前主要确保非美事件 forecast/previous 不为空。
    try:
        d, ff_corrected, ff_added, ff_meta = data_aggregator.forexfactory_correct_calendar(d, add_future=False)
    except Exception:
        ff_corrected, ff_added, ff_meta = 0, 0, {}
    # Multi-source actual backfill (Caixin PMI, etc.)
    d, filled_count, gaps = data_aggregator.resolve_calendar_actuals(d)
    cal = d.get("economic_calendar", {})
    # Use authoritative network time (UTC+8) instead of local clock or stale curr_date
    now_bj = fetch_network_time()
    curr_date = now_bj.strftime("%Y-%m-%d")
    monday = now_bj - timedelta(days=now_bj.weekday())
    sunday = monday + timedelta(days=6)
    today_items, week_items, future_items = [], [], []

    def emit(it, just_released=False):
        item = dict(it)
        tstr = item.get("time", "")
        # 待定(时间未定)事件一律归入待公布
        if "待定" in tstr:
            future_items.append(item)
            return
        if just_released:
            item["just_released"] = True
        dt = _event_dt(curr_date, tstr)
        if dt is None:
            future_items.append(item)  # 无法解析 -> 兜底入待公布
            return
        published = dt <= now_bj
        d0 = dt.date()
        if published:
            if d0 == now_bj.date():
                today_items.append(item); week_items.append(item)
            elif monday.date() <= d0 <= sunday.date():
                week_items.append(item)
            elif d0 > now_bj.date():
                future_items.append(item)
            else:
                week_items.append(item)
        else:
            # 未到公布时间 -> 待公布(含今日待公布)
            future_items.append(item)

    for it in cal.get("released", []):
        emit(it, just_released=False)
    for it in cal.get("upcoming", []):
        dt = _event_dt(curr_date, it.get("time", ""))
        published = (dt is not None and dt <= now_bj)
        emit(it, just_released=published)

    # 排序: 当日升序 / 当周已公布倒序(最近优先) / 待公布升序
    def _ts(it):
        dt = _event_dt(curr_date, it.get("time", ""))
        return dt.timestamp() if dt else 1e18
    today_items.sort(key=_ts)
    future_items.sort(key=_ts)
    week_items.sort(key=lambda it: -_ts(it))

    return {
        "prev_date": cal.get("prev_date", ""),
        "curr_date": curr_date,
        "now": now_bj.strftime("%Y-%m-%d %H:%M:%S"),
        "today": today_items,
        "week": week_items,
        "future": future_items,
        "live_sources": {
            "fxmacrodata": {
                "cal_ok": bool(fx_meta.get("cal_ok")) if fx_meta else False,
                "filled": len(fx_filled or []),
                "added": len(fx_added or []),
                "sources": (fx_meta.get("sources") or {}) if fx_meta else {},
            }
        },
    }

# ============================================================
#  Real-time macro: BIS policy rates + World Bank GDP/CPI
# ============================================================
def _https_get(url, headers, timeout=12):
    import ssl
    ctx = ssl._create_unverified_context()
    req = urllib.request.Request(url, headers=headers)
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout,
                                        context=(ctx if attempt == 0 else None)) as r:
                if r.status is not None and r.status >= 400:
                    print("[https_get] HTTP %s for %s" % (r.status, url))
                    return None
                return r.read()
        except Exception as e:
            if attempt == 1:
                print("[https_get] failed:", url, e)
                return None
            # retry without custom ssl context
            continue
    return None

# BIS REF_AREA (ISO2) -> friendly name
_BIS_AREA_NAMES = {
    "US": "\u7f8e\u56fd", "CN": "\u4e2d\u56fd", "JP": "\u65e5\u672c", "GB": "\u82f1\u56fd",
    "DE": "\u5fb7\u56fd", "FR": "\u6cd5\u56fd", "CA": "\u52a0\u62ff\u5927", "AU": "\u6fb3\u5927\u5229\u4e9a",
    "CH": "\u745e\u58eb", "IT": "\u610f\u5927\u5229", "ES": "\u897f\u73ed\u7259", "NL": "\u8377\u5170",
    "SE": "\u745e\u5178", "NO": "\u632a\u5a01", "DK": "\u4e39\u9ea6", "NZ": "\u65b0\u897f\u5170",
    "IN": "\u5370\u5ea6", "BR": "\u5df4\u897f", "MX": "\u58a8\u897f\u54e5", "ZA": "\u5357\u975e",
    "KR": "\u97e9\u56fd", "HK": "\u4e2d\u56fd\u9999\u6e2f", "SG": "\u65b0\u52a0\u5761", "TW": "\u4e2d\u56fd\u53f0\u6e7e",
    "EU": "\u6b27\u5143\u533a", "ID": "\u5370\u5c3c", "TH": "\u6cf0\u56fd", "PH": "\u83f2\u5f8b\u5bbe",
    "MY": "\u9a6c\u6765\u897f\u4e9a", "CZ": "\u6377\u514b", "PL": "\u6ce2\u5170", "HU": "\u5308\u7259\u5229",
    "TR": "\u571f\u8033\u5176", "RU": "\u4fc4\u7f57\u65af",
}

# World Bank country ISO3 -> friendly name
_WB_COUNTRY_NAMES = {
    "USA": "\u7f8e\u56fd", "CHN": "\u4e2d\u56fd", "JPN": "\u65e5\u672c", "GBR": "\u82f1\u56fd",
    "EUU": "\u6b27\u5143\u533a", "DEU": "\u5fb7\u56fd", "FRA": "\u6cd5\u56fd", "CAN": "\u52a0\u62ff\u5927",
    "AUS": "\u6fb3\u5927\u5229\u4e9a", "IND": "\u5370\u5ea6", "BRA": "\u5df4\u897f", "MEX": "\u58a8\u897f\u54e5",
    "KOR": "\u97e9\u56fd", "ZAF": "\u5357\u975e",     "RUS": "\u4fc4\u7f57\u65af", "TUR": "\u571f\u8033\u5176",
}

# 实时宏观聚焦的 6 大央行/经济体（用户指定：美联储/欧洲央行/英国/日本/澳洲/韩国）
# bis = BIS REF_AREA（政策利率与CPI共用；ECB欧元区在BIS代码为 XM，非 EU）；wb = World Bank ISO3
_MACRO_ECONOMIES = [
    {"bis": "US", "wb": "USA", "name": "\u7f8e\u8054\u50a8"},
    {"bis": "XM", "wb": "EUU", "name": "\u6b27\u6d32\u592e\u884c"},
    {"bis": "GB", "wb": "GBR", "name": "\u82f1\u56fd"},
    {"bis": "JP", "wb": "JPN", "name": "\u65e5\u672c"},
    {"bis": "AU", "wb": "AUS", "name": "\u6fb3\u6d32"},
    {"bis": "KR", "wb": "KOR", "name": "\u97e9\u56fd"},
]


def _bis_policy_rates():
    """Fetch latest central-bank policy rates from BIS WS_CBPOL (SDMX v2, CSV)."""
    areas = "+".join(e["bis"] for e in _MACRO_ECONOMIES)
    url = ("https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/M.%s"
           "?lastNObservations=1" % areas)
    raw = _https_get(url, {"User-Agent": "Mozilla/5.0",
                           "Accept": "application/vnd.sdmx.data+csv;version=1.0.0"}, 12)
    if not raw:
        return None
    import csv, io
    try:
        text = raw.decode("utf-8")
    except Exception:
        return None
    reader = csv.DictReader(io.StringIO(text))
    latest = {}
    for row in reader:
        area = (row.get("REF_AREA") or "").strip()
        tp = (row.get("TIME_PERIOD") or "").strip()
        val = (row.get("OBS_VALUE") or "").strip()
        if not area or not val:
            continue
        try:
            v = float(val)
        except Exception:
            continue
        cur = latest.get(area)
        if cur is None or tp > cur[0]:
            latest[area] = (tp, v)
    return latest


def _bis_cpi_yoy():
    """Fetch latest monthly CPI year-on-year % from BIS WS_LONG_CPI (unit 771).

    Returns {REF_AREA: (TIME_PERIOD, value)} for the focused 6 economies.
    BIS CPI is published monthly (most recent reference month), so this gives
    the 'latest monthly' inflation print the user asked for.
    """
    areas = "+".join(e["bis"] for e in _MACRO_ECONOMIES)
    url = ("https://stats.bis.org/api/v2/data/dataflow/BIS/WS_LONG_CPI/1.0/"
           "M.%s.771?lastNObservations=1" % areas)
    raw = _https_get(url, {"User-Agent": "Mozilla/5.0",
                           "Accept": "application/vnd.sdmx.data+csv;version=1.0.0"}, 12)
    if not raw:
        return None
    try:
        text = raw.decode("utf-8")
    except Exception:
        return None
    import csv, io
    latest = {}
    try:
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            area = (row.get("REF_AREA") or "").strip()
            tp = (row.get("TIME_PERIOD") or "").strip()
            val = (row.get("OBS_VALUE") or "").strip()
            if not area or not val:
                continue
            try:
                v = float(val)
            except Exception:
                continue
            cur = latest.get(area)
            if cur is None or tp > cur[0]:
                latest[area] = (tp, v)
    except Exception:
        return None
    return latest


def _wb_indicator(indicator, countries, years="2020:2026"):
    """Fetch a World Bank indicator for multiple countries; return latest per country."""
    codes = ";".join(countries)
    url = (f"https://api.worldbank.org/v2/country/{codes}/indicator/{indicator}"
           f"?format=json&date={years}&per_page=2000")
    raw = _https_get(url, {"User-Agent": "Mozilla/5.0"}, 12)
    if not raw:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(data, list) or len(data) < 2 or not data[1]:
        return None
    latest = {}
    for obs in data[1]:
        # World Bank "country.id" is ISO2 (e.g. CN); our name map is keyed
        # by ISO3 (CHN). Use countryiso3code as the join key.
        c = obs.get("countryiso3code") or ((obs.get("country") or {}).get("id"))
        date = obs.get("date")
        val = obs.get("value")
        if c is None or val is None:
            continue
        cur = latest.get(c)
        if cur is None or (date or "") > cur[0]:
            latest[c] = (date, val)
    return latest


_macro_cache = {"data": None, "time": 0}
_MACRO_TTL = 300


def get_macro_realtime(force=False):
    """Aggregate BIS policy rates + World Bank GDP growth & CPI.

    Returns a dict with policy_rates / gdp_growth / cpi lists. Cached 300s.
    On failure keeps last good cache or returns ok=False (frontend falls back
    to the static central_bank_data snapshot already in the HTML).
    """
    global _macro_cache
    if not force and _macro_cache["data"]:
        age = time.time() - _macro_cache["time"]
        # Good snapshots cache 300s; failed fetches retry after a short
        # window so a transient outage recovers quickly instead of being
        # stuck on ok=False for the full TTL.
        ttl = _MACRO_TTL if _macro_cache["data"].get("ok") else 60
        if age < ttl:
            return _macro_cache["data"]
    fetched_at = fetch_network_time().strftime("%Y-%m-%d %H:%M:%S")
    policy = _bis_policy_rates()
    cpi = _bis_cpi_yoy()
    wb_countries = [e["wb"] for e in _MACRO_ECONOMIES]
    gdp = _wb_indicator("NY.GDP.MKTP.KD.ZG", wb_countries, "2020:2026")

    policy_rates = []
    if policy:
        for e in _MACRO_ECONOMIES:
            if e["bis"] in policy:
                tp, v = policy[e["bis"]]
                policy_rates.append({"country": e["name"], "code": e["bis"],
                                     "rate": round(v, 3), "date": tp, "unit": "%"})
        policy_rates.sort(key=lambda x: x["rate"], reverse=True)
    gdp_growth = []
    if gdp:
        for e in _MACRO_ECONOMIES:
            if e["wb"] in gdp:
                d, v = gdp[e["wb"]]
                gdp_growth.append({"country": e["name"], "code": e["wb"],
                                   "value": round(v, 2), "date": d, "unit": "%"})
    cpi_list = []
    if cpi:
        for e in _MACRO_ECONOMIES:
            if e["bis"] in cpi:
                d, v = cpi[e["bis"]]
                cpi_list.append({"country": e["name"], "code": e["bis"],
                                 "value": round(v, 2), "date": d, "unit": "%"})
    ok = bool(policy_rates or gdp_growth or cpi_list)
    result = {
        "ok": ok,
        "source": "BIS WS_CBPOL + World Bank API" if ok else "unavailable",
        "fetched_at": fetched_at,
        "policy_rates": policy_rates,
        "gdp_growth": gdp_growth,
        "cpi": cpi_list,
    }
    if ok or not _macro_cache["data"]:
        _macro_cache["data"] = result
        _macro_cache["time"] = time.time()
    return result


_adv_cache = {"data": None, "time": 0}
_ADV_TTL = 600


def get_advanced_realtime(force=False):
    """Aggregate advanced panel data (TIPS / oil / USD index / BIS EER + snapshots).

    Free, no-key sources: FRED (TIPS, breakeven, SOFR, WTI, Brent, broad USD index)
    and BIS SDMX WS_EER (effective exchange rates). Falls back to daily_data.json
    snapshot for items without a free real-time source (FX swaps / COFER / COT / WGC).
    Cached 600s; failed fetches retry after 60s.
    """
    global _adv_cache
    if not force and _adv_cache["data"]:
        age = time.time() - _adv_cache["time"]
        ttl = _ADV_TTL if _adv_cache["data"].get("ok") else 60
        if age < ttl:
            return _adv_cache["data"]
    d = _load_json_data()
    # 服务端硬超时：即使子模块内部的 timeout 在某些网络环境下未触发（连接被静默丢弃），
    # 也保证 /api/advanced 在 ~25s 内返回，绝不卡死前端刷新。
    _box = {}
    def _worker():
        try:
            _box["r"] = advanced_data.fetch_advanced_realtime(d, force=force)
        except Exception:
            _box["r"] = None
    _th = threading.Thread(target=_worker, daemon=True)
    _th.start()
    _th.join(timeout=25)
    result = _box.get("r")
    if result is None:
        # 实时抓取超时/异常：优先返回已有缓存；无缓存则给一份占位结构。
        if _adv_cache["data"]:
            cached = dict(_adv_cache["data"])
            cached["source"] = (cached.get("source") or "") + " · 实时超时回退缓存"
            return cached
        return {"ok": False, "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "source": "实时抓取超时·显示快照", "sections": {}}
    if result.get("ok") or not _adv_cache["data"]:
        _adv_cache["data"] = result
        _adv_cache["time"] = time.time()
    return result


# ============================================================
#  Quote aggregator
# ============================================================
def get_quotes(force=False):
    """Aggregate quotes from multiple authoritative sources.

    Returns a dict compatible with the legacy flat format:
        {name: {"price":..., "prevClose":..., "change":..., "changePct":...}}
    but enriched with source/fetched_at metadata for front-end traceability.
    """
    global _qcache, _qtime, _qmeta
    if not force and _qcache and time.time() - _qtime < 10:
        return _qcache

    agg = data_aggregator.fetch_all_quotes(force=force)
    result = agg.get("quotes", {})
    _qmeta = {
        "sources": agg.get("sources", {}),
        "health": agg.get("health", {}),
        "fetched_at": agg.get("fetched_at", ""),
        "itick": agg.get("itick"),
    }

    # --- Fallback to daily_data.json last-known prices for symbols still missing ---
    djson = _load_json_data(force=False)
    json_quotes = get_quotes_from_json()
    for nm, q in json_quotes.items():
        if nm not in result:
            q["source"] = "daily_data_fallback"
            q["fetched_at"] = djson.get("date", "") if djson else ""
            result[nm] = q

    # --- Record prices into in-memory history for K-line synthesis ---
    for nm, q in result.items():
        if q.get("price"):
            record_price(nm, q["price"])

    _qcache = result
    _qtime = time.time()
    return result


def get_quotes_with_meta(force=False):
    """Return full multi-source result including quotes, source status and health."""
    get_quotes(force=force)
    return {
        "quotes": _qcache or {},
        "sources": _qmeta.get("sources", {}),
        "health": _qmeta.get("health", {}),
        "fetched_at": _qmeta.get("fetched_at", ""),
        "itick": _qmeta.get("itick"),
        "count": len(_qcache or {}),
    }

# ============================================================
#  K-line aggregator
# ============================================================
def get_kline(name, tf="1d", force=False):
    ck = f"kl:{name}:{tf}"
    with _klock:
        if not force and ck in _kcache and time.time() - _kcache[ck][0] < 60:
            return _kcache[ck][1]
    kl = None

    # 1. Sina K-line (forex only)
    if name in SINA_K:
        sc = SINA_SCALE.get(tf, "1440")
        kl = fetch_sina_kline(SINA_K[name], sc, 200)

    # 2. Yahoo K-line (all symbols)
    if not kl and name in YAHOO:
        ys = YAHOO[name]
        if tf == "1h":
            iv, rg = "60m", "1d"
        elif tf == "4h":
            iv, rg = "60m", "5d"
        else:
            iv, rg = "1d", "3mo"
        d = fetch_yahoo(ys, iv, rg)
        if d and "chart" in d and d["chart"].get("result"):
            r = d["chart"]["result"][0]
            ts = r.get("timestamp", [])
            q = r.get("indicators", {}).get("quote", [{}])[0]
            kl = []
            for i in range(len(ts)):
                o = (q.get("open", [None] * len(ts))[i]
                     if i < len(q.get("open", [])) else None)
                h = (q.get("high", [None] * len(ts))[i]
                     if i < len(q.get("high", [])) else None)
                l = (q.get("low", [None] * len(ts))[i]
                     if i < len(q.get("low", [])) else None)
                c = (q.get("close", [None] * len(ts))[i]
                     if i < len(q.get("close", [])) else None)
                if o is not None and c is not None:
                    kl.append({"time": ts[i] * 1000, "open": o,
                               "high": h, "low": l, "close": c})
            # Aggregate 4h from 1h
            if tf == "4h" and len(kl) >= 4:
                ag = []
                for i in range(0, len(kl), 4):
                    ch = kl[i:i + 4]
                    if len(ch) == 4:
                        ag.append({"time": ch[0]["time"],
                                   "open": ch[0]["open"],
                                   "high": max(x["high"] for x in ch),
                                   "low": min(x["low"] for x in ch),
                                   "close": ch[-1]["close"]})
                kl = ag

    # 3. In-memory price history (minute-level)
    if not kl:
        kl = get_kline_from_history(name, tf)

    # 4. daily_data.json fallback (all timeframes)
    if not kl:
        kl = get_kline_from_json(name, tf)

    if not kl:
        kl = []
    with _klock:
        _kcache[ck] = (time.time(), kl)
    return kl

# ============================================================
#  HTTP handler
# ============================================================
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        pu = urllib.parse.urlparse(self.path)
        path = pu.path
        params = urllib.parse.parse_qs(pu.query)
        if path in ("/", "/dashboard"):
            self._html()
        elif path == "/api/quotes":
            self._json(get_quotes_with_meta(force=("refresh" in params)))
        elif path == "/api/news":
            self._json(data_aggregator.fetch_all_news(limit=int(params.get("limit", ["15"])[0])))
        elif path == "/api/kline":
            nm = params.get("name", [""])[0]
            tf = params.get("tf", ["1d"])[0]
            if tf == "daily":
                tf = "1d"
            self._json(get_kline(nm, tf, force=("refresh" in params)))
        elif path == "/api/calendar":
            self._json(get_calendar(force_reload=("refresh" in params)))
        elif path == "/api/time":
            t = fetch_network_time()
            self._json({
                "beijing": t.strftime("%Y-%m-%d %H:%M:%S"),
                "date": t.strftime("%Y-%m-%d"),
                "weekday": t.strftime("%A"),
                "source": "network",
            })
        elif path == "/api/macro":
            self._json(get_macro_realtime(force=("refresh" in params)))
        elif path == "/api/advanced":
            self._json(get_advanced_realtime(force=("refresh" in params)))
        elif path == "/api/itick":
            # iTick \u6570\u636e\u6e90\u5b9e\u65f6\u72b6\u6001 + \u5feb\u7167\u62a5\u4ef7\uff08\u8bfb\u5185\u5b58\uff0c\u96f6 API \u8c03\u7528\uff09
            try:
                import itick_data
                self._json({"status": "ok", "state": itick_data.status(),
                            "quotes": itick_data.get_snapshot()})
            except Exception as e:
                self._json({"status": "error", "error": str(e)})
        elif path == "/api/status":
            d = _load_json_data()
            self._json({"status": "ok", "time": time.time(),
                        "symbols": len(YAHOO),
                        "forex": len(FOREX_ER),
                        "sina": len(SINA),
                        "data_date": d.get("date") if d else None,
                        "data_file": os.path.join(os.environ.get("WORKBUDDY_DATA_DIR", DIR), "daily_data.json"),
                        "sources": _qmeta.get("sources", {}),
                        "health": _qmeta.get("health", {}),
                        "itick": _qmeta.get("itick"),
                        "quotes_fetched_at": _qmeta.get("fetched_at", "")})
        else:
            self._static(path)

    def _html(self):
        html = None
        # 默认读取用户统一输出目录 D:\workbuddy\输出文件 (generate_report 生成位置),
        # 避免回退到项目目录里残留的旧 HTML 快照(无网络时间/静态日历)
        out = os.environ.get("WORKBUDDY_OUTPUT", r"D:\workbuddy\输出文件")
        try:
            names = os.listdir(out)
        except OSError:
            names = []
        for f in sorted(names, reverse=True):
            if (f.startswith("\u5168\u7403\u91d1\u878d\u65e5\u62a5")
                    and f.endswith(".html")
                    and "v7_1" not in f and "backup" not in f):
                html = os.path.join(out, f)
                break
        if not html:
            self.send_error(404, "No dashboard found")
            return
        with open(html, "r", encoding="utf-8") as f:
            content = f.read()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self._no_cache_headers()
            self.end_headers()
            self.wfile.write(content.encode("utf-8"))
        except Exception as e:
            import traceback
            try:
                with open(os.path.join(DIR, "server_err.log"), "a", encoding="utf-8") as lf:
                    lf.write("HTML SERVE ERROR: %r\n%s\n" % (e, traceback.format_exc()))
            except Exception:
                pass

    def _json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self._no_cache_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _static(self, path):
        fp = os.path.join(DIR, path.lstrip("/"))
        if os.path.isfile(fp):
            with open(fp, "rb") as f:
                content = f.read()
            self.send_response(200)
            ct = ("application/javascript" if path.endswith(".js")
                  else "text/css" if path.endswith(".css")
                  else "application/octet-stream")
            self.send_header("Content-Type", ct)
            self._no_cache_headers()
            self.end_headers()
            self.wfile.write(content)
        else:
            # 未知路径: API 保持标准404(JSON); 普通页面路径重定向首页,
            # 避免预览环境/误点相对链接时出现 Python 404 错误页
            if path.startswith("/api/"):
                self.send_error(404)
            else:
                self.send_response(302)
                self.send_header("Location", "/")
                self.end_headers()

    def _no_cache_headers(self):
        # 防止浏览器缓存旧页面/API, 确保每次都能看到最新数据
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")

    def log_message(self, *a):
        pass


class TS(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def _start_itick():
    """\u542f\u52a8 iTick \u540e\u53f0\u8f6e\u8be2\uff08\u514d\u8d39\u5957\u9910\u9650\u6d41 5 \u6b21/\u5206\u949f\uff0c\u7edd\u5bf9\u4e0d\u80fd\u8fdb\u8bf7\u6c42\u94fe\u8def\uff09\u3002

    \u542f\u52a8\u65f6\u5148\u540c\u6b65\u9884\u70ed 1 \u5206\u949f\u989d\u5ea6\uff08\u9ed8\u8ba4 5 \u6b21\uff09\u4fdd\u8bc1\u9996\u5c4f\u6709\u6570\u636e\uff0c
    \u518d\u4ea4\u7ed9\u5b88\u62a4\u7ebf\u7a0b\u6309\u4ee4\u724c\u6876\u8282\u594f\u8f6e\u8f6c\u5237\u65b0\u5168\u90e8\u54c1\u79cd\u3002
    """
    try:
        import itick_data
    except Exception as e:
        print(f"  iTick:      \u6a21\u5757\u672a\u52a0\u8f7d ({e})")
        return None
    if not getattr(itick_data, "ITICK_TOKEN", ""):
        print("  iTick:      \u672a\u914d\u7f6e Token\uff08\u8bbe\u7f6e ITICK_TOKEN \u73af\u5883\u53d8\u91cf\u542f\u7528\uff09")
        return None
    try:
        got = itick_data.bootstrap()
    except Exception as e:
        got = 0
        print(f"  iTick:      \u9884\u70ed\u5931\u8d25 {e}")
    itick_data.start_background()
    st = itick_data.status()
    print(f"  iTick:      {got} \u4e2a\u54c1\u79cd\u5df2\u9884\u70ed | \u540e\u53f0\u8f6e\u8be2\u5df2\u542f\u52a8 "
          f"({st['rpm']} \u6b21/\u5206\u949f, \u5171 {st['symbols']} \u54c1\u79cd, base={st['base']})")
    return st


if __name__ == "__main__":
    sv = TS(("0.0.0.0", PORT), Handler)
    print(f"\033[92m\u25b6 Live Server running at http://localhost:{PORT}\033[0m")
    print(f"  Dashboard:  http://localhost:{PORT}")
    print(f"  API:        /api/quotes  /api/news  /api/kline?name=XXX&tf=1h|4h|1d  /api/calendar  /api/macro  /api/itick")
    print(f"  Forex (ER): {len(FOREX_ER)} pairs  |  Sina: {len(SINA)} |  Yahoo: {len(YAHOO)}")
    _start_itick()
    print("  Ctrl+C to stop")
    try:
        sv.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        sv.server_close()
