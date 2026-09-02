# -*- coding: utf-8 -*-
"""进阶数据 (Advanced Data) 实时抓取模块。

为「进阶数据」面板提供免费、无需密钥的实时数据源：
  - FRED 公开 CSV（无需 key）：
      * DFII10     10年期 TIPS 实际收益率
      * T10YIE     10年期盈亏平衡通胀（市场通胀预期）
      * SOFR       担保隔夜融资利率
      * DCOILWTICO WTI 原油现货价
      * DCOILBRENTEU Brent 原油现货价
      * DTWEXBGS   贸易加权广义美元指数（DXY 权威代理）
  - BIS SDMX WS_EER（无需 key）：
      * 美/欧/日/英/瑞/加/澳/中 名义有效汇率(NEER) + 实际有效汇率(REER)，月度

对无免费实时源的数据（外汇掉期 / COFER / COT / WGC央行购金 / 黄金ETF / 黄金需求 / EIA库存），
从 daily_data.json 取快照并标记 live=False，由前端显示「快照·更新于 X」。

统一入口：fetch_advanced_realtime(daily_data, force=False) -> dict
"""
import csv
import io
import json
import re
import ssl
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


# ---------- FRED 公开 CSV（无需 key） ----------
# cosd 限制起始日，避免下载 6000+ 行完整历史（提速关键）
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


def _fetch_fred_one(sid, days=120, timeout=12):
    """抓取单个 FRED 序列（带 cosd 起始日过滤），返回 [[date, value|None], ...]。

    注意：FRED 的 fredgraph.csv 在多 id 拼接时会**忽略 cosd**（返回全历史），
    因此改为逐序列请求 + cosd，由上层并行调度——既保留 120 天窗口，又缩小单次下载量。
    """
    out = []
    try:
        cosd = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
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
    with ThreadPoolExecutor(max_workers=2) as ex:
        _fred_fut = ex.submit(fetch_fred_all, _fred_ids, 120, 12)
        _bis_fut = ex.submit(fetch_bis_eer, 13)
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

    # 5) 快照类：外汇掉期 / COFER / COT / 央行购金 / 黄金ETF / 黄金需求 / EIA库存
    snap = daily_data or {}
    sections["fx_swap"] = {
        "live": False,
        "updated": snap.get("updated"),
        "items": snap.get("fx_swap_data", []) or [],
        "note": snap.get("fx_swap_note", ""),
    }
    cofer = snap.get("cofer_data", {}) or {}
    sections["cofer"] = {
        "live": False, "updated": cofer.get("date"), "data": cofer,
    }
    cot = snap.get("cot_data", {}) or {}
    sections["cot"] = {
        "live": False, "updated": cot.get("date"), "data": cot,
    }
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
        "live": False, "data": snap.get("chart_adv_oil", {}) or {},
    }
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
