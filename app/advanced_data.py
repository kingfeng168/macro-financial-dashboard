# -*- coding: utf-8 -*-
"""进阶数据 (Advanced Data) 实时抓取模块。

为「进阶数据」面板提供免费的实时数据源：
  - FRED（官方 JSON API 优先，需免费 key；未配置时自动回退公开 CSV）：
      * DFII10     10年期 TIPS 实际收益率
      * T10YIE     10年期盈亏平衡通胀（市场通胀预期）
      * SOFR       担保隔夜融资利率
      * DCOILWTICO WTI 原油现货价
      * DCOILBRENTEU Brent 原油现货价
      * DTWEXBGS   贸易加权广义美元指数（DXY 权威代理）
  - BIS SDMX WS_EER（无需 key）：
      * 美/欧/日/英/瑞/加/澳/中 名义有效汇率(NEER) + 实际有效汇率(REER)，月度
  - EIA v2 REST（需免费 API key，EIA_API_KEY）：
      * WCRSTUS1 美国商业原油库存（千桶，周度），市场最关注的 EIA 库存口径
  - WGC 央行购金（www.gold.org Gold Demand Trends 文章解析，无需 key）
  - IMF COFER 外汇储备币种份额（SDMX 3.0，沙箱被 WAF 拦、真机实时，无需 key）

实时源（无需 key）：BIS 有效汇率 + WGC 央行购金 + IMF COFER(真机)；
需 key 实时源：FRED 官方 API（未配 key 时自动回退公开 CSV，仍保持实时）、EIA 原油库存。
对仍无免费实时源的数据（外汇掉期 / 黄金ETF / 黄金需求），
从 daily_data.json 取快照并标记 live=False，由前端显示「快照·更新于 X」。

统一入口：fetch_advanced_realtime(daily_data, force=False) -> dict
"""
import csv
import io
import json
import zipfile
import re
import ssl
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import urllib.request

# ---------- 基础 HTTP ----------
_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE


def _https_get(url, accept="*/*", timeout=25, binary=False):
    """简单 GET，返回 bytes 或 str。失败抛异常由调用方处理。"""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": accept,
    })
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
        data = r.read()
    return data if binary else data.decode("utf-8", "replace")


def _https_get_bytes(url, timeout=35):
    """GET 返回原始 bytes（用于 ZIP 等二进制）。CFTC 会拦截默认 UA，必须带浏览器 UA。"""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "*/*",
    })
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
        return r.read()


# ---------- FRED（官方 API 优先，公开 CSV 回退） ----------
# 公开分发版：FRED key 仅通过环境变量 FRED_API_KEY 提供，不在代码中硬编码。
#   不配 key 也能实时（自动回退公开 CSV 通道）；配了则走更稳定的官方 JSON API。
#   设置： Windows: set FRED_API_KEY=你的key   Linux/Mac: export FRED_API_KEY=你的key
FRED_API_KEY = os.environ.get("FRED_API_KEY") or ""
# 官方 JSON API：observation_start 精确过滤，结构化返回（无 CSV 表头歧义），端点更稳定
FRED_API = ("https://api.stlouisfed.org/fred/series/observations"
            "?series_id={id}&api_key={key}&file_type=json"
            "&observation_start={cosd}&sort_order=asc")
# 回退通道：公开 CSV（无需 key）。cosd 限制起始日，避免下载 6000+ 行完整历史（提速关键）
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}&cosd={cosd}"

# 序列 -> 中文名 / 用途
FRED_SERIES = {
    "DFII10": "10Y TIPS 实际收益率",
    "T10YIE": "10Y 盈亏平衡通胀",
    "SOFR": "SOFR 隔夜担保融资利率",
    "DCOILWTICO": "WTI 原油",
    "DCOILBRENTEU": "Brent 原油",
    "DTWEXBGS": "广义美元指数",
}

# ---------- EIA 原油库存（需 API key，v2 REST） ----------
# WCRSTUS1 = 美国商业原油库存（不含 SPR），千桶，周度；市场最关注的 EIA 库存口径。
# 公开分发版：EIA key 仅通过环境变量 EIA_API_KEY 提供，不在代码中硬编码。
#   运行前设置： Windows: set EIA_API_KEY=你的key   Linux/Mac: export EIA_API_KEY=你的key
EIA_API_KEY = os.environ.get("EIA_API_KEY") or ""
EIA_CRUDE_URL = "https://api.eia.gov/v2/petroleum/stoc/wstk/data"
EIA_CRUDE_SERIES = "WCRSTUS1"


def _fetch_fred_one(sid, days=120, timeout=12):
    """抓取单个 FRED 序列（带起始日过滤），返回 [[date, value|None], ...]。

    双通道，任一成功即返回：
      1) 官方 JSON API（需 FRED_API_KEY）——observation_start 精确过滤、结构化返回，
         无 CSV 表头歧义，且是专用数据端点，比图表端点更稳定；
      2) 公开 CSV fredgraph.csv（无需 key）——未配 key 或 API 失败时回退。

    两条通道均逐序列请求（fredgraph.csv 多 id 拼接会忽略 cosd 返回全历史，
    故必须逐序列），由上层并行调度；单序列失败不影响其他序列。
    """
    cosd = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    # ---- 通道1：官方 JSON API ----
    if FRED_API_KEY:
        try:
            url = FRED_API.format(id=sid, key=FRED_API_KEY, cosd=cosd)
            d = json.loads(_https_get(url, timeout=timeout))
            out = []
            for o in d.get("observations", []):
                v = (o.get("value") or ".").strip()
                try:
                    out.append([o.get("date"), None if v in (".", "") else float(v)])
                except (TypeError, ValueError):
                    out.append([o.get("date"), None])
            if out:
                return out
        except Exception:
            pass  # 落到 CSV 回退通道

    # ---- 通道2：公开 CSV 回退 ----
    out = []
    try:
        url = FRED_CSV.format(id=sid, cosd=cosd)
        raw = _https_get(url, timeout=timeout)
        lines = [ln for ln in raw.split("\n") if ln.strip()]
        if len(lines) < 2:
            return out
        header = [h.strip() for h in lines[0].split(",")]
        # FRED 单序列 CSV 首列为 observation_date；多序列为 DATE。
        # 兼容两种表头，避免首列判断失败导致整段数据被丢弃。
        date_idx = None
        for i, h in enumerate(header):
            if h.lower() in ("date", "observation_date"):
                date_idx = i
                break
        if date_idx is None:
            return out
        val_idx = 1 if date_idx == 0 else 0
        for ln in lines[1:]:
            parts = ln.split(",")
            if len(parts) <= max(date_idx, val_idx):
                continue
            d = parts[date_idx].strip()
            v = parts[val_idx].strip()
            try:
                out.append([d, None if v in (".", "NaN", "") else float(v)])
            except ValueError:
                out.append([d, None])
    except Exception:
        pass
    return out


def fetch_fred_all(series_ids, days=120, timeout=12, workers=6):
    """并行抓取多个 FRED 序列，返回 {sid: [[date, value|None], ...]}。

    逐序列请求（cosd 生效，仅取近 days 天）+ ThreadPoolExecutor 并行，
    兼顾「小下载量 / 正确日期窗口 / 单序列失败不影响其他序列」。
    """
    out = {sid: [] for sid in series_ids}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_fetch_fred_one, sid, days, timeout): sid for sid in series_ids}
        for f in futs:
            sid = futs[f]
            try:
                out[sid] = f.result()
            except Exception:
                out[sid] = []
    return out


# ---------- BIS 有效汇率（SDMX，无需 key） ----------
BIS_EER = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_EER/1.0/*?lastNObservations={n}"
# EER 区域代码 -> 中文名
EER_AREAS = ["US", "EA", "JP", "GB", "CH", "CA", "AU", "CN"]
EER_AREA_NAME = {
    "US": "美元", "EA": "欧元", "JP": "日元", "GB": "英镑",
    "CH": "瑞郎", "CA": "加元", "AU": "澳元", "CN": "人民币",
}


def fetch_bis_eer(lastn=13):
    """返回 {area: {'neer':(val,date), 'reer':(val,date), 'neer_series':[[t,v]], 'reer_series':[[t,v]]}}"""
    out = {}
    try:
        raw = _https_get(BIS_EER.format(n=lastn),
                         accept="application/vnd.sdmx.data+csv;version=1.0.0", timeout=15)
        reader = csv.DictReader(io.StringIO(raw))
        tmp = {}
        for row in reader:
            area = (row.get("REF_AREA") or "").strip()
            etype = (row.get("EER_TYPE") or "").strip()       # N 名义 / R 实际
            basket = (row.get("EER_BASKET") or "").strip()     # B 广义
            freq = (row.get("FREQ") or "").strip()            # M 月度
            tp = (row.get("TIME_PERIOD") or "").strip()
            val = row.get("OBS_VALUE")
            if basket != "B" or freq != "M":
                continue
            if area not in EER_AREAS:
                continue
            try:
                v = float(val)
            except (TypeError, ValueError):
                continue
            tmp.setdefault(area, {"N": [], "R": []})
            tmp[area][etype].append((tp, v))
        for area, d in tmp.items():
            neer = sorted(d.get("N", []))
            reer = sorted(d.get("R", []))
            out[area] = {
                "neer": (neer[-1][1], neer[-1][0]) if neer else (None, None),
                "reer": (reer[-1][1], reer[-1][0]) if reer else (None, None),
                "neer_series": [[t, round(v, 2)] for t, v in neer],
                "reer_series": [[t, round(v, 2)] for t, v in reer],
            }
    except Exception:
        pass
    return out


# ---------- CFTC COT（Traders in Financial Futures, 无需 key） ----------
# CFTC 将历史年报打包为年度 ZIP，路径 /files/dea/history/fut_fin_txt_{year}.zip
COT_YEAR_URL = "https://www.cftc.gov/files/dea/history/fut_fin_txt_{y}.zip"
# 主要币种 -> TFF 报告中的市场名关键字
COT_MARKETS = [
    ("EUR", "EURO FX"),
    ("JPY", "JAPANESE YEN"),
    ("GBP", "BRITISH POUND"),
    ("AUD", "AUSTRALIAN DOLLAR"),
    ("CAD", "CANADIAN DOLLAR"),
    ("CHF", "SWISS FRANC"),
    ("MXN", "MEXICAN PESO"),
    ("NZD", "NEW ZEALAND DOLLAR"),
]
COT_TREND_WEEKS = 24  # 走势图展示最近 N 周


def _parse_cot_year(txt):
    """解析 FinFutYY.txt：返回 {ccy: [row,...]}，每个币种按文件顺序（组内日期降序，首行=最新）。"""
    rdr = csv.DictReader(io.StringIO(txt))
    rows = {}
    for row in rdr:
        name = (row.get("Market_and_Exchange_Names") or "")
        for ccy, key in COT_MARKETS:
            if key in name:
                rows.setdefault(ccy, []).append(row)
                break
    return rows


def fetch_cot():
    """实时抓取 CFTC TFF 外汇持仓，返回 {live, items:[[ccy,类型,净持仓,变动,说明]...], report_date}。

    净持仓 = 多头 - 空头（合约）；杠杆基金 ≈ 投机盘，全体 = 所有报告商合计。
    无 key、CFTC 官方公开源；下载失败回退 live=False。
    """
    out = {"live": False, "items": [], "series": {}, "report_date": None}
    year = datetime.now().year
    for y in (year, year - 1):
        try:
            data = _https_get_bytes(COT_YEAR_URL.format(y=y), timeout=35)
            z = zipfile.ZipFile(io.BytesIO(data))
            name = [n for n in z.namelist() if n.lower().endswith(".txt")][0]
            txt = z.read(name).decode("latin1", "replace")
            rows_by_ccy = _parse_cot_year(txt)
            if not rows_by_ccy:
                continue
            report_dates = [(r[0].get("Report_Date_as_YYYY-MM-DD") or "").strip()
                           for r in rows_by_ccy.values() if r]
            report_date = max(report_dates)

            def _int(row, k):
                try:
                    return int((row.get(k) or "0").replace(",", "").strip() or 0)
                except (ValueError, TypeError):
                    return 0

            def _fmt(v):
                return f"{v:+,}"

            items = []
            series = {}
            for ccy, _ in COT_MARKETS:
                rl = rows_by_ccy.get(ccy)
                if not rl:
                    continue
                row = rl[0]  # 最新周
                lev_net = _int(row, "Lev_Money_Positions_Long_All") - _int(row, "Lev_Money_Positions_Short_All")
                lev_chg = _int(row, "Change_in_Lev_Money_Long_All") - _int(row, "Change_in_Lev_Money_Short_All")
                tot_net = _int(row, "Tot_Rept_Positions_Long_All") - _int(row, "Tot_Rept_Positions_Short_All")
                tot_chg = _int(row, "Change_in_Tot_Rept_Long_All") - _int(row, "Change_in_Tot_Rept_Short_All")
                items.append([ccy, "杠杆基金净", _fmt(lev_net), _fmt(lev_chg), ""])
                items.append([ccy, "全体净", _fmt(tot_net), _fmt(tot_chg), ""])
                # 历史净持仓（rl 降序，取最近 N 周并翻转为升序）
                hist = rl[:COT_TREND_WEEKS][::-1]
                dates, lev, tot = [], [], []
                for r in hist:
                    d = (r.get("Report_Date_as_YYYY-MM-DD") or "").strip()
                    if not d:
                        continue
                    dates.append(d)
                    lev.append(_int(r, "Lev_Money_Positions_Long_All") - _int(r, "Lev_Money_Positions_Short_All"))
                    tot.append(_int(r, "Tot_Rept_Positions_Long_All") - _int(r, "Tot_Rept_Positions_Short_All"))
                series[ccy] = {"dates": dates, "lev": lev, "tot": tot}
            if items:
                return {"live": True, "items": items, "series": series, "report_date": report_date}
        except Exception:
            continue
    return out


# ---------- EIA 原油库存（需 API key） ----------
def fetch_eia_crude(api_key=None, weeks=60, timeout=30):
    """抓取 EIA 周度美国商业原油库存 (WCRSTUS1，千桶)。返回带 live 标记的结构。

    路径: petroleum/stoc/wstk/data，按 facets[series][]=WCRSTUS1 过滤；
    注意 EIA v2 要求 data[0]=value 这类方括号参数，urllib 直拼 URL 即可（无需 curl 转义）。
    """
    ak = api_key or EIA_API_KEY
    if not ak:
        return {"live": False, "error": "no EIA key", "series": {}, "items": []}
    try:
        params = (
            "api_key=%s&frequency=weekly&data[0]=value"
            "&facets[series][]=%s"
            "&sort[0][column]=period&sort[0][direction]=desc&offset=0&length=%d"
        ) % (ak, EIA_CRUDE_SERIES, weeks)
        url = EIA_CRUDE_URL + "?" + params
        raw = _https_get(url, timeout=timeout)
        d = json.loads(raw)
        r = d.get("response", {})
        data = r.get("data", [])
        if not data:
            return {"live": False, "error": "empty payload", "series": {}, "items": []}
        recs = []
        for x in data:
            p = x.get("period")
            v = x.get("value")
            if p is None or v in (None, ""):
                continue
            try:
                v = float(v)
            except Exception:
                continue
            recs.append((p, v))
        if not recs:
            return {"live": False, "error": "no valid rows", "series": {}, "items": []}
        recs.sort(key=lambda t: t[0])
        labels = [t[0] for t in recs]
        vals = [t[1] for t in recs]
        latest_p, latest_v = recs[-1]
        prev_v = recs[-2][1] if len(recs) >= 2 else None
        change = (latest_v - prev_v) if prev_v is not None else None
        yoy = (latest_v - recs[-53][1]) if len(recs) >= 53 else None
        desc = (data[0].get("series-description") or "U.S. Ending Stocks of Crude Oil").replace("(Thousand Barrels)", "").strip()
        note = ("EIA 周度美国商业原油库存 (WCRSTUS1，千桶)，最新 %s；"
                "周变动 = 最新 − 上周；同比≈最新 − 去年同周。通常每周三 22:30(北京时间) 公布。") % latest_p
        items = [
            ["最新库存", "%.0f 千桶" % latest_v, "", latest_p],
            ["周变动", (("+%.0f" % change) if change >= 0 else "%.0f" % change) if change is not None else "--", "", "vs 上周"],
            ["同比(约1年)", (("+%.0f" % yoy) if yoy >= 0 else "%.0f" % yoy) if yoy is not None else "--", "", "vs 去年同周"],
        ]
        return {
            "live": True,
            "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "series_id": EIA_CRUDE_SERIES,
            "desc": desc,
            "latest_period": latest_p,
            "latest_value": round(latest_v, 1),
            "prev_value": round(prev_v, 1) if prev_v is not None else None,
            "change": round(change, 1) if change is not None else None,
            "yoy": round(yoy, 1) if yoy is not None else None,
            "unit": "千桶",
            "items": items,
            "series": {"美国商业原油库存(千桶)": [[labels[i], round(vals[i], 1)] for i in range(len(labels))]},
            "note": note,
        }
    except Exception as e:
        return {"live": False, "error": str(e), "series": {}, "items": []}


# ---------- WGC 央行购金（www.gold.org 可达；api.gold.org 沙箱被拦） ----------
def fetch_wgc_cb_gold(timeout=25):
    """实时抓取 WGC 全球央行季度净购金（Gold Demand Trends 最新一期 central-banks 章节）。

    沙箱仅 www.gold.org 主站可达，图表明细走 api.gold.org（被拦）；故解析文章叙述文本提取
    最新季度净购金(t)与上半年合计。季度发布，季后约5-6周公布。失败回退快照。
    """
    try:
        land = _https_get("https://www.gold.org/goldhub/research/gold-demand-trends", timeout=timeout)
        slugs = re.findall(r"gold-demand-trends/gold-demand-trends-q([1-4])-(\d{4})", land)
        if not slugs:
            return {"live": False, "error": "no GDT slug", "items": []}
        best = max(slugs, key=lambda t: (int(t[1]), int(t[0])))
        q, y = best
        slug = "gold-demand-trends-q%s-%s" % (q, y)
        url = "https://www.gold.org/goldhub/research/gold-demand-trends/%s/central-banks" % slug
        html = _https_get(url, timeout=timeout)
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text)
        # 最新季度净购金
        latest_v = None
        for pat in (r"Net purchases totalled[^\d]{0,50}?([0-9,]+)t in Q",
                    r"reaching ([0-9,]+)t",
                    r"net purchases[^.]{0,120}?([0-9,]+)t"):
            m = re.search(pat, text, re.I)
            if m:
                latest_v = int(m.group(1).replace(",", ""))
                break
        # 上半年合计
        h1_v = None
        mh = re.search(r"H1 net demand of ([0-9,]+)t", text)
        if not mh:
            mh = re.search(r"H1[^.]{0,80}?([0-9,]+)t", text)
        if mh:
            h1_v = int(mh.group(1).replace(",", ""))
        # 上一季度（best-effort）
        prev_v = None
        mp = re.search(r"Q1'?s revised estimate of ([0-9,]+)t", text)
        if not mp:
            mp = re.search(r"up [0-9]+% from ([0-9,]+)t in the previous quarter", text)
        if mp:
            prev_v = int(mp.group(1).replace(",", ""))
        label = "%s Q%s" % (y, q)
        items = []
        if latest_v is not None:
            items.append([label, "%d t" % latest_v, "", "最新季度净购金"])
        if prev_v is not None:
            items.append(["上一季度", "%d t" % prev_v, "", ""])
        if h1_v is not None:
            items.append(["%s H1" % y, "%d t" % h1_v, "", "上半年合计"])
        note = ("数据来源 WGC Gold Demand Trends（%s），季度发布；图表明细走 api.gold.org 沙箱不可达，"
                "此处解析文章叙述提取最新季度净购金。通常季后约5-6周公布。") % slug
        if not items:
            return {"live": False, "error": "parse empty", "items": []}
        return {
            "live": True,
            "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "latest_quarter": label,
            "latest_value": latest_v,
            "h1_value": h1_v,
            "items": items,
            "note": note,
            "source": slug,
        }
    except Exception as e:
        return {"live": False, "error": str(e), "items": []}


# ---------- IMF COFER 外汇储备币种份额（SDMX 3.0，沙箱被 WAF 拦，真机可达） ----------
def fetch_imf_cofer(timeout=25):
    """实时抓取 IMF COFER 全球外汇储备币种份额（美元/欧元/日元/英镑/人民币）。

    SDMX 3.0 REST: https://www.imf.org/Services/SDMX/3.0/REST/data/COFER/...
    维度 key 顺序 FREQ.AREA.CURRENCY.MEASURE，示例 Q.G001.AFXRA.CI_USD.SHRO_PT
    (G001=World; CURRENCY=CI_USD/EUR/JPY/GBP/CNY; MEASURE=SHRO_PT 份额%)。
    沙箱被 IMF Akamai WAF 拦(403)，真机可达；失败抛异常由调用方回退快照。
    """
    ccy_codes = ["CI_USD", "CI_EUR", "CI_JPY", "CI_GBP", "CI_CNY"]
    ccy_names = {"CI_USD": "美元", "CI_EUR": "欧元", "CI_JPY": "日元", "CI_GBP": "英镑", "CI_CNY": "人民币"}
    key = "Q.G001.AFXRA." + "+".join(ccy_codes) + ".SHRO_PT"
    bases = [
        "https://www.imf.org/Services/SDMX/3.0/REST/data/COFER/",
        "https://api.imf.org/external/sdmx/3.0/rest/data/COFER/",
    ]
    raw = None
    last_err = ""
    for base in bases:
        try:
            url = base + key + "?format=csvfile"
            r = _https_get(url, accept="application/vnd.sdmx.data+csv;version=2.0.0", timeout=timeout)
            if r and "OBS_VALUE" in r:
                raw = r
                break
        except Exception as e:
            last_err = str(e)
    if not raw:
        raise RuntimeError("COFER 所有端点不可达: " + last_err)
    lines = [ln for ln in raw.replace("\r", "").split("\n") if ln.strip()]
    if len(lines) < 2:
        raise ValueError("COFER csv 行数不足")
    hdr = [h.strip().strip('"') for h in lines[0].split(",")]
    i_cur = hdr.index("CURRENCY") if "CURRENCY" in hdr else None
    i_tp = hdr.index("TIME_PERIOD") if "TIME_PERIOD" in hdr else (hdr.index("TIME") if "TIME" in hdr else None)
    if i_tp is None:
        raise ValueError("COFER csv 缺少 TIME 列")
    i_val = hdr.index("OBS_VALUE") if "OBS_VALUE" in hdr else (hdr.index("VALUE") if "VALUE" in hdr else len(hdr) - 1)
    per_ccy = {}
    for ln in lines[1:]:
        parts = [p.strip().strip('"') for p in ln.split(",")]
        if len(parts) <= max(i_tp, i_val):
            continue
        ccy = parts[i_cur] if i_cur is not None else ccy_codes[0]
        tp = parts[i_tp]
        try:
            val = float(parts[i_val])
        except Exception:
            continue
        per_ccy.setdefault(ccy, {"series": []})["series"].append([tp, val])
    shares = {}
    for ccy, rec in per_ccy.items():
        rec["series"].sort(key=lambda t: t[0])
        rec["latest_period"], rec["latest_val"] = rec["series"][-1]
        shares[ccy] = round(rec["latest_val"], 2)
    if not shares:
        raise ValueError("COFER 未解析到任何有效行")
    latest_period = max(rec["latest_period"] for rec in per_ccy.values())
    items = []
    for ccy in ccy_codes:
        if ccy not in shares:
            continue
        rec = per_ccy[ccy]
        s = rec["series"]
        cur = rec["latest_val"]
        prev = s[-2][1] if len(s) >= 2 else None
        chg = round(cur - prev, 2) if prev is not None else None
        chg_str = ("%.2f" % chg) if chg is not None else "--"
        if chg is not None and chg >= 0:
            chg_str = "+" + chg_str
        items.append([ccy_names[ccy], "%.2f" % cur, chg_str, rec["latest_period"]])
    series = {}
    for ccy in ["CI_USD", "CI_EUR", "CI_CNY", "CI_JPY", "CI_GBP"]:
        if ccy in per_ccy:
            series[ccy_names[ccy] + "份额%"] = [[p, round(v, 2)] for p, v in per_ccy[ccy]["series"]]
    note = ("数据来源 IMF COFER（官方外汇储备币种构成，SDMX 3.0 实时接口），季度发布，最新 %s；"
            "份额=各币种占全球已披露外汇储备比例(%%)。") % latest_period
    return {
        "live": True,
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date": latest_period,
        "usd": shares.get("CI_USD"), "eur": shares.get("CI_EUR"),
        "jpy": shares.get("CI_JPY"), "gbp": shares.get("CI_GBP"), "cny": shares.get("CI_CNY"),
        "items": items, "series": series, "note": note,
    }


# ---------- 统一入口 ----------
def fetch_advanced_realtime(daily_data, force=False):
    """聚合所有进阶数据，返回带 live 标记与时间戳的结构。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sections = {}
    live_parts = []

    # 1) TIPS / 盈亏平衡 / SOFR / 原油 / 美元指数（FRED 日频）+ 4) BIS 有效汇率
    #    —— FRED 6 序列并行逐序列请求(fetch_fred_all, cosd 生效仅取120天) 与 BIS 并行抓取，
    #       最坏耗时≈max(单序列FRED, BIS)≈12s；单序列失败仅该板块回退快照。
    _fred_ids = ["DFII10", "T10YIE", "SOFR", "DCOILWTICO", "DCOILBRENTEU", "DTWEXBGS"]
    with ThreadPoolExecutor(max_workers=6) as ex:
        _fred_fut = ex.submit(fetch_fred_all, _fred_ids, 120, 12)
        _bis_fut = ex.submit(fetch_bis_eer, 13)
        _cot_fut = ex.submit(fetch_cot)
        _macro_fut = ex.submit(fetch_fred_all, ["CPIAUCSL", "UNRATE"], 820, 15)
        _eia_fut = ex.submit(fetch_eia_crude)
        _wgc_fut = ex.submit(fetch_wgc_cb_gold)
        _cofer_fut = ex.submit(fetch_imf_cofer)
        try:
            # 硬超时兜底：即使 urllib 内部 timeout 在某些网络下未触发，
            # 也保证整个实时抓取不超过 ~15s，避免刷新卡死。
            _fred_all = _fred_fut.result(timeout=15)
        except Exception:
            _fred_all = {sid: [] for sid in _fred_ids}
        try:
            eer_raw = _bis_fut.result(timeout=18)
        except Exception:
            eer_raw = {}
        try:
            _cot = _cot_fut.result(timeout=25)
        except Exception:
            _cot = {"live": False, "items": [], "report_date": None}
        try:
            _fred_macro = _macro_fut.result(timeout=20)
        except Exception:
            _fred_macro = {}
        try:
            _eia = _eia_fut.result(timeout=20)
        except Exception:
            _eia = {"live": False, "error": "timeout", "series": {}, "items": []}
        try:
            _wgc = _wgc_fut.result(timeout=20)
        except Exception:
            _wgc = {"live": False, "error": "timeout", "series": {}, "items": []}
        try:
            _cofer = _cofer_fut.result(timeout=20)
        except Exception:
            _cofer = {"live": False, "items": [], "series": {}}

    def _pick(sid, lastn=60):
        lst = _fred_all.get(sid, [])
        s = [p for p in lst if p[1] is not None]
        if not s:
            return None, None, []
        tail = s[-lastn:]
        return tail[-1][1], tail[-1][0], [[d, round(v, 2)] for d, v in tail]

    dfii_v, dfii_d, dfii_s = _pick("DFII10")
    t10_v, t10_d, t10_s = _pick("T10YIE")
    sofr_v, sofr_d, _ = _pick("SOFR", 30)
    wti_v, wti_d, wti_s = _pick("DCOILWTICO")
    brent_v, brent_d, brent_s = _pick("DCOILBRENTEU")
    usd_v, usd_d, usd_s = _pick("DTWEXBGS")
    # FRED 实时是否成功（用于 live 标记，须在快照回退前判定）
    _fred_tips_ok = not (dfii_v is None and t10_v is None and sofr_v is None)
    _fred_oil_ok = not (wti_v is None and brent_v is None)
    _fred_usd_ok = usd_v is not None
    # —— 快照回退：FRED 不可达时用 daily_data 最新快照填充，避免面板空白 ——
    snap = daily_data or {}
    _tb = snap.get("tips_breakeven", {}) or {}
    _tips_snap_date = None
    if dfii_v is None and _tb.get("dfii10"):
        dfii_v = _tb["dfii10"].get("latest"); dfii_d = _tb["dfii10"].get("date"); dfii_s = _tb["dfii10"].get("series", []) or []; _tips_snap_date = _tb.get("updated")
    if t10_v is None and _tb.get("t10yie"):
        t10_v = _tb["t10yie"].get("latest"); t10_d = _tb["t10yie"].get("date"); t10_s = _tb["t10yie"].get("series", []) or []; _tips_snap_date = _tb.get("updated")
    tips_live = _fred_tips_ok
    spread_note = ""
    if dfii_v is not None and t10_v is not None:
        spread = t10_v - dfii_v
        spread_note = ("10Y 盈亏平衡通胀 %.2f%% − 10Y TIPS 实际收益率 %.2f%% = 利差 %.2f%%"
                       "（反映市场通胀预期）") % (t10_v, dfii_v, spread)
    sections["tips"] = {
        "live": tips_live,
        "fetched_at": (_tips_snap_date if (not _fred_tips_ok and _tips_snap_date) else now),
        "dfii10": {"value": dfii_v, "date": dfii_d},
        "t10yie": {"value": t10_v, "date": t10_d},
        "sofr": {"value": sofr_v, "date": sofr_d},
        "spread_note": spread_note,
        "labels": [d for d, _ in dfii_s],
        "series": {
            "TIPS实际收益率(DFII10)": [[d, round(v, 2)] for d, v in dfii_s],
            "盈亏平衡通胀(T10YIE)": [[d, round(v, 2)] for d, v in t10_s],
        },
    }
    if tips_live:
        live_parts.append("FRED")

    # 2) 原油（FRED 日频，实时，已在上方并行取得）
    oil_live = _fred_oil_ok
    sections["oil"] = {
        "live": oil_live,
        "fetched_at": now,
        "wti": {"value": wti_v, "date": wti_d},
        "brent": {"value": brent_v, "date": brent_d},
        "labels": [d for d, _ in wti_s],
        "series": {
            "WTI原油": [[d, round(v, 2)] for d, v in wti_s],
            "Brent原油": [[d, round(v, 2)] for d, v in brent_s],
        },
    }
    if oil_live:
        live_parts.append("FRED")

    # 3) 广义美元指数（FRED 日频，实时，DXY 代理，已并行取得）
    sections["usd_index"] = {
        "live": _fred_usd_ok,
        "fetched_at": now,
        "value": usd_v,
        "date": usd_d,
        "labels": [d for d, _ in usd_s],
        "series": {"广义美元指数(DTWEXBGS)": [[d, round(v, 2)] for d, v in usd_s]},
        "note": "DTWEXBGS = 贸易加权广义美元指数（商品与服务·广义口径），作为 DXY 的权威代理指标",
    }
    if usd_v is not None:
        live_parts.append("FRED")

    # 4) BIS 有效汇率（已在上方与 FRED 并行取得）
    eer_areas = []
    for code in EER_AREAS:
        d = eer_raw.get(code)
        if not d:
            continue
        neer_v, neer_d = d["neer"]
        reer_v, reer_d = d["reer"]
        eer_areas.append({
            "code": code,
            "name": EER_AREA_NAME.get(code, code),
            "neer": neer_v, "neer_date": neer_d,
            "reer": reer_v, "reer_date": reer_d,
            "neer_series": d["neer_series"],
            "reer_series": d["reer_series"],
        })
    eer_live = bool(eer_areas)
    if not eer_areas:
        # BIS 不可达时，回退到 daily_data 的 USD Broad 快照
        _ed = snap.get("eer_data", []) or []
        _es = snap.get("eer_series", {}) or {}
        _neer_val = next((r[1] for r in _ed if "NEER" in str(r[0])), None)
        _reer_val = next((r[1] for r in _ed if "REER" in str(r[0])), None)
        _neer_ser = _es.get("美元NEER", [])
        _labels = _es.get("labels", [])
        _neer_series = [[_labels[i], round(v, 2)] for i, v in enumerate(_neer_ser)] if (_labels and _neer_ser) else []
        if _neer_val is not None or _reer_val is not None:
            eer_areas.append({"code": "US", "name": "美元", "neer": _neer_val, "neer_date": "快照",
                              "reer": _reer_val, "reer_date": "快照", "neer_series": _neer_series, "reer_series": []})
            eer_live = False
    sections["eer"] = {
        "live": eer_live,
        "fetched_at": now,
        "areas": eer_areas,
        "note": "BIS 有效汇率指数(2020=100)，月度更新；NEER=名义有效汇率，REER=实际有效汇率",
    }
    if eer_live:
        live_parts.append("BIS")

    # 4b) 美国 CPI（同比/月率）与失业率（FRED 月频，实时，需 ~13 个月历史算同比）
    _cpi_s = _fred_macro.get("CPIAUCSL", [])
    _un_s = _fred_macro.get("UNRATE", [])
    _cpi_vals = [p for p in _cpi_s if p[1] is not None]
    _un_vals = [p for p in _un_s if p[1] is not None]
    cpi_sec = {"live": bool(_cpi_vals), "fetched_at": now, "value": None,
               "yoy": None, "mom": None, "date": None, "series": {}}
    unrate_sec = {"live": bool(_un_vals), "fetched_at": now, "value": None,
                  "change": None, "date": None, "series": {}}
    if _cpi_vals:
        cpi_sec["value"] = round(_cpi_vals[-1][1], 2)
        cpi_sec["date"] = _cpi_vals[-1][0]
        if len(_cpi_vals) >= 2:
            cpi_sec["mom"] = round((_cpi_vals[-1][1] / _cpi_vals[-2][1] - 1) * 100, 2)
        if len(_cpi_vals) >= 13:
            cpi_sec["yoy"] = round((_cpi_vals[-1][1] / _cpi_vals[-13][1] - 1) * 100, 2)
            yoy_series = []
            for i in range(12, len(_cpi_vals)):
                try:
                    y = (_cpi_vals[i][1] / _cpi_vals[i - 12][1] - 1) * 100
                except Exception:
                    y = None
                yoy_series.append([_cpi_vals[i][0], None if y is None else round(y, 2)])
            cpi_sec["series"] = {"美国CPI同比%": yoy_series}
        if _cpi_vals:
            live_parts.append("FRED")
    if _un_vals:
        unrate_sec["value"] = round(_un_vals[-1][1], 2)
        unrate_sec["date"] = _un_vals[-1][0]
        if len(_un_vals) >= 2:
            unrate_sec["change"] = round(_un_vals[-1][1] - _un_vals[-2][1], 2)
        unrate_sec["series"] = {"美国失业率%": [[d, round(v, 2)] for d, v in _un_vals]}
        if _un_vals:
            live_parts.append("FRED")
    sections["cpi"] = cpi_sec
    sections["unemployment"] = unrate_sec

    # 5) 快照类：外汇掉期 / COFER / COT / 央行购金 / 黄金ETF / 黄金需求 / EIA库存
    snap = daily_data or {}
    sections["fx_swap"] = {
        "live": False,
        "updated": snap.get("updated"),
        "items": snap.get("fx_swap_data", []) or [],
        "note": snap.get("fx_swap_note", ""),
    }
    cofer = snap.get("cofer_data", {}) or {}
    if _cofer.get("live"):
        sections["cofer"] = {
            "live": True,
            "fetched_at": _cofer.get("fetched_at"),
            "date": _cofer.get("date"),
            "usd": _cofer.get("usd"), "eur": _cofer.get("eur"),
            "jpy": _cofer.get("jpy"), "gbp": _cofer.get("gbp"), "cny": _cofer.get("cny"),
            "items": _cofer.get("items", []),
            "series": _cofer.get("series", {}),
            "note": _cofer.get("note"),
        }
        live_parts.append("IMF")
    else:
        sections["cofer"] = {
            "live": False, "updated": cofer.get("date"), "data": cofer,
        }
    # 5b) COT（CFTC TFF）— 实时抓取（无需 key）；失败回退 daily_data 快照
    if _cot.get("live"):
        cot_note = ("CFTC TFF 期货-only，最新报告日 %s；净持仓=多头-空头(合约，正=净多/负=净空)；"
                    "杠杆基金≈投机盘，全体=所有报告商。每周五发布、数据截至上周二。") % _cot["report_date"]
        sections["cot"] = {
            "live": True,
            "fetched_at": now,
            "series": _cot.get("series", {}),
            "data": {"items": _cot["items"], "note": cot_note},
        }
        live_parts.append("CFTC")
    else:
        cot = snap.get("cot_data", {}) or {}
        sections["cot"] = {
            "live": False, "updated": cot.get("date"), "data": cot,
        }
    if _wgc.get("live"):
        sections["cb_gold"] = {
            "live": True,
            "fetched_at": _wgc.get("fetched_at"),
            "latest_quarter": _wgc.get("latest_quarter"),
            "latest_value": _wgc.get("latest_value"),
            "h1_value": _wgc.get("h1_value"),
            "items": _wgc.get("items", []),
            "note": _wgc.get("note"),
        }
        live_parts.append("WGC")
    else:
        sections["cb_gold"] = {
            "live": False, "items": snap.get("cb_gold_data", []) or [],
            "note": snap.get("cb_gold_note", ""),
        }
    sections["etf_gold"] = {
        "live": False, "items": snap.get("etf_gold_data", []) or [],
        "note": snap.get("etf_gold_note", ""),
    }
    sections["gold_demand"] = {
        "live": False, "data": snap.get("gold_demand_data", {}) or {},
    }
    sections["eia_oil"] = {
        "live": bool(_eia.get("live")),
        "fetched_at": _eia.get("fetched_at"),
        "series_id": _eia.get("series_id"),
        "desc": _eia.get("desc"),
        "latest_period": _eia.get("latest_period"),
        "latest_value": _eia.get("latest_value"),
        "prev_value": _eia.get("prev_value"),
        "change": _eia.get("change"),
        "yoy": _eia.get("yoy"),
        "unit": _eia.get("unit"),
        "items": _eia.get("items", []),
        "series": _eia.get("series", {}),
        "note": _eia.get("note"),
    } if _eia.get("live") else {
        "live": False, "data": snap.get("chart_adv_oil", {}) or {},
        "items": _eia.get("items", []), "error": _eia.get("error"),
    }
    if _eia.get("live"):
        live_parts.append("EIA")
    sections["dxy_ibs"] = {
        "live": False, "data": snap.get("dxy_ibs", {}) or {},
    }
    sections["eia_iea_oil"] = {
        "live": False, "data": snap.get("oil_data", {}) or {},
    }

    ok = bool(live_parts)
    return {
        "ok": ok,
        "fetched_at": now,
        "source": " + ".join(dict.fromkeys(live_parts)) if live_parts else "全部快照回退",
        "sections": sections,
    }
