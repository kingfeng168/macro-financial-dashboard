# -*- coding: utf-8 -*-
"""统一金融日报生成器 - 读取daily_data.json生成HTML+Excel
用法: python generate_report.py [daily_data.json]
"""
import json, os, sys
from datetime import datetime, timedelta

DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("WORKBUDDY_DATA_DIR", DIR)
DATA_FILE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(DATA_DIR, "daily_data.json")
with open(DATA_FILE, 'r', encoding='utf-8') as f:
    D = json.load(f)

# Enhance calendar actuals before report generation
import calendar_fetcher
D = calendar_fetcher.fetch_calendar_actuals(D)

DATE = D["date"]
MONTHS = D["months"]
CUTOFF = D.get("cutoff_time", f"{DATE} 收盘")
C = ["#58a6ff","#ff7b72","#7ee787","#ffa657","#d2a8ff","#79c0ff","#f0883e","#a5d6ff","#ff9ec7","#b3f0ff","#ffd700","#ff6b6b","#4ecdc4","#95e1d3","#c084fc","#fb7185","#f9c74f","#90be6d","#f3722c","#43aa8b","#577590","#e76f51","#8ecae6","#ffb703"]
# Output to D:\workbuddy\输出文件 per user preference (avoid C: drive for deliverables)
OUTPUT_DIR = os.environ.get("WORKBUDDY_OUTPUT", "D:/workbuddy/输出文件")
os.makedirs(OUTPUT_DIR, exist_ok=True)
HTML_OUT = os.path.join(OUTPUT_DIR, f"全球金融日报_{DATE}.html")
XLSX_OUT = os.path.join(OUTPUT_DIR, f"全球金融日报_{DATE}_V9.xlsx")

def fc(v):
    return '<span class="flat">-</span>' if v is None else f'<span class="pos">+{v:.2f}</span>' if v>0 else f'<span class="neg">{v:.2f}</span>' if v<0 else '<span class="flat">0.00</span>'
def fa(v):
    return '<span class="flat">-</span>' if v is None else '<span class="pos">&#9650;</span>' if v>0 else '<span class="neg">&#9660;</span>' if v<0 else '<span class="flat">&#9670;</span>'
def fn(v,d=2):
    return '<span class="flat">-</span>' if v is None else f'{v:.{d}f}'
def co():
    return f'<div class="co-note cutoff-note">&#9201; 数据截止时间: {CUTOFF}</div>'

# Series maps for click-to-highlight
SMAP = {
    "overview": {"道琼斯工业平均指数":"道琼斯","标普500指数":"标普500","纳斯达克综合指数":"纳斯达克","恒生指数":"恒生指数","恒生科技指数":"恒生科技","日经225指数":"日经225","德国DAX30":"德国DAX","英国富时100指数":"英国富时100","美元指数":"美元指数","欧元/美元":"EUR/USD","美元/日元":"USD/JPY","英镑/美元":"GBP/USD","现货黄金":"现货黄金","现货白银":"现货白银","WTI原油":"WTI原油","布伦特原油":"布伦特原油","SOFR隔夜":"SOFR隔夜","USD IRS 10Y":"USD IRS 10Y","ESTR":"ESTR","比特币":"比特币","美国VIX恐慌指数":"美国VIX恐慌指数"},
    "forex": {"欧元/美元":"EUR/USD","英镑/美元":"GBP/USD","澳元/美元":"AUD/USD","美元/日元":"USD/JPY","美元/瑞郎":"USD/CHF","美元/加元":"USD/CAD","新西兰元/美元":"NZD/USD","美元/港币":"USD/HKD","美元指数":"美元指数","欧元/日元(交叉盘)":"EUR/JPY","英镑/日元(交叉盘)":"GBP/JPY","欧元/英镑(交叉盘)":"EUR/GBP","澳元/日元(交叉盘)":"AUD/JPY","欧元/瑞郎(交叉盘)":"EUR/CHF"},
    "commodities": {"现货黄金":"现货黄金","现货白银":"现货白银","WTI原油":"WTI原油","布伦特原油":"布伦特原油","天然气":"天然气"},
    "bonds": {"美国2年期国债":"美国2年期","美国5年期国债":"美国5年期","美国10年期国债":"美国10年期","美国30年期国债":"美国30年期","德国10年期国债":"德国10年期","英国10年期国债":"英国10年期","法国10年期国债":"法国10年期","意大利10年期国债":"意大利10年期","日本10年期国债":"日本10年期","澳大利亚10年期国债":"澳大利亚10年期"},
    "ois_irs": {("SOFR","隔夜"):"SOFR隔夜",("SOFR","3个月"):"SOFR 3M",("ESTR","隔夜"):"ESTR",("SONIA","隔夜"):"SONIA",("TONA","隔夜"):"TONA",("Fed Funds","有效利率"):"Fed Funds",("USD IRS","2年"):"USD IRS 2Y",("USD IRS","10年"):"USD IRS 10Y",("EUR IRS","10年"):"EUR IRS 10Y",("GBP IRS","10年"):"GBP IRS 10Y",("JPY IRS","10年"):"JPY IRS 10Y"},
    "indices": {"道琼斯工业平均指数":"道琼斯","标普500指数":"标普500","纳斯达克综合指数":"纳斯达克","恒生指数":"恒生指数","恒生科技指数":"恒生科技","日经225指数":"日经225","韩国KOSPI指数":"韩国KOSPI","德国DAX30指数":"德国DAX","英国富时100指数":"英国富时100","法国CAC40指数":"法国CAC40","欧洲斯托克50指数":"欧洲斯托克50","澳大利亚ASX200指数":"澳大利亚ASX200","印度Sensex指数":"印度Sensex"},
    "macro": {"美元指数(DXY)":"美元指数","SOFR隔夜":"SOFR隔夜","ESTR(欧元短期利率)":"ESTR","SONIA(英镑隔夜指数)":"SONIA","USD IRS 10年":"USD IRS 10Y","EUR IRS 10年":"EUR IRS 10Y","比特币(BTC)":"比特币","美国VIX恐慌指数":"美国VIX恐慌指数"},
}

# Yahoo Finance symbol mapping (table row name -> Yahoo symbol)
YAHOO_MAP = {
    "欧元/美元":"EURUSD=X","美元/日元":"JPY=X","英镑/美元":"GBPUSD=X","澳元/美元":"AUDUSD=X",
    "美元/瑞郎":"USDCHF=X","美元/加元":"USDCAD=X","新西兰元/美元":"NZDUSD=X","美元/港币":"USDHKD=X",
    "美元指数":"DX-Y.NYB","欧元/日元(交叉盘)":"EURJPY=X","英镑/日元(交叉盘)":"GBPJPY=X",
    "欧元/英镑(交叉盘)":"EURGBP=X","澳元/日元(交叉盘)":"AUDJPY=X",    "欧元/瑞郎(交叉盘)":"EURCHF=X",
    "英镑/澳元(交叉盘)":"GBPAUD=X","欧元/澳元(交叉盘)":"EURAUD=X","澳元/新西兰元(交叉盘)":"AUDNZD=X",
    "瑞郎/日元(交叉盘)":"CHFJPY=X","加元/日元(交叉盘)":"CADJPY=X","新西兰元/日元(交叉盘)":"NZDJPY=X",
    "现货黄金":"GC=F","现货白银":"SI=F","WTI原油":"CL=F","布伦特原油":"BZ=F","天然气":"NG=F",
    "道琼斯工业平均指数":"^DJI","标普500指数":"^GSPC","纳斯达克综合指数":"^IXIC",
    "罗素2000指数":"^RUT","欧洲斯托克50指数":"^STOXX50E","德国DAX30指数":"^GDAXI",
    "德国DAX30":"^GDAXI","法国CAC40指数":"^FCHI","英国富时100指数":"^FTSE",
    "意大利富时MIB指数":"^FTMIB","恒生指数":"^HSI","恒生科技指数":"^HSTECH",
    "日经225指数":"^N225","韩国KOSPI指数":"^KS11","澳大利亚ASX200指数":"^AXJO",
    "印度Sensex指数":"^BSESN","比特币":"BTC-USD","美国VIX恐慌指数":"^VIX",
}

# Live kline panels disabled: forex/commodities/indices charts now embed 2026 YTD daily data.
# Live quotes still refresh the tables via /api/quotes (name-based cell update).
LIVE_PANELS = {}

def cb(cid):
    return f"""<div class="chart-box"><div class="chart-toolbar" data-toolbar="{cid}">
<div class="toolbar-group"><button class="chart-btn active" data-tf="daily" onclick="switchTimeframe('{cid}','daily')">日线</button></div>
<div class="toolbar-sep"></div>
<div class="toolbar-group"><button class="chart-btn active" data-type="line" onclick="switchChartType('{cid}','line')">折线</button></div>
<div class="toolbar-sep"></div>
<button class="chart-btn" onclick="toggleAllSeries('{cid}')">全选/取消</button></div>
<div id="chart_{cid}" class="chart"></div>
<div class="note">折线图 · 日线数据 | 点击表格行高亮 | 悬停查看 | 滚轮缩放</div></div>"""

def cb_hist(cid):
    return f"""<div class="chart-box"><div class="chart-toolbar" data-toolbar="{cid}">
<div class="toolbar-group"><button class="chart-btn" onclick="toggleAllSeries('{cid}')">全选/取消</button></div>
<div class="toolbar-sep"></div>
<div class="toolbar-group"><span style="color:#8b949e;font-size:11px">&#9679; 2026年初至今 &#183; 日线收盘价</span></div>
</div>
<div id="chart_{cid}" class="chart"></div>
<div class="note">2026年初至今日线数据 (外汇=ECB参考汇率, 商品=新浪期货, 股指=东财) | 点击表格行高亮 | 悬停查看 | 滚轮缩放</div></div>"""

def sr(t):
    return f'<tr class="section-row"><td colspan="7">&#9656; {t}</td></tr>'

def clk(name, cid):
    sm = SMAP.get(cid, {})
    sn = sm.get(name, '')
    if not sn and cid == "ois_irs":
        # name is a tuple key for OIS/IRS
        sn = sm.get(name, '')
    return f' onclick="highlightSeries(\'{cid}\',\'{sn}\')" class="clickable-row"' if sn else ''

# Section grouping helpers
def group_by(items, key_fn):
    seen = []
    for it in items:
        k = key_fn(it)
        if k not in seen:
            seen.append(k)
    return [(k, [it for it in items if key_fn(it)==k]) for k in seen]

CSS = """*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI','Microsoft YaHei',sans-serif;background:#0d1117;color:#c9d1d9;min-height:100vh}
.header{background:linear-gradient(135deg,#1a1f35,#0d1117);padding:16px 30px;border-bottom:1px solid #30363d;display:flex;flex-direction:column;align-items:flex-start;gap:5px}
.header h1{font-size:22px;color:#58a6ff;font-weight:600;line-height:1.25}
.header .meta{font-size:13px;color:#8b949e}
.header .ver{font-size:11px;color:#f0883e;margin-left:8px;padding:2px 6px;border:1px solid #f0883e;border-radius:4px;vertical-align:middle}
.tabs{display:flex;background:#161b22;border-bottom:1px solid #30363d;overflow-x:auto;padding:0 10px;position:sticky;top:0;z-index:100}
@media(min-width:1200px){.tabs{padding-right:400px}}
.tab{padding:12px 18px;cursor:pointer;color:#8b949e;font-size:14px;white-space:nowrap;border-bottom:2px solid transparent;transition:all .2s}
.tab:hover{color:#c9d1d9;background:#21262d}.tab.active{color:#58a6ff;border-bottom-color:#58a6ff;font-weight:600}
.content{padding:20px 30px;max-width:1600px;margin:0 auto}
.panel{display:none}.panel.active{display:block}
.table-wrap{overflow-x:auto;margin-bottom:24px;border-radius:8px;border:1px solid #30363d}
table{width:100%;border-collapse:collapse;font-size:13px}
thead{background:#1c2333}th{padding:10px 12px;text-align:center;color:#8b949e;font-weight:600;border-bottom:1px solid #30363d;white-space:nowrap}
td{padding:8px 12px;text-align:center;border-bottom:1px solid #21262d}tr:hover{background:#161b22}
tr.section-row td{background:#1c2333;color:#58a6ff;font-weight:600;font-size:13px;text-align:left;padding:6px 12px}
tr.clickable-row{cursor:pointer;transition:background .15s}tr.clickable-row:hover{background:#1a2335}
.pos{color:#ff4d4f;font-weight:600}.neg{color:#52c41a;font-weight:600}.flat{color:#8b949e}
.tag-high{display:inline-block;padding:2px 8px;border-radius:4px;background:#ff4d4f;color:#fff;font-size:12px;font-weight:600}
.tag-mid{display:inline-block;padding:2px 8px;border-radius:4px;background:#faad14;color:#000;font-size:12px;font-weight:600}
.chart-box{background:#161b22;border-radius:8px;border:1px solid #30363d;padding:16px;margin-top:8px}
.chart-toolbar{display:flex;gap:8px;margin-bottom:10px;align-items:center;flex-wrap:wrap}
.toolbar-group{display:flex;gap:4px}.toolbar-sep{width:1px;height:24px;background:#30363d;margin:0 4px}
.chart-btn{padding:6px 14px;border:1px solid #30363d;background:#21262d;color:#8b949e;border-radius:6px;cursor:pointer;font-size:13px;transition:all .2s}
.chart-btn:hover{background:#30363d;color:#c9d1d9}.chart-btn.active{background:#1f6feb;color:#fff;border-color:#1f6feb;font-weight:600}
.chart{width:100%;height:450px}.note{font-size:12px;color:#8b949e;margin-top:8px;text-align:right}
.ac{background:#161b22;border-radius:8px;border:1px solid #30363d;padding:16px;margin-bottom:16px}
.ac .ct{font-size:15px;color:#58a6ff;font-weight:600;margin-bottom:8px}.ac .tt{font-size:14px;color:#e3b341;font-weight:600;margin-bottom:8px}
.ac .bd{font-size:13px;color:#c9d1d9;line-height:1.8}.ac .fo{font-size:12px;color:#f85149;margin-top:8px}
.anc{background:#1c1c2e;border-radius:8px;border-left:4px solid #ff4d4f;padding:14px;margin-bottom:12px}
.anc.med{border-left-color:#faad14}.anc .at{font-size:14px;font-weight:600;margin-bottom:6px;color:#e3b341}
.anc .ac2{font-size:12px;color:#8b949e;margin-bottom:6px}.anc .ad{font-size:13px;color:#c9d1d9;line-height:1.7;margin-bottom:6px}
.anc .ai{font-size:12px;color:#f85149;line-height:1.6}
.st{font-size:16px;color:#58a6ff;font-weight:600;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid #30363d}.sst{font-size:14px;color:#e3b341;font-weight:600;margin:18px 0 10px 0;padding-bottom:6px;border-bottom:1px dashed #30363d}
.cb-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:12px}
@media(max-width:980px){.cb-grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:600px){.cb-grid{grid-template-columns:1fr}}
.cb-card{background:#0d1117;border:1px solid #30363d;border-radius:8px;padding:12px 14px;min-width:0}
.cb-card-title{font-size:14px;color:#58a6ff;font-weight:600;margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid #30363d;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cb-card table{width:100%;border-collapse:collapse}
.cb-card th{font-size:11px;color:#8b949e;text-align:left;padding:4px 6px;border-bottom:1px solid #21262d}
.cb-card td{font-size:12px;padding:5px 6px;color:#c9d1d9}
.cb-card .cb-date{white-space:nowrap;color:#8b949e}
.cb-row-pub .cb-val{color:#7ee787;font-weight:600}
.cb-row-up .cb-val{color:#e3b341}
.cb-row-up .cb-date{color:#6e7681}
.cb-tag{font-size:10px;padding:1px 5px;border-radius:3px;margin-left:6px}
.cb-tag-pub{background:#1a3320;color:#7ee787}.cb-tag-up{background:#332d1a;color:#e3b341}
.co-note{font-size:12px;color:#e3b341;background:#1c2333;border:1px solid #30363d;border-left:3px solid #e3b341;border-radius:4px;padding:6px 12px;margin-bottom:14px;display:inline-block}
.sr2{display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap}
.sc{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:14px 20px;min-width:160px;flex:1}
.sc .lb{font-size:12px;color:#8b949e;margin-bottom:4px}.sc .vl{font-size:20px;font-weight:700}.sc .cg{font-size:13px;margin-top:2px}
.live-btn{padding:5px 11px;border:1px solid #30363d;background:#21262d;color:#c9d1d9;border-radius:6px;cursor:pointer;font-size:12px;transition:all .2s;display:flex;align-items:center;gap:5px}
.live-btn:hover{background:#30363d}.live-btn.active{background:#1f6feb;color:#fff;border-color:#1f6feb}
.live-btn.green{background:#238636;color:#fff;border-color:#238636}.live-btn.green:hover{background:#2ea043}
.live-dot{width:8px;height:8px;border-radius:50%;background:#52c41a;box-shadow:0 0 6px #52c41a;flex-shrink:0}
.live-dot.off{background:#f85149;box-shadow:0 0 6px #f85149}
.live-dot.loading{background:#faad14;animation:pulse 1s infinite}
.just-released{animation:flash 2s ease-out}
@keyframes flash{0%{background:#1f6feb33}100%{background:transparent}}
.src-badge{display:inline-block;padding:0 6px;margin-right:5px;border-radius:3px;font-size:10px;font-weight:700;letter-spacing:.3px;color:#0d1117;background:linear-gradient(90deg,#58a6ff,#3fb950);box-shadow:0 0 6px rgba(88,166,255,.35);vertical-align:1px;cursor:help}
.cal-live-note{font-size:12px;color:#7ee787;margin-top:6px;display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.cal-live-note .mini{font-size:10px;font-weight:700;padding:1px 5px;border-radius:3px;background:#1f6feb33;color:#58a6ff;border:1px solid #58a6ff55}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.3}}
.live-info{font-size:13px;color:#8b949e}.live-time{font-size:12px;color:#8b949e;margin-left:auto}
.live-spin{display:inline-block;width:14px;height:14px;border:2px solid #30363d;border-top-color:#58a6ff;border-radius:50%;animation:spin .6s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.live-controls{position:fixed;top:12px;right:14px;display:flex;gap:8px;align-items:center;background:rgba(22,27,34,0.96);border:1px solid #30363d;border-radius:8px;padding:6px 10px;z-index:999;box-shadow:0 4px 12px rgba(0,0,0,0.4);flex-wrap:wrap;max-width:min(520px,calc(100vw - 28px));justify-content:flex-end}
.live-info{font-size:12px;color:#8b949e;white-space:nowrap}
.live-time{font-size:11px;color:#6e7681;white-space:nowrap}
.loading-hint{font-size:12px;color:#6e7681;padding:10px 4px}
.rt-macro-block{background:#0a0e16;border:1px solid #1f6feb55;border-left:3px solid #58a6ff;border-radius:8px;padding:12px 14px;margin-bottom:14px;box-shadow:0 0 14px rgba(88,166,255,0.10)}
.news-list{display:flex;flex-direction:column;gap:10px}
.news-item{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 14px;transition:background .15s}
.news-item:hover{background:#1c2333}
.news-item a{color:#58a6ff;text-decoration:none;font-size:14px;font-weight:600;line-height:1.5;display:block;margin-bottom:6px}
.news-item a:hover{text-decoration:underline}
.news-meta{font-size:11px;color:#8b949e;display:flex;gap:12px;flex-wrap:wrap;margin-bottom:6px}
.news-source{background:#1f6feb22;color:#58a6ff;padding:1px 6px;border-radius:4px;font-size:11px}
.news-summary{font-size:12px;color:#c9d1d9;line-height:1.6}
.news-important{border-left:3px solid #f85149;background:rgba(248,81,73,0.06)}
.news-badge{background:#f85149;color:#fff;font-size:10px;padding:0 5px;border-radius:3px;margin-left:6px}
.news-loading{font-size:13px;color:#8b949e;padding:20px;text-align:center}
/* 新闻频道筛选（黄金/外汇/商品/原油为交易主线） */
.news-chan-bar{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}
.news-chan{cursor:pointer;font-size:12px;padding:3px 10px;border-radius:12px;border:1px solid #30363d;background:#161b22;color:#8b949e;transition:all .18s;user-select:none}
.news-chan:hover{border-color:#58a6ff;color:#58a6ff}
.news-chan.active{background:linear-gradient(135deg,#1f6feb,#388bfd);border-color:#58a6ff;color:#fff;box-shadow:0 0 8px rgba(88,166,255,.45)}
.news-chan-tag{font-size:10px;padding:1px 6px;border-radius:3px;margin-left:6px;font-weight:600}
.ct-gold{background:#f9c74f22;color:#f9c74f;border:1px solid #f9c74f55}
.ct-fx{background:#58a6ff22;color:#58a6ff;border:1px solid #58a6ff55}
.ct-comm{background:#52c41a22;color:#52c41a;border:1px solid #52c41a55}
.ct-oil{background:#ff7a4522;color:#ff7a45;border:1px solid #ff7a4555}
.ct-other{background:#8b949e22;color:#8b949e;border:1px solid #8b949e55}
.source-ok{color:#52c41a}.source-fail{color:#f85149}.source-warn{color:#faad14}
.data-source-tag{font-size:10px;padding:1px 5px;border-radius:3px;background:#21262d;color:#8b949e;margin-left:4px}
.source-status-bar{font-size:11px;color:#8b949e;display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.source-status-bar span{display:flex;align-items:center;gap:4px}
.rt-macro-title{font-size:13px;color:#58a6ff;font-weight:600;margin-bottom:10px;text-shadow:0 0 8px rgba(88,166,255,0.4)}
.rt-macro-block .sr2{margin-bottom:0}
.rt-macro-block .sc{background:#11161f;border-color:#1f6feb44}
.adv-tbl{width:100%;border-collapse:collapse;margin-top:8px;font-size:12px}
.adv-tbl th{text-align:left;color:#8b949e;font-weight:600;border-bottom:1px solid #30363d;padding:6px 8px}
.adv-tbl td{color:#c9d1d9;padding:5px 8px;border-bottom:1px solid #21262d}
.adv-tbl tr:hover td{background:#1c2330}
/* 进阶面板霓虹视觉（TIPS 利差 / 多国 EER 对比） */
.ac.neon-tips{border-color:#00f0ff55;box-shadow:0 0 18px rgba(0,240,255,.13),inset 0 0 22px rgba(0,240,255,.05)}
.ac.neon-tips .tt{color:#00f0ff;text-shadow:0 0 12px rgba(0,240,255,.6)}
.ac.neon-eer{border-color:#ff2d9555;box-shadow:0 0 18px rgba(255,45,149,.12),inset 0 0 22px rgba(255,45,149,.05)}
.ac.neon-eer .tt{color:#ff61d2;text-shadow:0 0 12px rgba(255,97,210,.55)}
.ac.neon-oil{border-color:#ff6b3555;box-shadow:0 0 18px rgba(255,107,53,.13),inset 0 0 22px rgba(255,107,53,.05)}
.ac.neon-oil .tt{color:#ffa940;text-shadow:0 0 12px rgba(255,169,64,.6)}
.ac.neon-usd{border-color:#4dabf755;box-shadow:0 0 18px rgba(77,171,247,.13),inset 0 0 22px rgba(77,171,247,.05)}
.ac.neon-usd .tt{color:#4dabf7;text-shadow:0 0 12px rgba(77,171,247,.6)}"""

# ===================== Build HTML =====================
H = []
H.append(f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>全球金融信息日报 V9 {DATE}</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>{CSS}</style></head><body>
<div class="header"><h1>全球金融信息日报<span class="ver">V9</span></h1>
<div class="meta">数据日期: <span id="headerDataDate">{DATE}</span> | 行情更新: <b id="headerCutoff" style="color:#e3b341">{CUTOFF}</b> | 网络当前时间: <b id="networkTime" style="color:#7ee787">--</b></div></div>
<div class="tabs" id="tabs">
<div class="tab active" data-panel="overview">全球概览</div>
<div class="tab" data-panel="forex">外汇</div><div class="tab" data-panel="commodities">大宗商品</div>
<div class="tab" data-panel="bonds">债券</div><div class="tab" data-panel="ois_irs">利率掉期</div>
<div class="tab" data-panel="indices">股指</div><div class="tab" data-panel="econ">财经日历</div>
<div class="tab" data-panel="cb">央行动态</div><div class="tab" data-panel="analysis">走势分析</div>
<div class="tab" data-panel="macro">宏观数据</div><div class="tab" data-panel="anomaly">重点提示</div>
<div class="tab" data-panel="news">实时新闻</div>
<div class="tab" data-panel="advanced">进阶数据</div>
</div><div class="content">''')
H.append('<div class="live-controls" id="liveControls">')
H.append('<button class="live-btn" id="autoUpdateBtn" onclick="toggleAutoUpdate()"><span class="live-dot off" id="liveDot"></span><span id="autoBtnText">自动更新(5分钟)</span></button>')
H.append('<button class="live-btn green" onclick="manualUpdate()">&#x21bb; 手动更新</button>')
H.append('<span class="live-info" id="liveStatus">&#9889; 检查服务器连接...</span>')
H.append('<span class="live-time" id="lastUpdateTime">尚未更新</span>')
H.append('</div>')
H.append('<div class="source-status-bar" id="quoteSourceStatus" style="background:rgba(22,27,34,0.92);border:1px solid #30363d;border-radius:6px;padding:6px 12px;margin:8px 0 4px 0;">行情源: 等待刷新...</div>')

# Overview
H.append('<div class="panel active" id="panel-overview">')
H.append('<div class="st">所有品类关键数据一览</div>')
H.append(co())
H.append('<div class="sr2">')
for lb,vl,col,cg in D.get("stat_cards",[]):
    H.append(f'<div class="sc" data-label="{lb}"><div class="lb">{lb}</div><div class="vl" style="color:{col}">{vl}</div><div class="cg {("pos" if "+" in cg else "neg" if "-" in cg else "")}">{cg}</div></div>')
H.append('</div>')
H.append('<div class="table-wrap"><table><thead><tr><th>类别</th><th>品种</th><th>价格/收益率</th><th>日涨跌幅(%)</th><th>备注</th></tr></thead><tbody>')
ov_secs = group_by(D["overview_items"], lambda x: x[0])
for sec_t, sec_items in ov_secs:
    H.append(sr(sec_t))
    for cat,name,price,chg,note in sec_items:
        H.append(f'<tr><td>{cat}</td><td style="text-align:left">{name}</td><td>{fn(price,4)}</td><td>{fc(chg)}</td><td style="color:#8b949e;font-size:12px;text-align:left">{note}</td></tr>')
H.append('</tbody></table></div>')
H.append('</div>')

# Forex
H.append('<div class="panel" id="panel-forex">')
H.append('<div class="st">外汇市场行情 (含交叉盘货币)</div>')
H.append(co())
H.append('<div class="table-wrap"><table><thead><tr><th>品种(中文)</th><th>代码</th><th>汇率/价格</th><th>日变化(%)</th><th>方向</th><th>分析备注</th></tr></thead><tbody>')
fx_main = [x for x in D["forex_data"] if "交叉盘" not in x[0]]
fx_cross = [x for x in D["forex_data"] if "交叉盘" in x[0]]
H.append(sr("主要货币对"))
for name,code,price,chg,note in fx_main:
    H.append(f'<tr{clk(name,"forex")}><td style="text-align:left">{name}</td><td>{code}</td><td>{fn(price,4)}</td><td>{fc(chg)}</td><td>{fa(chg)}</td><td style="color:#8b949e;font-size:12px;text-align:left">{note}</td></tr>')
H.append(sr("交叉盘货币"))
for name,code,price,chg,note in fx_cross:
    H.append(f'<tr{clk(name,"forex")}><td style="text-align:left">{name}</td><td>{code}</td><td>{fn(price,4)}</td><td>{fc(chg)}</td><td>{fa(chg)}</td><td style="color:#8b949e;font-size:12px;text-align:left">{note}</td></tr>')
H.append('</tbody></table></div>')
H.append(cb_hist("forex"))
H.append('</div>')

# Commodities
H.append('<div class="panel" id="panel-commodities">')
H.append('<div class="st">大宗商品行情</div>')
H.append(co())
H.append('<div class="table-wrap"><table><thead><tr><th>品种</th><th>代码</th><th>价格</th><th>涨跌幅(%)</th><th>单位</th><th>走势</th><th>分析备注</th></tr></thead><tbody>')
for name,code,price,chg,unit,note in D["commodity_data"]:
    d = "&#9650; 涨" if chg>0 else "&#9660; 跌" if chg<0 else "&#9670; 平"
    cl = "pos" if chg>0 else "neg" if chg<0 else "flat"
    H.append(f'<tr{clk(name,"commodities")}><td style="text-align:left">{name}</td><td>{code}</td><td>{fn(price,2)}</td><td>{fc(chg)}</td><td>{unit}</td><td class="{cl}">{d}</td><td style="color:#8b949e;font-size:12px;text-align:left">{note}</td></tr>')
H.append('</tbody></table></div>')
H.append(cb_hist("commodities"))
H.append('</div>')

# Bonds
H.append('<div class="panel" id="panel-bonds">')
H.append('<div class="st">主要国债收益率 (%)</div>')
H.append(co())
H.append('<div class="table-wrap"><table><thead><tr><th>国债品种</th><th>代码</th><th>收益率(%)</th><th>日变化(bp)</th><th>走势</th></tr></thead><tbody>')
bd_secs = group_by(D["bond_data"], lambda x: x[1].split()[0])
for sec_t, sec_items in bd_secs:
    cn_map = {"US":"美国","DE":"德国","UK":"英国","FR":"法国","IT":"意大利","JP":"日本","AU":"澳大利亚"}
    H.append(sr(cn_map.get(sec_t, sec_t)))
    for name,code,yv,chg in sec_items:
        d = "&#9650; 上行" if chg>0 else "&#9660; 下行" if chg<0 else "&#9670; 持平"
        cl = "pos" if chg>0 else "neg" if chg<0 else "flat"
        H.append(f'<tr{clk(name,"bonds")}><td style="text-align:left">{name}</td><td>{code}</td><td>{fn(yv,4)}</td><td>{fc(chg)}</td><td class="{cl}">{d}</td></tr>')
H.append('</tbody></table></div>')
H.append(cb("bonds"))
H.append('</div>')

# OIS & IRS
H.append('<div class="panel" id="panel-ois_irs">')
H.append('<div class="st">OIS利率掉期 &amp; IRS利率互换</div>')
H.append(co())
H.append('<div class="table-wrap"><table><thead><tr><th>利率类型</th><th>期限</th><th>利率(%)</th><th>日变化(bp)</th><th>备注</th></tr></thead><tbody>')
ois_secs = group_by(D["ois_irs_data"], lambda x: x[0].split()[0] if " " in x[0] else x[0])
cat_map = {"SOFR":"基准利率","ESTR":"基准利率","SONIA":"基准利率","TONA":"基准利率","Fed":"基准利率","USD":"美元 (USD)","EUR":"欧元 (EUR)","GBP":"英镑 (GBP)","JPY":"日元 (JPY)"}
for sec_t, sec_items in ois_secs:
    H.append(sr(cat_map.get(sec_t, sec_t)))
    for typ,term,rate,chg,note in sec_items:
        key = (typ, term)
        sm = SMAP.get("ois_irs", {})
        sn = sm.get(key, '')
        oc = f' onclick="highlightSeries(\'ois_irs\',\'{sn}\')" class="clickable-row"' if sn else ''
        H.append(f'<tr{oc}><td style="font-weight:600;color:#58a6ff;text-align:left">{typ}</td><td>{term}</td><td>{fn(rate,4)}</td><td>{fc(chg)}</td><td style="color:#8b949e;font-size:12px;text-align:left">{note}</td></tr>')
H.append('</tbody></table></div>')
H.append(cb("ois_irs"))
H.append('</div>')

# Indices
H.append('<div class="panel" id="panel-indices">')
H.append('<div class="st">全球股指行情</div>')
H.append(co())
H.append('<div class="table-wrap"><table><thead><tr><th>指数名称</th><th>代码</th><th>收盘价</th><th>涨跌幅(%)</th><th>涨跌</th><th>市场</th><th>分析备注</th></tr></thead><tbody>')
mkt_map = {"美洲":["美国"],"欧洲":["欧洲","德国","法国","英国","意大利"],"亚太":["中国","中国香港","日本","韩国","澳大利亚","印度"]}
for sec_t, countries in mkt_map.items():
    sec_items = [x for x in D["index_data"] if x[4] in countries]
    if sec_items:
        H.append(sr(sec_t))
        for name,code,close,chg,market,note in sec_items:
            H.append(f'<tr{clk(name,"indices")}><td style="text-align:left">{name}</td><td>{code}</td><td>{fn(close,2)}</td><td>{fc(chg)}</td><td>{fa(chg)}</td><td>{market}</td><td style="color:#8b949e;font-size:12px;text-align:left">{note}</td></tr>')
H.append('</tbody></table></div>')
H.append(cb_hist("indices"))
H.append('</div>')

# Economic Calendar
H.append('<div class="panel" id="panel-econ">')
cal = D.get("economic_calendar", {})
prev_d = cal.get("prev_date", "")
curr_d = cal.get("curr_date", "")
H.append('<div class="st">财经日历</div>')

# Three-way dynamic classification by REAL current date (must match live_server.py)
_now = datetime.now()
_today = _now
_monday = _today - timedelta(days=_today.weekday())
_sunday = _monday + timedelta(days=6)
def _cal_event_dt(ev_time):
    try:
        return datetime.strptime(f"{_now.year}-{ev_time}", "%Y-%m-%d %H:%M")
    except Exception:
        return None
_cal_today, _cal_week, _cal_future = [], [], []
def _cal_emit(it):
    tstr = it.get("time", "")
    if "待定" in tstr:
        _cal_future.append(it); return
    dt = _cal_event_dt(tstr)
    if not dt:
        _cal_future.append(it); return
    published = dt <= _now
    d0 = dt.date()
    if published:
        if d0 == _today.date():
            _cal_today.append(it); _cal_week.append(it)
        elif _monday.date() <= d0 <= _sunday.date():
            _cal_week.append(it)
        elif d0 > _today.date():
            _cal_future.append(it)
        else:
            _cal_week.append(it)
    else:
        _cal_future.append(it)
for it in cal.get("released", []):
    _cal_emit(it)
for it in cal.get("upcoming", []):
    _cal_emit(it)
# 排序: 当日升序 / 当周已公布倒序(最近优先) / 待公布升序
def _cal_ts(it):
    dt = _cal_event_dt(it.get("time", ""))
    return dt.timestamp() if dt else 1e18
_cal_today.sort(key=_cal_ts)
_cal_future.sort(key=_cal_ts)
_cal_week.sort(key=lambda it: -_cal_ts(it))

def _cal_table(sec_id, title, color):
    H.append(f'<div class="st" style="margin-top:20px;color:{color}">{title}</div>')
    H.append(f'<div class="table-wrap"><table><thead><tr><th>时间</th><th>国家</th><th>事件</th><th>实际值</th><th>预测值</th><th>前值</th><th>影响</th><th>备注</th></tr></thead><tbody id="cal-tbody-{sec_id}"></tbody></table></div>')

H.append(f'<div class="co-note">&#128197; 待公布=未到公布时间(含今日待公布) | 当日=今日已公布 | 当周已公布=本周(周一至周日)已公布·最近优先 | &#9851; 手动/自动更新时按真实北京时间归类并取数</div>')
H.append(f'<div id="calLiveNote" class="cal-live-note" style="display:none"></div>')
# Section 1: 待公布数据 (未到公布时间)
_cal_table("future", '&#9660; 待公布数据 (未到公布时间)', "#f0883e")
# Section 2: 当日已公布数据
_cal_table("today", f'&#9650;&#9660; 当日已公布数据 (<span id="calTodayDate">{_now.strftime("%Y-%m-%d")}</span>)', "#58a6ff")
# Section 3: 当周已公布数据 (Monday..Sunday, 最近优先)
_cal_table("week", '&#9650; 当周已公布数据 (最近优先)', "#7ee787")
# Calendar chart container (custom, replaces standard cb("econ"))
future_n, today_n, week_n = len(_cal_future), len(_cal_today), len(_cal_week)
H.append(f'''<div class="chart-box"><div class="chart-toolbar" data-toolbar="econ">
<div class="toolbar-group"><button class="chart-btn active" data-cal-type="bar" onclick="switchCalendarType('econ','bar')">柱状图 (实际/预测/前值)</button>
<button class="chart-btn" data-cal-type="line" onclick="switchCalendarType('econ','line')">折线图 (2026 YTD)</button></div>
<div class="toolbar-sep"></div>
<div class="toolbar-group" data-cal-section-group>
<button class="chart-btn active" data-cal-section="all" onclick="switchCalendarSection('econ','all')">全部 ({future_n+today_n+week_n})</button>
<button class="chart-btn" data-cal-section="today" onclick="switchCalendarSection('econ','today')">当日 ({today_n})</button>
<button class="chart-btn" data-cal-section="week" onclick="switchCalendarSection('econ','week')">已公布 ({week_n})</button>
<button class="chart-btn" data-cal-section="future" onclick="switchCalendarSection('econ','future')">待公布 ({future_n})</button>
</div>
<div class="toolbar-sep"></div>
<div class="toolbar-group"><button class="chart-btn" data-cal-toggle="all" onclick="toggleCalendarSeries('econ')">全选/取消</button></div>
<div class="toolbar-sep"></div>
<div class="toolbar-group"><span style="color:#8b949e;font-size:11px">&#9679; 红=超预期 &#9679; 绿=低于预期 &#9679; 灰=待公布</span></div>
</div>
<div id="chart_econ" class="chart"></div>
<div class="note">柱状图=各次公布对比 | 折线图=有历史数据的指标YTD趋势 | 点击图例可单独切换 | 全选/取消一键切换</div></div>''')
H.append('</div>')

# Central Banks
H.append('<div class="panel" id="panel-cb">')
H.append('<div class="st">主要央行政策动态</div>')
# split into rate decisions and speeches; drop BI from rate decision list
_speech_keys = ("讲话", "演讲", "Jackson Hole")
_speech_srcs = ("Jackson Hole", "央行日程")
rate_rows = []
speech_rows = []
for row in D["central_bank_data"]:
    cbi, core, detail, src, note = row
    is_speech = any(k in core for k in _speech_keys) or src in _speech_srcs
    if is_speech:
        speech_rows.append(row)
    elif "印尼央行" not in cbi:
        rate_rows.append(row)

# 1. latest rate decisions
H.append('<div class="sst">央行的最近一次利率决议</div>')
H.append('<div class="table-wrap"><table><thead><tr><th>央行</th><th>核心动态</th><th>详细内容</th><th>信息来源</th><th>备注</th></tr></thead><tbody>')
for cbi,core,detail,src,note in rate_rows:
    H.append(f'<tr><td style="font-weight:600;color:#58a6ff;white-space:nowrap">{cbi}</td><td style="font-weight:600;text-align:left">{core}</td><td style="font-size:12px;text-align:left;color:#c9d1d9;line-height:1.6">{detail}</td><td style="font-size:12px">{src}</td><td style="font-size:12px;text-align:left">{note}</td></tr>')
H.append('</tbody></table></div>')

# 2. central bank officials' signals
H.append('<div class="sst">央行官员释放信息</div>')
H.append('<div class="table-wrap"><table><thead><tr><th>央行</th><th>事件</th><th>详细内容</th><th>信息来源</th><th>备注</th></tr></thead><tbody>')
for cbi,core,detail,src,note in speech_rows:
    H.append(f'<tr><td style="font-weight:600;color:#58a6ff;white-space:nowrap">{cbi}</td><td style="font-weight:600;text-align:left">{core}</td><td style="font-size:12px;text-align:left;color:#c9d1d9;line-height:1.6">{detail}</td><td style="font-size:12px">{src}</td><td style="font-size:12px;text-align:left">{note}</td></tr>')
H.append('</tbody></table></div>')

# 3. 各央行 2026 年利率决议小模块（3列网格，含已发布+待发布）
_cb_timeline = D.get("central_bank_timeline", {})
if _cb_timeline:
    H.append('<div class="sst">2026年利率决议安排（已发布 / 待发布）</div>')
    H.append('<div class="cb-grid">')
    for bn, items in _cb_timeline.items():
        H.append(f'<div class="cb-card"><div class="cb-card-title">{bn}</div>')
        H.append('<table><thead><tr><th>日期</th><th>利率</th><th>变动</th></tr></thead><tbody>')
        for it in items:
            if it.get("status") == "published":
                row_cls = "cb-row-pub"
                tag = '<span class="cb-tag cb-tag-pub">已发布</span>'
                val = it.get("rate", "-")
            else:
                row_cls = "cb-row-up"
                tag = '<span class="cb-tag cb-tag-up">待发布</span>'
                val = it.get("rate", "待发布")
            H.append(f'<tr class="{row_cls}"><td class="cb-date">{it.get("date","")}</td><td class="cb-val">{val}</td><td>{it.get("change","")}{tag}</td></tr>')
        H.append('</tbody></table></div>')
    H.append('</div>')

# 4. 实时宏观数据 (BIS 央行政策利率 + World Bank GDP/CPI) -- 点击刷新取最新
H.append('<div class="sst">实时宏观数据 <span style="font-size:12px;color:#8b949e">（BIS 央行政策利率 + World Bank GDP/CPI · 点击「刷新实时宏观」取最新值）</span></div>')
H.append('<div style="margin:6px 0 10px;display:flex;align-items:center;gap:10px;flex-wrap:wrap">'
         '<button class="live-btn green" onclick="fetchMacro()">&#x21bb; 刷新实时宏观</button>'
         '<span class="live-time" id="macroFetchedAt" style="margin-left:0">尚未获取（离线时显示下方静态快照）</span></div>')
H.append('<div class="rt-macro-block"><div class="rt-macro-title">&#9670; 主要央行政策利率 (美联储/欧央/英/日/澳/韩 · BIS WS_CBPOL)</div>'
         '<div class="sr2" id="macroPolicyRates"><div class="loading-hint">点击上方「刷新实时宏观」获取 BIS 主要央行政策利率实时数据…</div></div></div>')
H.append('<div class="rt-macro-block"><div class="rt-macro-title">&#9670; GDP 年增速 % (World Bank · 最新公布)</div>'
         '<div class="sr2" id="macroGdp"><div class="loading-hint">…</div></div></div>')
H.append('<div class="rt-macro-block"><div class="rt-macro-title">&#9670; CPI 月度同比 % (BIS WS_LONG_CPI · 最新月份)</div>'
         '<div class="sr2" id="macroCpi"><div class="loading-hint">…</div></div></div>')

H.append(cb("cb"))
H.append('</div>')

# Analysis
H.append('<div class="panel" id="panel-analysis">')
H.append('<div class="st">金融产品走势分析</div>')
for cat,ttl,body,focus in D["analysis_data"]:
    H.append(f'<div class="ac"><div class="ct">{cat}</div><div class="tt">{ttl}</div><div class="bd">{body}</div><div class="fo">&#9888; {focus}</div></div>')
H.append(cb("analysis"))
H.append('</div>')

# Macro
H.append('<div class="panel" id="panel-macro">')
H.append('<div class="st">宏观金融指标 (含OIS/IRS)</div>')
H.append(co())
H.append('<div class="table-wrap"><table><thead><tr><th>指标名称</th><th>数值</th><th>日变化</th><th>单位</th><th>备注</th></tr></thead><tbody>')
for name,value,chg,unit,note in D["macro_data"]:
    H.append(f'<tr{clk(name,"macro")}><td style="text-align:left">{name}</td><td style="font-weight:600">{fn(value,4)}</td><td>{fc(chg)}</td><td>{unit}</td><td style="color:#8b949e;font-size:12px;text-align:left">{note}</td></tr>')
H.append('</tbody></table></div>')
H.append(cb("macro"))
H.append('</div>')

# Anomaly
H.append('<div class="panel" id="panel-anomaly">')
H.append('<div class="st">&#9888; 重点提示</div>')
H.append('<div class="tt" style="margin-top:6px">&#9660; 重点提示详情</div>')
_LEVEL_RANK = {"极高":5,"高":4,"中高":3,"中":2,"低":1,"":0}
anomaly_sorted = sorted(D["anomaly_data"], key=lambda x: _LEVEL_RANK.get(x[4],0), reverse=True)
for title,cat,detail,impact,level in anomaly_sorted:
    cls = "anc" if level=="极高" else "anc med"
    tag = f'<span class="tag-high">{level}</span>' if level=="极高" else f'<span class="tag-mid">{level}</span>'
    H.append(f'<div class="{cls}"><div class="at">{title} {tag}</div><div class="ac2">类别: {cat}</div><div class="ad">{detail}</div><div class="ai"><strong>影响评估:</strong> {impact}</div></div>')
H.append('</div>')

# Real-time News
H.append('<div class="panel" id="panel-news">')
H.append('<div class="st">&#128240; 实时财经新闻 (多源聚合)</div>')
H.append('<div class="bd" style="margin-bottom:10px">来源: 华尔街见闻(黄金/外汇/商品/原油多频道快讯 + 深度 + 热文) / 金十数据 / 东方财富 / 新浪财经 | 点击标题可跳转原文（路透因网络限制暂未接入）</div>')
H.append('<div id="newsSourceStatus" style="margin-bottom:8px;font-size:12px;color:#8b949e"></div>')
H.append('<div id="newsChannelBar" class="news-chan-bar"></div>')
H.append('<div id="newsList" class="news-list"><div class="loading">正在加载新闻...</div></div>')
H.append('</div>')

# ===================== Advanced data =====================
# Chart data extraction (used both by panel HTML and JS init)
_adv_tips = D.get("tips_breakeven", {}) or {}
_adv_tips_df = (_adv_tips.get("dfii10", {}) or {}).get("series", [])
_adv_tips_ie = (_adv_tips.get("t10yie", {}) or {}).get("series", [])
_adv_tips_n = min(len(_adv_tips_df), len(_adv_tips_ie))
_adv_tips_labels = [d for d, _ in _adv_tips_df[-_adv_tips_n:]] if _adv_tips_n else []
_adv_tips_vals = {
    "TIPS实际收益率(DFII10)": [round(v, 2) for _, v in _adv_tips_df[-_adv_tips_n:]],
    "盈亏平衡通胀(T10YIE)": [round(v, 2) for _, v in _adv_tips_ie[-_adv_tips_n:]],
} if _adv_tips_n else {}
_adv_eer = D.get("eer_series", {}) or {}
_adv_eer_labels = _adv_eer.get("labels", [])
_adv_eer_vals = {k: v for k, v in _adv_eer.items() if k != "labels"}
_adv_oil = D.get("chart_adv_oil", {}) or {}
_adv_oil_labels = _adv_oil.get("labels", [])
_adv_oil_vals = {k: v for k, v in _adv_oil.items() if k != "labels"}

H.append('<div class="panel" id="panel-advanced">')
H.append('<div class="sst">进阶数据实时 <span style="font-size:12px;color:#8b949e">（FRED TIPS/原油/美元指数 + BIS有效汇率 · 点击「刷新进阶数据」取最新值）</span></div>')
H.append('<div style="margin:10px 0">')
H.append('  <button class="live-btn green" onclick="fetchAdvanced()">&#x21bb; 刷新进阶数据</button>')
H.append('  <span class="live-time" id="advFetchedAt" style="margin-left:0">尚未获取（离线时显示下方静态快照）</span></div>')
# 以下容器由 JS fetchAdvanced() 实时填充（实时块显示徽标，快照块标注更新时间）
H.append('<div id="advTips" class="ac neon-tips"><div class="loading-hint">点击「刷新进阶数据」获取实时 TIPS / 原油 / 美元指数 / BIS有效汇率…</div></div>')
H.append('<div id="advOil" class="ac neon-oil"></div>')
H.append('<div id="advUsd" class="ac neon-usd"></div>')
H.append('<div id="advEer" class="ac neon-eer"></div>')
H.append('<div id="advCpi" class="ac neon-cpi"></div>')
H.append('<div id="advUnemployment" class="ac neon-un"></div>')
H.append('<div id="advDxyIbs" class="ac"></div>')
H.append('<div id="advFxSwap" class="ac"></div>')
H.append('<div id="advCofer" class="ac"></div>')
H.append('<div id="advCot" class="ac"></div>')
H.append('<div id="advCbGold" class="ac"></div>')
H.append('<div id="advEtf" class="ac"></div>')
H.append('<div id="advGoldDemand" class="ac"></div>')
H.append('<div id="advEiaOil" class="ac"></div>')
H.append('<div id="advEiaIea" class="ac"></div>')
H.append('</div>')

# ---- JS ----
H.append('</div>\n<script>')
JS = r"""
var echartsInstances={},chartDataStore={},chartTimeframe={},chartChartType={},highlightedSeries={};
var COLORS=__COLORS__;
function genTF(vals,tf){
var lb=[],vb=[];
for(var m=0;m<vals.length-1;m++){for(var d=0;d<20;d++){var t=d/20;var v=vals[m]+(vals[m+1]-vals[m])*t;
v+=Math.sin(d*0.7+m*1.3)*Math.abs(vals[m+1]-vals[m])*0.15;vb.push(parseFloat(v.toFixed(4)));lb.push((m+1)+"/"+(d+1));}}
vb.push(vals[vals.length-1]);lb.push("最新");return{labels:lb,values:vb};}
function initChart(cid,title,sd){var names=Object.keys(sd);var vals=names.map(function(n){return sd[n];});
chartDataStore[cid]={title:title,names:names,values:vals,colors:COLORS};
chartTimeframe[cid]='daily';chartChartType[cid]='line';renderChart(cid);}
function initHistChart(cid,title,dates,seriesMap){var names=Object.keys(seriesMap);var vals=names.map(function(n){return seriesMap[n];});
chartDataStore[cid]={title:title,names:names,values:vals,dates:dates,histMode:true,colors:COLORS};
chartTimeframe[cid]='daily';chartChartType[cid]='line';renderChart(cid);}
function renderChart(cid){var d=chartDataStore[cid];if(!d)return;
var tf=chartTimeframe[cid]||'daily';var tfLabels=null;var series=[];
if(d.histMode&&d.dates){
  tfLabels=d.dates;
  d.names.forEach(function(name,idx){series.push({name:name,type:'line',data:d.values[idx],smooth:true,symbol:'none',connectNulls:true,lineStyle:{width:1.6}});});
}else{
  d.names.forEach(function(name,idx){var td=genTF(d.values[idx],tf);if(!tfLabels)tfLabels=td.labels;var vs=td.values;
  series.push({name:name,type:'line',data:vs,smooth:true,symbol:'none',lineStyle:{width:2}});});}
var option={title:{text:d.title,textStyle:{color:'#58a6ff',fontSize:14}},
tooltip:{trigger:'axis',backgroundColor:'rgba(22,27,34,0.95)',borderColor:'#30363d',textStyle:{color:'#c9d1d9'}},
legend:{data:d.names,textStyle:{color:'#8b949e',fontSize:11},top:30,type:'scroll'},
grid:{left:'8%',right:'12%',bottom:'15%',top:80},
dataZoom:[{type:'slider',xAxisIndex:0,bottom:10,height:20,backgroundColor:'#161b22',fillerColor:'#30363d',textStyle:{color:'#8b949e'}},{type:'inside',xAxisIndex:0}],
xAxis:{type:'category',data:tfLabels,axisLine:{lineStyle:{color:'#30363d'}},axisLabel:{color:'#8b949e'}},
yAxis:{type:'value',scale:true,axisLine:{lineStyle:{color:'#30363d'}},axisLabel:{color:'#8b949e'},splitLine:{lineStyle:{color:'#21262d'}}},
series:series,color:d.colors};
if(!echartsInstances[cid]){echartsInstances[cid]=echarts.init(document.getElementById('chart_'+cid));}
echartsInstances[cid].setOption(option,true);
if(highlightedSeries[cid]){var sel={};d.names.forEach(function(n){sel[n]=(n===highlightedSeries[cid]);});
echartsInstances[cid].setOption({legend:{selected:sel}});}}
function switchTimeframe(cid,tf){chartTimeframe[cid]=tf;
var tb=document.querySelector('[data-toolbar="'+cid+'"]');if(tb)tb.querySelectorAll('[data-tf]').forEach(function(b){b.classList.toggle('active',b.dataset.tf===tf);});
if(livePanels[cid]&&serverOnline){loadLiveKline(cid,tf);}else{renderChart(cid);}}
function switchChartType(cid,type){chartChartType[cid]=type;
var tb=document.querySelector('[data-toolbar="'+cid+'"]');if(tb)tb.querySelectorAll('[data-type]').forEach(function(b){b.classList.toggle('active',b.dataset.type===type);});
if(chartDataStore[cid]&&chartDataStore[cid].liveKline&&Object.keys(chartDataStore[cid].liveKline).length>0&&serverOnline){renderLiveChart(cid);}else{renderChart(cid);}}
function toggleAllSeries(cid){var chart=echartsInstances[cid];if(!chart)return;
var opt=chart.getOption();var ld=opt.legend[0].data;var sel=opt.legend[0].selected||{};
var allOn=ld.every(function(n){return sel[n]!==false;});var ns={};ld.forEach(function(n){ns[n]=!allOn;});
chart.setOption({legend:{selected:ns}});}
function highlightSeries(cid,sn){if(highlightedSeries[cid]===sn){highlightedSeries[cid]=null;
var d=chartDataStore[cid];var sel={};d.names.forEach(function(n){sel[n]=true;});
echartsInstances[cid].setOption({legend:{selected:sel}});}else{highlightedSeries[cid]=sn;if(chartDataStore[cid]&&chartDataStore[cid].liveKline&&Object.keys(chartDataStore[cid].liveKline).length>0&&serverOnline){renderLiveChart(cid);}else{renderChart(cid);}}}
document.querySelectorAll('.tab').forEach(function(tab){tab.addEventListener('click',function(){
document.querySelectorAll('.tab').forEach(function(t){t.classList.remove('active');});
document.querySelectorAll('.panel').forEach(function(p){p.classList.remove('active');});
tab.classList.add('active');document.getElementById('panel-'+tab.dataset.panel).classList.add('active');
setTimeout(function(){
Object.values(echartsInstances).forEach(function(c){if(c)c.resize();});
},120);});});
window.addEventListener('resize',function(){Object.values(echartsInstances).forEach(function(c){if(c)c.resize();});});
var livePanels=__LIVE_PANELS__;
var serverOnline=false;var autoTimer=null;
// Live data always comes from the local real-time server on port 8800,
// regardless of whether the HTML is opened as file:// or served from another port.
// 防御: ECharts CDN 未加载(离线/网络/被墙)时, 用 no-op stub 避免 echarts.init 抛错中断整个脚本(否则财经日历等后续初始化不执行)
if(typeof echarts==='undefined'){window.echarts={init:function(){return {setOption:function(){},resize:function(){},dispose:function(){},showLoading:function(){},hideLoading:function(){},on:function(){},off:function(){}};}};}
// 实时数据服务器默认运行在 localhost:8800。无论本页面通过 file://、静态预览
// 还是由 live_server 自身托管打开, 都优先连 localhost:8800, 保证"实时刷新"永远可用。
(function(){
  var cands=[];
  if(window.location.protocol!=='file:') cands.push(window.location.origin); // 当前源(若就是 live_server)
  cands.push('http://localhost:8800');
  cands.push('http://127.0.0.1:8800');
  window._BASE_CANDIDATES=cands;
})();
var BASE=window._BASE_CANDIDATES[0];
var _offlineRetryTimer=null;
function showOfflineBanner(show){
  var b=document.getElementById('offlineBanner');
  if(show){
    if(!b){
      b=document.createElement('div');
      b.id='offlineBanner';
      b.style.cssText='position:fixed;left:50%;top:64px;transform:translateX(-50%);z-index:1000;background:#3d2a00;border:1px solid #e3b341;color:#ffd666;padding:10px 16px;border-radius:8px;font-size:13px;max-width:92vw;text-align:center;box-shadow:0 6px 18px rgba(0,0,0,0.5)';
      b.innerHTML='&#9888; 实时数据服务器未连接 / 缓存旧页面。请先关闭旧 APP 窗口，再双击运行 <b>启动全球金融日报APP.bat</b>；'+
        '然后在浏览器地址栏输入 <a href="http://localhost:8800/" target="_blank" style="color:#7ee787;text-decoration:underline">http://localhost:8800/</a> '+
        '(不要使用预览链接或双击 HTML 文件)。若仍显示旧数据，按 <b>Ctrl+F5</b> 强制刷新。'+
        '（下方静态行情与图表仍正常显示，连上后会自动刷新为实时数据）';
      document.body.appendChild(b);
    }
  } else if(b){ b.remove(); }
}
function checkServer(){
  var cands=window._BASE_CANDIDATES, idx=0, ctl=null;
  function tryNext(){
    if(idx>=cands.length){
      serverOnline=false;
      document.getElementById('liveStatus').innerHTML='&#9888; 服务器离线 - 请运行 启动全球金融日报APP.bat';
      document.getElementById('liveDot').classList.add('off');
      showOfflineBanner(true);
      // 离线时每 10s 自动重试, 启动服务器后自动恢复
      if(!_offlineRetryTimer) _offlineRetryTimer=setInterval(function(){if(!serverOnline)checkServer();},10000);
      return;
    }
    var base=cands[idx++];
    if(ctl)try{ctl.abort();}catch(e){}
    ctl=new AbortController();
    var timer=setTimeout(function(){try{ctl.abort();}catch(e){}},8000);
    fetch(base+'/api/status',{cache:'no-store',signal:ctl.signal}).then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(d){
      clearTimeout(timer);
      BASE=base;
      if(_offlineRetryTimer){clearInterval(_offlineRetryTimer);_offlineRetryTimer=null;}
      serverOnline=true;
      showOfflineBanner(false);
      var dataDate=d.data_date||'';
      document.getElementById('liveStatus').innerHTML='&#9989; 服务器在线 ('+d.symbols+'个品种)'+(dataDate?' · 数据日期:'+dataDate:'');
      document.getElementById('liveDot').classList.remove('off');
      var hd=document.getElementById('headerDataDate'); if(hd && dataDate && hd.textContent!==dataDate) hd.textContent=dataDate;
      doFullUpdate();
    }).catch(function(e){ clearTimeout(timer); tryNext(); });
  }
  tryNext();
}
function fetchNetworkTime(){if(!serverOnline)return;_fetchJSON('ntime',BASE+'/api/time',8000).then(function(d){var el=document.getElementById('networkTime');if(el&&d.beijing)el.textContent=d.beijing+' (来源: '+d.source+')';}).catch(function(e){console.warn('fetchNetworkTime:',e);});}
// 实时宏观: BIS 央行政策利率 + World Bank GDP/CPI
function fetchMacro(){var fa=document.getElementById('macroFetchedAt');if(!serverOnline){if(fa)fa.textContent='服务器未连接 · 显示下方静态快照';return;}
  if(fa)fa.textContent='获取中...';
  _fetchJSON('macro',BASE+'/api/macro?refresh=1',20000).then(function(d){
    if(fa)fa.textContent='实时数据获取于: '+(d.fetched_at||'--')+' · 来源: '+(d.source||'');
    renderMacroCards('macroPolicyRates', d.policy_rates, 'rate', 'date', '%', 'blue');
    renderMacroCards('macroGdp', d.gdp_growth, 'value', 'date', '%', 'sign');
    renderMacroCards('macroCpi', d.cpi, 'value', 'date', '%', 'amber');
  }).catch(function(e){
    if(fa)fa.textContent='获取失败: '+((e&&e.message)||e)+' · 显示下方静态快照';
  });}
function renderMacroCards(containerId, arr, valKey, dateKey, suffix, colorMode){
  var box=document.getElementById(containerId);if(!box)return;
  if(!arr||!arr.length){box.innerHTML='<div class="loading-hint">暂无数据 / 获取失败，请稍后重试或查看本页下方静态快照</div>';return;}
  box.innerHTML=arr.map(function(it){
    var v=it[valKey];var color='#58a6ff';
    if(colorMode==='sign'){color = v>0?'#ff7b72':(v<0?'#7ee787':'#c9d1d9');}
    else if(colorMode==='amber'){color='#e3b341';}
    var disp=(v==null?'--':((colorMode==='sign'&&v>0)?'+':'')+v+suffix);
    return '<div class="sc"><div class="lb">'+it.country+'</div><div class="vl" style="color:'+color+'">'+disp+'</div><div class="cg" style="color:#8b949e;font-size:11px">'+((it[dateKey]||'')+'')+'</div></div>';
  }).join('');}
// ===== 进阶数据实时面板（FRED TIPS/原油/美元指数 + BIS有效汇率 实时；其余为快照） =====
function initAdvChart(cid,title,seriesMap){
  var el=document.getElementById(cid);if(!el)return;
  var box=document.getElementById('chart_'+cid);
  if(!box){box=document.createElement('div');box.id='chart_'+cid;box.style.height='220px';box.style.marginTop='12px';el.appendChild(box);}
  var names=Object.keys(seriesMap||{});
  if(!names.length)return;
  var labels=(seriesMap[names[0]]||[]).map(function(p){return p[0];});
  var series=names.map(function(n){
    return {name:n,type:'line',data:(seriesMap[n]||[]).map(function(p){return p[1];}),smooth:true,symbol:'none',lineStyle:{width:1.8}};
  });
  var option={
    backgroundColor:'transparent',
    tooltip:{trigger:'axis',backgroundColor:'rgba(22,27,34,0.95)',borderColor:'#30363d',textStyle:{color:'#c9d1d9'}},
    legend:{data:names,textStyle:{color:'#8b949e',fontSize:11},top:0,type:'scroll'},
    grid:{left:'8%',right:'8%',bottom:'18%',top:38},
    dataZoom:[{type:'slider',xAxisIndex:0,bottom:6,height:16,backgroundColor:'#161b22',fillerColor:'#30363d',textStyle:{color:'#8b949e'}},{type:'inside'}],
    xAxis:{type:'category',data:labels,axisLine:{lineStyle:{color:'#30363d'}},axisLabel:{color:'#8b949e',fontSize:10,interval:Math.max(0,Math.floor(labels.length/8))}},
    yAxis:{type:'value',scale:true,axisLine:{lineStyle:{color:'#30363d'}},axisLabel:{color:'#8b949e'},splitLine:{lineStyle:{color:'#21262d'}}},
    series:series,color:COLORS
  };
  if(!echartsInstances[cid])echartsInstances[cid]=echarts.init(box);
  echartsInstances[cid].setOption(option,true);
}
/* ===== 进阶图表霓虹渲染器（TIPS 利差 / 多国 EER 对比） ===== */
function hexA(h,a){var n=parseInt(h.slice(1),16);var r=(n>>16)&255,g=(n>>8)&255,b=n&255;return 'rgba('+r+','+g+','+b+','+a+')';}
function neonGrad(h,t,b){return {type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:hexA(h,t)},{offset:1,color:hexA(h,b)}]};}
var NEON_PAL=['#00f0ff','#ff2d95','#7c4dff','#00ff9d','#ffd300','#ff6b35','#4dabf7','#ff5252','#2af598','#ff61d2'];
function neonLine(cid,seriesMap,opt){
  opt=opt||{};
  var el=document.getElementById(cid);if(!el)return;
  var box=document.getElementById('chart_'+cid);
  if(!box){box=document.createElement('div');box.id='chart_'+cid;box.style.height=(opt.height||240)+'px';box.style.marginTop='12px';box.style.borderRadius='8px';el.appendChild(box);}
  var names=Object.keys(seriesMap||{});
  if(!names.length)return;
  var labels=(seriesMap[names[0]]||[]).map(function(p){return p[0];});
  var colors=opt.colors||NEON_PAL;
  var glow=opt.glow||13, lw=opt.width||2.4;
  var gc=opt.glowColor||colors[0];
  box.style.background='radial-gradient(120% 80% at 50% 0%,'+hexA(gc,0.10)+',rgba(13,17,23,0) 70%)';
  var series=names.map(function(n,i){
    var c=colors[i%colors.length];
    var data=(seriesMap[n]||[]).map(function(p){return p[1];});
    var s={name:n,type:'line',data:data,smooth:true,symbol:'none',
      lineStyle:{width:lw,color:c,shadowBlur:glow,shadowColor:c,opacity:0.96},
      itemStyle:{color:c,shadowBlur:10,shadowColor:c},
      emphasis:{focus:'series',lineStyle:{width:lw+1.6}},
      z:i+1};
    if(opt.area!==false)s.areaStyle={color:neonGrad(c,opt.areaTop!=null?opt.areaTop:0.24,0)};
    if(opt.markLast!==false&&data.length){
      var last=data[data.length-1];
      s.markPoint={symbol:'circle',symbolSize:opt.markSize||9,
        itemStyle:{color:c,shadowBlur:16,shadowColor:c,borderColor:'#ffffff',borderWidth:1.5},
        label:{show:true,formatter:last.toFixed(2)+(opt.suffix||''),color:c,fontSize:10,fontWeight:'bold',position:'top',textShadowColor:c,textShadowBlur:6},
        data:[{coord:[labels[labels.length-1],last]}]};
    }
    if(opt.zeroLine){
      s.markLine={silent:true,symbol:'none',lineStyle:{color:'#9fb3c8',type:'dashed',width:1},
        label:{show:true,position:'end',formatter:'0',color:'#9fb3c8',fontSize:10},data:[{yAxis:0}]};
    }
    return s;
  });
  var primary=colors[0];
  var option={backgroundColor:'transparent',animationDuration:1300,animationEasing:'cubicOut',
    tooltip:{trigger:'axis',backgroundColor:'rgba(8,12,20,0.92)',borderColor:primary,borderWidth:1,
      textStyle:{color:'#e6f7ff',fontSize:12},
      axisPointer:{type:'line',lineStyle:{color:hexA(primary,0.5),width:1,type:'dashed'}},
      formatter:function(ps){if(!ps.length)return'';var s=ps[0].axisValue+(opt.unit?' ('+opt.unit+')':'')+'\n';ps.forEach(function(p){var v=p.value==null?'--':p.value.toFixed(2)+(opt.suffix||'');s+=p.marker+p.seriesName+': '+v+'\n';});return s;}},
    legend:{data:names,top:0,type:'scroll',textStyle:{color:'#9fb3c8',fontSize:11},inactiveColor:'#3a4756',itemWidth:18,itemHeight:3,itemGap:14,pageTextStyle:{color:'#9fb3c8'},pageIconColor:primary,pageIconInactiveColor:'#3a4756'},
    grid:{left:'7%',right:'6%',bottom:opt.dataZoom===false?'8%':'15%',top:38,containLabel:true},
    xAxis:{type:'category',data:labels,boundaryGap:false,axisLine:{lineStyle:{color:hexA(primary,0.35)}},axisTick:{show:false},axisLabel:{color:'#8b949e',fontSize:10,interval:Math.max(0,Math.floor(labels.length/8))}},
    yAxis:{type:'value',scale:true,name:opt.yName||'',nameTextStyle:{color:'#8b949e',fontSize:10},axisLine:{show:false},axisTick:{show:false},axisLabel:{color:'#8b949e',fontSize:10,formatter:function(v){return v+(opt.suffix||'');}},splitLine:{lineStyle:{color:'rgba(120,140,170,0.12)'}}},
    series:series,color:colors};
  if(opt.dataZoom!==false){
    option.dataZoom=[{type:'slider',xAxisIndex:0,bottom:8,height:16,backgroundColor:'rgba(20,26,38,0.6)',borderColor:hexA(primary,0.15),fillerColor:hexA(primary,0.18),dataBackground:{lineStyle:{color:hexA(primary,0.5)},areaStyle:{color:hexA(primary,0.12)}},selectedDataBackground:{lineStyle:{color:primary},areaStyle:{color:hexA(primary,0.2)}},handleStyle:{color:primary,shadowBlur:8,shadowColor:primary},moveHandleStyle:{color:hexA(primary,0.6)},textStyle:{color:'#8b949e'},labelFormatter:''},{type:'inside'}];
  }
  // 净头寸零轴着色：正值=青(#00f0ff) / 负值=品红(#ff2d95)，按 y 值符号分段
  if(opt.posNeg){
    option.visualMap={show:false,dimension:1,seriesIndex:'all',
      pieces:[{gte:0,color:'#00f0ff'},{lt:0,color:'#ff2d95'}],
      outOfRange:{color:'#8b949e'}};
  }
  if(echartsInstances[cid]){try{echartsInstances[cid].dispose();}catch(e){}}
  echartsInstances[cid]=echarts.init(box);
  echartsInstances[cid].setOption(option,true);
}
function _advBadge(live,fetched_at,updated){
  if(live)return '<span style="color:#7ee787;font-size:12px">● 实时·'+(fetched_at||'')+'</span>';
  var u=updated||fetched_at||'--';
  return '<span style="color:#e3b341;font-size:12px">● 快照·更新于 '+u+'</span>';
}
function _fmt(v,suffix){if(v===null||v===undefined)return '--';var s=(typeof v==='number')?v.toFixed(2):v;return s+(suffix||'');}
function _sc(lb,vl,cg,color){
  var c=color||'#58a6ff';
  return '<div class="sc"><div class="lb">'+lb+'</div><div class="vl" style="color:'+c+'">'+vl+'</div><div class="cg" style="color:#8b949e;font-size:11px">'+cg+'</div></div>';
}
function renderAdvTips(sec){
  var el=document.getElementById('advTips');if(!el)return;
  if(!sec){el.innerHTML='<div class="loading-hint">TIPS 数据暂不可用</div>';return;}
  var d=sec.dfii10||{},t=sec.t10yie||{},s=sec.sofr||{};
  var html='<div class="tt">TIPS 实际收益率 / 通胀预期 / 利差（霓虹实时） <span style="float:right">'+_advBadge(sec.live,sec.fetched_at)+'</span></div>';
  html+='<div style="display:flex;flex-wrap:wrap;gap:10px;margin:10px 0">';
  html+=_sc('10Y TIPS实际收益率 (DFII10)',_fmt(d.value)+'%',d.date||'','#00f0ff');
  html+=_sc('10Y 盈亏平衡通胀 (T10YIE)',_fmt(t.value)+'%',t.date||'','#ff2d95');
  html+=_sc('SOFR 隔夜担保融资',_fmt(s.value)+'%',s.date||'','#00ff9d');
  html+='</div>';
  if(sec.spread_note)html+='<div class="bd" style="font-size:12px;color:#8b949e;margin-bottom:8px">'+sec.spread_note+'</div>';
  el.innerHTML=html;
  // 计算利差序列 DFII10 - T10YIE（实际利率 − 通胀预期）
  var sm={};
  var df=(sec.series&&sec.series['TIPS实际收益率(DFII10)'])||[];
  var tb=(sec.series&&sec.series['盈亏平衡通胀(T10YIE)'])||[];
  sm['TIPS实际收益率(DFII10)']=df;
  sm['盈亏平衡通胀(T10YIE)']=tb;
  if(df.length&&tb.length){
    var tmap={};tb.forEach(function(p){tmap[p[0]]=p[1];});
    var sp=df.map(function(p){var x=tmap[p[0]];return [p[0],(x==null||p[1]==null)?null:+(p[1]-x).toFixed(2)];});
    sm['利差 (DFII10−T10YIE)']=sp;
  }
  if(Object.keys(sm).length)neonLine('advTips',sm,{colors:['#00f0ff','#ff2d95','#00ff9d'],yName:'%',suffix:'%',areaTop:0.26,height:250,glowColor:'#00f0ff'});
}
function renderAdvOil(sec){
  var el=document.getElementById('advOil');if(!el)return;
  if(!sec){el.innerHTML='<div class="loading-hint">原油数据暂不可用</div>';return;}
  var w=sec.wti||{},b=sec.brent||{};
  var html='<div class="tt">原油现货价（霓虹实时, WTI / Brent） <span style="float:right">'+_advBadge(sec.live,sec.fetched_at)+'</span></div>';
  html+='<div style="display:flex;flex-wrap:wrap;gap:10px;margin:10px 0">';
  html+=_sc('WTI 原油',_fmt(w.value)+' $/bbl',w.date||'','#ffa940');
  html+=_sc('Brent 原油',_fmt(b.value)+' $/bbl',b.date||'','#ff6b35');
  html+='</div>';
  el.innerHTML=html;
  if(sec.series&&Object.keys(sec.series).length)neonLine('advOil',sec.series,{colors:['#ffa940','#ff6b35'],yName:'$/bbl',areaTop:0.22,height:230,glowColor:'#ffa940'});
}
function renderAdvUsd(sec){
  var el=document.getElementById('advUsd');if(!el)return;
  if(!sec){el.innerHTML='<div class="loading-hint">美元指数暂不可用</div>';return;}
  var html='<div class="tt">广义美元指数（霓虹实时, DTWEXBGS） <span style="float:right">'+_advBadge(sec.live,sec.fetched_at)+'</span></div>';
  html+='<div style="display:flex;flex-wrap:wrap;gap:10px;margin:10px 0">'+_sc('广义美元指数',_fmt(sec.value),sec.date||'','#4dabf7')+'</div>';
  if(sec.note)html+='<div class="bd" style="font-size:12px;color:#8b949e">'+sec.note+'</div>';
  el.innerHTML=html;
  if(sec.series&&Object.keys(sec.series).length)neonLine('advUsd',sec.series,{colors:['#4dabf7'],yName:'DTWEXBGS',areaTop:0.20,height:230,glowColor:'#4dabf7'});
}
function renderAdvEer(sec){
  var el=document.getElementById('advEer');if(!el)return;
  if(!sec||!sec.areas||!sec.areas.length){el.innerHTML='<div class="loading-hint">BIS 有效汇率暂不可用</div>';return;}
  var html='<div class="tt">BIS 有效汇率指数（霓虹多国对比, 2020=100, 月度） <span style="float:right">'+_advBadge(sec.live,sec.fetched_at)+'</span></div>';
  html+='<table class="adv-tbl"><thead><tr><th>经济体</th><th>NEER 名义</th><th>日期</th><th>REER 实际</th><th>日期</th></tr></thead><tbody>';
  sec.areas.forEach(function(a){
    html+='<tr><td>'+a.name+'</td><td>'+(a.neer!=null?a.neer.toFixed(2):'--')+'</td><td style="color:#8b949e;font-size:11px">'+(a.neer_date||'')+'</td><td>'+(a.reer!=null?a.reer.toFixed(2):'--')+'</td><td style="color:#8b949e;font-size:11px">'+(a.reer_date||'')+'</td></tr>';
  });
  html+='</tbody></table>';
  if(sec.note)html+='<div class="bd" style="font-size:12px;color:#8b949e;margin-top:6px">'+sec.note+'</div>';
  el.innerHTML=html;
  var sm={};
  sec.areas.forEach(function(a){if(a.reer_series&&a.reer_series.length)sm[a.name+' REER']=a.reer_series;});
  if(Object.keys(sm).length)neonLine('advEer',sm,{colors:['#ff2d95','#00f0ff','#7c4dff','#00ff9d','#ffd300','#ff6b35','#4dabf7','#ff5252'],yName:'REER (2020=100)',areaTop:0.10,height:280,glowColor:'#ff2d95',markLast:false});
}
function renderAdvCpi(sec){
  var el=document.getElementById('advCpi');if(!el)return;
  if(!sec){el.innerHTML='<div class="loading-hint">CPI 数据暂不可用</div>';return;}
  var html='<div class="tt">美国 CPI 通胀（霓虹实时, FRED CPIAUCSL） <span style="float:right">'+_advBadge(sec.live,sec.fetched_at)+'</span></div>';
  html+='<div style="display:flex;flex-wrap:wrap;gap:10px;margin:10px 0">';
  html+=_sc('CPI 指数',_fmt(sec.value),sec.date||'','#ffd300');
  html+=_sc('CPI 同比 YoY',(sec.yoy!=null?sec.yoy.toFixed(2):'--')+'%','#ffd300');
  html+=_sc('CPI 月率 MoM',(sec.mom!=null?sec.mom.toFixed(2):'--')+'%','#ffd300');
  html+='</div>';
  if(sec.note)html+='<div class="bd" style="font-size:12px;color:#8b949e;margin-bottom:8px">'+sec.note+'</div>';
  el.innerHTML=html;
  if(sec.series&&Object.keys(sec.series).length)neonLine('advCpi',sec.series,{colors:['#ffd300'],yName:'CPI 同比 %',suffix:'%',areaTop:0.22,height:230,glowColor:'#ffd300'});
}
function renderAdvUnemployment(sec){
  var el=document.getElementById('advUnemployment');if(!el)return;
  if(!sec){el.innerHTML='<div class="loading-hint">失业率数据暂不可用</div>';return;}
  var html='<div class="tt">美国失业率（霓虹实时, FRED UNRATE） <span style="float:right">'+_advBadge(sec.live,sec.fetched_at)+'</span></div>';
  html+='<div style="display:flex;flex-wrap:wrap;gap:10px;margin:10px 0">';
  html+=_sc('失业率 U3',(sec.value!=null?sec.value.toFixed(2):'--')+'%',sec.date||'','#ff6b35');
  html+=_sc('月变动',(sec.change!=null?(sec.change>0?'+':'')+sec.change.toFixed(2):'--')+' pt','#ff6b35');
  html+='</div>';
  if(sec.note)html+='<div class="bd" style="font-size:12px;color:#8b949e;margin-bottom:8px">'+sec.note+'</div>';
  el.innerHTML=html;
  if(sec.series&&Object.keys(sec.series).length)neonLine('advUnemployment',sec.series,{colors:['#ff6b35'],yName:'失业率 %',suffix:'%',areaTop:0.20,height:230,glowColor:'#ff6b35'});
}
function renderAdvDxyIbs(sec){
  var el=document.getElementById('advDxyIbs');if(!el)return;
  if(!sec){el.innerHTML='<div class="loading-hint">DXY IBS 数据暂不可用</div>';return;}
  var html='<div class="tt">DXY 内部买卖盘比 (IBS) <span style="float:right">'+_advBadge(sec.live,sec.fetched_at)+'</span></div>';
  var d=sec.data||{};
  if(d.formula)html+='<div class="bd" style="font-size:11px;color:#8b949e">'+d.formula+'</div>';
  html+='<div style="display:flex;flex-wrap:wrap;gap:10px;margin:8px 0">';
  html+=_sc('IBS 值',(d.value!=null?d.value.toFixed(2):'--'),d.date||'');
  html+=_sc('日内高',(d.high!=null?d.high.toFixed(2):'--'),'');
  html+=_sc('日内低',(d.low!=null?d.low.toFixed(2):'--'),'');
  html+=_sc('收盘',(d.close!=null?d.close.toFixed(2):'--'),'');
  html+='</div>';
  if(d.band)html+='<div class="bd" style="font-size:12px;color:#8b949e">'+d.band+'</div>';
  if(d.note)html+='<div class="bd" style="font-size:12px;color:#8b949e">'+d.note+'</div>';
  el.innerHTML=html;
}
function renderAdvFxSwap(sec){
  var el=document.getElementById('advFxSwap');if(!el)return;
  if(!sec){el.innerHTML='<div class="loading-hint">外汇掉期数据暂不可用</div>';return;}
  var html='<div class="tt">外汇掉期点 (FX Swaps) <span style="float:right">'+_advBadge(sec.live,sec.fetched_at,sec.updated)+'</span></div>';
  if(sec.items&&sec.items.length){
    html+='<table class="adv-tbl"><thead><tr><th>货币对</th><th>期限</th><th>掉期点</th><th>来源</th></tr></thead><tbody>';
    sec.items.forEach(function(it){html+='<tr><td>'+(it[0]||'')+'</td><td>'+(it[1]||'')+'</td><td>'+(it[2]!=null?it[2]:'--')+'</td><td style="color:#8b949e;font-size:11px">'+(it[3]||'')+'</td></tr>';});
    html+='</tbody></table>';
  } else html+='<div class="loading-hint">暂无数据</div>';
  if(sec.note)html+='<div class="bd" style="font-size:12px;color:#8b949e;margin-top:6px">'+sec.note+'</div>';
  el.innerHTML=html;
}
function renderAdvCofer(sec){
  var el=document.getElementById('advCofer');if(!el)return;
  if(!sec){el.innerHTML='<div class="loading-hint">COFER 数据暂不可用</div>';return;}
  var html='<div class="tt">IMF COFER 外汇储备币种构成 <span style="float:right">'+_advBadge(sec.live,sec.fetched_at,sec.updated)+'</span></div>';
  if(sec.live&&sec.items&&sec.items.length){
    html+='<div style="display:flex;flex-wrap:wrap;gap:10px;margin:10px 0">';
    if(sec.usd!=null)html+=_sc('美元份额', sec.usd.toFixed(2)+'%', sec.date||'','#00f0ff');
    if(sec.eur!=null)html+=_sc('欧元份额', sec.eur.toFixed(2)+'%', '','#7c4dff');
    if(sec.cny!=null)html+=_sc('人民币份额', sec.cny.toFixed(2)+'%', '','#ffd300');
    if(sec.jpy!=null)html+=_sc('日元份额', sec.jpy.toFixed(2)+'%', '','#ff6b35');
    if(sec.gbp!=null)html+=_sc('英镑份额', sec.gbp.toFixed(2)+'%', '','#00ff9d');
    html+='</div>';
    html+='<table class="adv-tbl"><thead><tr><th>币种</th><th>占比%</th><th>变动(pp)</th><th>季度</th></tr></thead><tbody>';
    sec.items.forEach(function(it){html+='<tr><td>'+(it[0]||'')+'</td><td>'+(it[1]!=null?it[1]:'--')+'</td><td>'+(it[2]!=null?it[2]:'--')+'</td><td style="color:#8b949e;font-size:11px">'+(it[3]||'')+'</td></tr>';});
    html+='</tbody></table>';
  } else {
    var d=sec.data||{};
    if(d.total)html+='<div class="bd" style="margin:6px 0"><b style="color:#e3b341">'+d.total+'</b></div>';
    if(d.items&&d.items.length){
      html+='<table class="adv-tbl"><thead><tr><th>币种</th><th>占比%</th><th>变动(pp)</th><th>说明</th></tr></thead><tbody>';
      d.items.forEach(function(it){html+='<tr><td>'+(it[0]||'')+'</td><td>'+(it[1]!=null?it[1]:'--')+'</td><td>'+(it[2]!=null?it[2]:'--')+'</td><td style="color:#8b949e;font-size:11px">'+(it[3]||'')+'</td></tr>';});
      html+='</tbody></table>';
    }
  }
  if(sec.note)html+='<div class="bd" style="font-size:12px;color:#8b949e;margin-top:6px">'+sec.note+'</div>';
  el.innerHTML=html;
  if(sec.live&&sec.series){
    var sm={};Object.keys(sec.series).forEach(function(k){sm[k]=sec.series[k];});
    if(Object.keys(sm).length)neonLine('advCofer',sm,{colors:['#00f0ff','#7c4dff','#ffd300','#ff6b35','#00ff9d'],yName:'份额%',areaTop:0.10,height:240,glowColor:'#00f0ff',markLast:true});
  }
}
var _cotSec=null,_cotMode='lev';
function _cotBtnStyle(m){
  var on=_cotMode===m;
  return 'cursor:pointer;border:1px solid '+(on?'#00f0ff':'#30363d')+';background:'+(on?'rgba(0,240,255,0.14)':'transparent')+';color:'+(on?'#00f0ff':'#8b949e')+';padding:4px 12px;border-radius:6px;font-size:12px;font-weight:'+(on?'bold':'normal');
}
function _setCotMode(m){_cotMode=m;var t=document.getElementById('cotToggle');if(t){var bs=t.getElementsByTagName('button');for(var i=0;i<bs.length;i++){bs[i].setAttribute('style',_cotBtnStyle(i===0?'lev':'tot'));}}_renderCotChart();}
function _renderCotChart(){
  if(!_cotSec||!_cotSec.series)return;
  var sm={};
  Object.keys(_cotSec.series).forEach(function(ccy){
    var s=_cotSec.series[ccy];
    if(s&&s.dates&&s.dates.length){
      var arr=_cotMode==='tot'?s.tot:s.lev;
      if(arr)sm[ccy+' '+( _cotMode==='tot'?'全体净':'杠杆净')]=s.dates.map(function(dt,i){return [dt,arr[i]];});
    }
  });
  if(Object.keys(sm).length)neonLine('advCot',sm,{colors:['#00f0ff','#ff2d95','#7c4dff','#00ff9d','#ffd300','#ff6b35','#4dabf7','#ff5252'],yName:'净持仓(合约)',areaTop:0.10,height:260,glowColor:'#00f0ff',markLast:false,zeroLine:true,posNeg:true});
}
function renderAdvCot(sec){
  var el=document.getElementById('advCot');if(!el)return;
  _cotSec=sec;
  if(!sec){el.innerHTML='<div class="loading-hint">COT 数据暂不可用</div>';return;}
  var html='<div class="tt">CFTC COT 持仓 (实时·各币种净头寸走势) <span style="float:right">'+_advBadge(sec.live,sec.fetched_at,sec.updated)+'</span></div>';
  var d=sec.data||{};
  if(d.items&&d.items.length){
    html+='<table class="adv-tbl"><thead><tr><th>品种</th><th>方向</th><th>净持仓</th><th>变动</th><th>说明</th></tr></thead><tbody>';
    d.items.forEach(function(it){html+='<tr><td>'+(it[0]||'')+'</td><td>'+(it[1]||'')+'</td><td>'+(it[2]!=null?it[2]:'--')+'</td><td>'+(it[3]!=null?it[3]:'--')+'</td><td style="color:#8b949e;font-size:11px">'+(it[4]||'')+'</td></tr>';});
    html+='</tbody></table>';
  }
  if(d.note)html+='<div class="bd" style="font-size:12px;color:#8b949e;margin-top:6px">'+d.note+'</div>';
  // 杠杆净 / 全体净 切换 + 零轴正负着色说明
  html+='<div id="cotToggle" style="margin:10px 0;display:flex;gap:8px;align-items:center;flex-wrap:wrap">'
       +'<button onclick="_setCotMode(\'lev\')" style="'+_cotBtnStyle('lev')+'">杠杆基金净</button>'
       +'<button onclick="_setCotMode(\'tot\')" style="'+_cotBtnStyle('tot')+'">全体净</button>'
       +'<span style="font-size:11px;margin-left:6px"><span style="color:#00f0ff">● 零线以上=净多(青)</span> <span style="color:#ff2d95">● 以下=净空(品红)</span></span></div>';
  el.innerHTML=html;
  _renderCotChart();
}
function renderAdvCbGold(sec){
  var el=document.getElementById('advCbGold');if(!el)return;
  if(!sec){el.innerHTML='<div class="loading-hint">央行购金数据暂不可用</div>';return;}
  var html='<div class="tt">全球央行购金 (WGC) <span style="float:right">'+_advBadge(sec.live,sec.fetched_at)+'</span></div>';
  if(sec.live&&sec.latest_value!=null){
    html+='<div style="display:flex;flex-wrap:wrap;gap:10px;margin:10px 0">';
    html+=_sc('最新季度净购金 ('+ (sec.latest_quarter||'') +')', (sec.latest_value+' t'), '央行净买入', '#ffd300');
    if(sec.h1_value!=null)html+=_sc(sec.latest_quarter.split(' ')[0]+' 上半年合计', (sec.h1_value+' t'), 'H1 累计', '#00ff9d');
    html+='</div>';
  }
  if(sec.items&&sec.items.length){
    html+='<table class="adv-tbl"><thead><tr><th>期间</th><th>净购金</th><th>同比</th><th>说明</th></tr></thead><tbody>';
    sec.items.forEach(function(it){html+='<tr><td>'+(it[0]||'')+'</td><td>'+(it[1]||'')+'</td><td>'+(it[2]||'')+'</td><td style="color:#8b949e;font-size:11px">'+(it[3]||'')+'</td></tr>';});
    html+='</tbody></table>';
  }
  if(sec.note)html+='<div class="bd" style="font-size:12px;color:#8b949e;margin-top:6px">'+sec.note+'</div>';
  el.innerHTML=html;
}
function renderAdvEtf(sec){
  var el=document.getElementById('advEtf');if(!el)return;
  if(!sec){el.innerHTML='<div class="loading-hint">黄金ETF数据暂不可用</div>';return;}
  var html='<div class="tt">黄金 ETF 流量 <span style="float:right">'+_advBadge(sec.live,sec.fetched_at)+'</span></div>';
  if(sec.items&&sec.items.length){
    html+='<table class="adv-tbl"><thead><tr><th>区间/主体</th><th>流量</th><th>方向</th><th>说明</th></tr></thead><tbody>';
    sec.items.forEach(function(it){html+='<tr><td>'+(it[0]||'')+'</td><td>'+(it[1]||'')+'</td><td>'+(it[2]||'')+'</td><td style="color:#8b949e;font-size:11px">'+(it[3]||'')+'</td></tr>';});
    html+='</tbody></table>';
  }
  if(sec.note)html+='<div class="bd" style="font-size:12px;color:#8b949e;margin-top:6px">'+sec.note+'</div>';
  el.innerHTML=html;
}
function renderAdvGoldDemand(sec){
  var el=document.getElementById('advGoldDemand');if(!el)return;
  if(!sec){el.innerHTML='<div class="loading-hint">黄金需求数据暂不可用</div>';return;}
  var html='<div class="tt">全球黄金需求 (WGC) <span style="float:right">'+_advBadge(sec.live,sec.fetched_at)+'</span></div>';
  var d=sec.data||{};
  if(d.date)html+='<div class="bd" style="font-size:12px;color:#8b949e">'+d.date+'</div>';
  if(d.items&&d.items.length){
    html+='<table class="adv-tbl"><thead><tr><th>指标</th><th>数值</th><th>同比/变动</th><th>说明</th></tr></thead><tbody>';
    d.items.forEach(function(it){html+='<tr><td>'+(it[0]||'')+'</td><td>'+(it[1]||'')+'</td><td>'+(it[2]||'')+'</td><td style="color:#8b949e;font-size:11px">'+(it[3]||'')+'</td></tr>';});
    html+='</tbody></table>';
  }
  el.innerHTML=html;
}
function renderAdvEiaOil(sec){
  var el=document.getElementById('advEiaOil');if(!el)return;
  if(!sec){el.innerHTML='<div class="loading-hint">EIA 原油库存数据暂不可用</div>';return;}
  var lv=sec.latest_value, ch=sec.change, yoy=sec.yoy, unit=sec.unit||'千桶';
  var chColor = ch==null?'#8b949e':(ch>=0?'#ff6b6b':'#3fb950'); // 库存升=偏空(暖色)
  var yoyColor = yoy==null?'#8b949e':(yoy>=0?'#ff6b6b':'#3fb950');
  var html='<div class="tt">EIA 原油库存（商业·周度·实时） <span style="float:right">'+_advBadge(sec.live,sec.fetched_at)+'</span></div>';
  html+='<div style="display:flex;flex-wrap:wrap;gap:10px;margin:10px 0">';
  html+=_sc('最新商业原油库存 ('+unit+')', (lv!=null?Math.round(lv).toLocaleString():'--'), sec.latest_period||'','#ffd300');
  html+='<div class="sc"><div class="lb">周变动</div><div class="vl" style="color:'+chColor+'">'+(ch==null?'--':(ch>=0?'+':'')+Math.round(ch).toLocaleString())+'</div><div class="cg" style="color:#8b949e;font-size:11px">vs 上周</div></div>';
  html+='<div class="sc"><div class="lb">同比(约1年)</div><div class="vl" style="color:'+yoyColor+'">'+(yoy==null?'--':(yoy>=0?'+':'')+Math.round(yoy).toLocaleString())+'</div><div class="cg" style="color:#8b949e;font-size:11px">vs 去年同周</div></div>';
  html+='</div>';
  if(sec.note)html+='<div class="bd" style="font-size:12px;color:#8b949e;margin-top:2px">'+sec.note+'</div>';
  el.innerHTML=html;
  if(sec.series){
    var sm={};Object.keys(sec.series).forEach(function(k){sm[k]=sec.series[k];});
    if(Object.keys(sm).length)neonLine('advEiaOil',sm,{colors:['#ffd300'],yName:'千桶',areaTop:0.10,height:240,glowColor:'#ffd300',markLast:true});
  }
}
function renderAdvEiaIea(sec){
  var el=document.getElementById('advEiaIea');if(!el)return;
  if(!sec){el.innerHTML='<div class="loading-hint">EIA/IEA 石油数据暂不可用</div>';return;}
  var html='<div class="tt">EIA / IEA 石油供需与价格展望 <span style="float:right">'+_advBadge(sec.live,sec.fetched_at)+'</span></div>';
  var d=sec.data||{};
  ['weekly','steo','iea'].forEach(function(k){
    var blk=d[k];if(!blk)return;
    if(blk.date)html+='<div class="bd" style="font-size:12px;color:#e3b341;margin-top:6px">'+blk.date+'</div>';
    if(blk.items&&blk.items.length){
      html+='<table class="adv-tbl"><thead><tr><th>指标</th><th>数值</th><th>预期/对比</th><th>说明</th></tr></thead><tbody>';
      blk.items.forEach(function(it){html+='<tr><td>'+(it[0]||'')+'</td><td>'+(it[1]||'')+'</td><td>'+(it[2]||'')+'</td><td style="color:#8b949e;font-size:11px">'+(it[3]||'')+'</td></tr>';});
      html+='</tbody></table>';
    }
    if(blk.api_note)html+='<div class="bd" style="font-size:11px;color:#8b949e">'+blk.api_note+'</div>';
  });
  el.innerHTML=html;
}
function fetchAdvanced(){
  var fa=document.getElementById('advFetchedAt');
  if(!serverOnline){if(fa)fa.textContent='服务器未连接 · 显示下方静态快照';return;}
  if(fa)fa.textContent='获取中...';
  _fetchJSON('advanced',BASE+'/api/advanced?refresh=1',30000).then(function(d){
    if(fa)fa.textContent='实时数据获取于: '+(d.fetched_at||'--')+' · 来源: '+(d.source||'');
    var S=d.sections||{};
    try{renderAdvTips(S.tips);}catch(e){console.error('renderAdvTips',e);}
    try{renderAdvOil(S.oil);}catch(e){console.error('renderAdvOil',e);}
    try{renderAdvUsd(S.usd_index);}catch(e){console.error('renderAdvUsd',e);}
    try{renderAdvEer(S.eer);}catch(e){console.error('renderAdvEer',e);}
    try{renderAdvCpi(S.cpi);}catch(e){console.error('renderAdvCpi',e);}
    try{renderAdvUnemployment(S.unemployment);}catch(e){console.error('renderAdvUnemployment',e);}
    try{renderAdvDxyIbs(S.dxy_ibs);}catch(e){console.error('renderAdvDxyIbs',e);}
    try{renderAdvFxSwap(S.fx_swap);}catch(e){console.error('renderAdvFxSwap',e);}
    try{renderAdvCofer(S.cofer);}catch(e){console.error('renderAdvCofer',e);}
    try{renderAdvCot(S.cot);}catch(e){console.error('renderAdvCot',e);}
    try{renderAdvCbGold(S.cb_gold);}catch(e){console.error('renderAdvCbGold',e);}
    try{renderAdvEtf(S.etf_gold);}catch(e){console.error('renderAdvEtf',e);}
    try{renderAdvGoldDemand(S.gold_demand);}catch(e){console.error('renderAdvGoldDemand',e);}
    try{renderAdvEiaOil(S.eia_oil);}catch(e){console.error('renderAdvEiaOil',e);}
    try{renderAdvEiaIea(S.eia_iea_oil);}catch(e){console.error('renderAdvEiaIea',e);}
  }).catch(function(e){
    if(fa)fa.textContent='获取失败: '+((e&&e.message)||e)+' · 显示下方静态快照';
  });
}
/* ===== 刷新治理层: 超时(AbortController) / 互斥(防堆积) / 竞态(序号) / 合并连点 ===== */
var _reqCtl={};var _reqSeq={};var _busy={};var _pending={};var _lastQuotesAt=0;var _lastQuotesMs=0;
function _fetchJSON(mod,url,timeoutMs){
  timeoutMs=timeoutMs||20000;
  if(_reqCtl[mod]){try{_reqCtl[mod].abort();}catch(e){}}
  var seq=(_reqSeq[mod]=(_reqSeq[mod]||0)+1);
  var ctl=new AbortController();_reqCtl[mod]=ctl;
  var timer=setTimeout(function(){try{ctl.abort();}catch(e){}},timeoutMs);
  return fetch(url,{cache:'no-store',signal:ctl.signal}).then(function(r){
    clearTimeout(timer);
    if(!r.ok)throw new Error('HTTP '+r.status);
    return r.json();
  }).then(function(d){
    if(_reqSeq[mod]!==seq)throw new Error('stale-response');
    if(_reqCtl[mod]===ctl)_reqCtl[mod]=null;
    return d;
  },function(e){clearTimeout(timer);if(_reqCtl[mod]===ctl)_reqCtl[mod]=null;throw e;});
}
function _exclusive(mod,fn){
  if(_busy[mod]){_pending[mod]=true;return;}
  _busy[mod]=true;
  var release=function(){_busy[mod]=false;if(_pending[mod]){_pending[mod]=false;fn(release);}};
  try{fn(release);}catch(e){release();}
}
function fetchQuotes(){_exclusive('quotes',function(done){
  var elDot=document.getElementById('liveDot');var elSt=document.getElementById('liveStatus');
  var t0=Date.now();
  if(elDot)elDot.classList.add('loading');
  if(elSt)elSt.innerHTML='<span class="live-spin"></span> 正在获取全网数据...';
  _fetchJSON('quotes',BASE+'/api/quotes?refresh=1',45000).then(function(payload){
    var data=payload.quotes||payload;var cnt=Object.keys(data).length;
    var metaSources=payload.sources||{};var metaHealth=payload.health||{};
    var fetchedAt=payload.fetched_at||'';
    var ms=Date.now()-t0;_lastQuotesMs=ms;_lastQuotesAt=Date.now();
    if(elDot)elDot.classList.remove('loading');
    if(elSt)elSt.innerHTML='&#9989; 服务器在线 ('+cnt+'个品种) · 刷新耗时 '+((ms/1000).toFixed(1))+'s';
    for(var nm in data){updateTableCells(nm,data[nm]);}
    updateStatCards(data);
    renderQuoteSourceStatus(metaSources,metaHealth,fetchedAt);
    var hc=document.getElementById('headerCutoff');if(hc&&fetchedAt)hc.textContent=fetchedAt;
    var notes=document.querySelectorAll('.cutoff-note');
    for(var ni=0;ni<notes.length;ni++){notes[ni].innerHTML='&#9201; 数据截止时间: '+fetchedAt;}
    var now=new Date();document.getElementById('lastUpdateTime').textContent='最后更新: '+now.toLocaleTimeString();
    done();
  }).catch(function(e){
    var ms=Date.now()-t0;
    if(elDot)elDot.classList.remove('loading');
    if(e&&e.message==='stale-response'){done();return;}
    var msg=(e&&e.name==='AbortError')?'刷新超时('+((ms/1000).toFixed(0))+'s) - 服务器响应慢, 请稍后重试':('更新失败: '+((e&&e.message)||e));
    if(elSt)elSt.innerHTML='&#9888; '+msg;
    done();
  });
});}
function updateTableCells(name,q){var rows=document.querySelectorAll('#panel-overview tbody tr,#panel-forex tbody tr,#panel-commodities tbody tr,#panel-indices tbody tr,#panel-bonds tbody tr,#panel-macro tbody tr');rows.forEach(function(row){var cells=row.querySelectorAll('td');if(cells.length<4)return;var found=false;for(var i=0;i<Math.min(cells.length,3);i++){var t=cells[i].textContent.trim();if(t===name||t.indexOf(name)>=0||name.indexOf(t)>=0){found=true;break;}}if(!found)return;if(q.price!==null&&q.price!==undefined&&cells[2]){var srcTag=q.source&&q.source!=='daily_data_fallback'?'':'<span class="data-source-tag" title="来源:'+(q.source||'')+' '+(q.fetched_at||'')+'">回退</span>';cells[2].innerHTML=q.price.toFixed(4)+srcTag;}if(q.changePct!==null&&q.changePct!==undefined&&cells[3]){var cls=q.changePct>0?'pos':q.changePct<0?'neg':'flat';var sign=q.changePct>0?'+':'';cells[3].innerHTML='<span class="'+cls+'">'+sign+q.changePct.toFixed(2)+'</span>';}});}
function updateStatCards(data){
  var map={'道琼斯指数':'道琼斯工业平均指数','美元指数':'美元指数','现货黄金':'现货黄金','WTI原油':'WTI原油','VIX恐慌指数':'美国VIX恐慌指数','SOFR隔夜':'SOFR隔夜'};
  document.querySelectorAll('.sc[data-label]').forEach(function(card){
    var label=card.getAttribute('data-label');
    var key=map[label]||label;
    var q=data[key];
    if(!q||q.price===undefined||q.price===null)return;
    var vl=card.querySelector('.vl');var cg=card.querySelector('.cg');
    if(!vl||!cg)return;
    var decimals=2;
    if(label.indexOf('黄金')>=0||label.indexOf('原油')>=0){decimals=2;}
    else if(label.indexOf('美元')>=0){decimals=3;}
    else if(label.indexOf('VIX')>=0||label.indexOf('SOFR')>=0||label.indexOf('利率')>=0){decimals=2;}
    vl.textContent=q.price.toLocaleString('en-US',{minimumFractionDigits:decimals,maximumFractionDigits:decimals});
    var cls=q.changePct>0?'pos':q.changePct<0?'neg':'flat';
    var sign=q.changePct>0?'+':'';
    cg.className='cg '+cls;
    cg.textContent=sign+(q.changePct===0?'0.00':q.changePct.toFixed(2))+'%';
    vl.style.color=(q.changePct>0?'#ff4d4f':(q.changePct<0?'#52c41a':'#c9d1d9'));
  });
}
function renderQuoteSourceStatus(sources,health,fetchedAt){
  var el=document.getElementById('quoteSourceStatus');if(!el)return;
  var labels={'frankfurter':'ECB外汇','sina_hf':'新浪商品','sina_int':'新浪指数','sina_fx':'新浪外汇','eastmoney':'东方财富','yahoo_special':'Yahoo','yahoo_indices':'Yahoo指数','yahoo_commodities':'Yahoo商品','daily_data_fallback':'日报快照'};
  var html='<span>行情源:</span>';
  for(var k in sources){var ok=sources[k];var label=labels[k]||k;html+='<span class="'+(ok?'source-ok':'source-fail')+'">● '+label+'</span>';}
  if(fetchedAt)html+='<span>获取于 '+fetchedAt+'</span>';
  el.innerHTML=html;}
/* ===== 实时新闻：多源聚合 + 频道筛选（黄金/外汇/商品/原油为交易主线） ===== */
var _newsItems=[];var _newsChan='全部';
function _chanCls(c){if(c==='黄金')return 'ct-gold';if(c==='外汇')return 'ct-fx';if(c==='商品')return 'ct-comm';if(c==='原油')return 'ct-oil';return 'ct-other';}
function setNewsChannel(c){_newsChan=c;renderNewsChannels();renderNewsList();}
function renderNewsChannels(){
  var bar=document.getElementById('newsChannelBar');if(!bar)return;
  var order=['全部','黄金','外汇','商品','原油','深度','热文','全球','快讯','其他'];
  var cnt={};_newsItems.forEach(function(it){var c=it.channel||'其他';cnt[c]=(cnt[c]||0)+1;});
  var html='';
  order.forEach(function(c){
    var n=(c==='全部')?_newsItems.length:(cnt[c]||0);
    if(c!=='全部'&&!n)return;
    html+='<span class="news-chan'+(_newsChan===c?' active':'')+'" data-chan="'+c+'">'+c+' '+n+'</span>';
  });
  bar.innerHTML=html;
  bar.onclick=function(e){var t=e.target;if(!t)return;var c=t.getAttribute('data-chan');if(c)setNewsChannel(c);};
}
function renderNewsList(){
  var el=document.getElementById('newsList');if(!el)return;
  var list=(_newsChan==='全部')?_newsItems:_newsItems.filter(function(it){return (it.channel||'其他')===_newsChan;});
  if(!list.length){el.innerHTML='<div class="news-loading">该频道暂无内容</div>';return;}
    el.innerHTML=list.map(function(it){
      var url=it.url||'#';var target=url==='#'?'':' target="_blank" rel="noopener"';
      var pub=it.published_at?'· '+it.published_at:'';
      var imp=it.important?' news-important':'';
      var badge=it.important?'<span class="news-badge">重要</span>':'';
      var ch=it.channel?'<span class="news-chan-tag '+_chanCls(it.channel)+'">'+it.channel+'</span>':'';
      return '<div class="news-item'+imp+'"><div class="news-meta"><span class="news-source">'+(it.source_name||'来源未知')+'</span>'+ch+badge+'<span>'+pub+'</span></div><a href="'+url+'" data-url="'+url+'"'+target+'>'+(it.title||'')+'</a><div class="news-summary">'+(it.summary||'')+'</div></div>';
    }).join('');
    el.onclick=function(ev){var a=ev&&ev.target&&ev.target.closest?ev.target.closest('a[data-url]'):null;if(!a)return;var u=a.getAttribute('data-url')||'';if(!u||u==='#'||u.indexOf('http')!==0){ev.preventDefault();return;}ev.preventDefault();try{window.open(u,'_blank','noopener');}catch(err){window.location.href=u;}};
  }
function fetchNews(){
  if(!serverOnline)return;
  var el=document.getElementById('newsList');
  if(el)el.innerHTML='<div class="news-loading">正在从多源聚合实时新闻...</div>';
  _fetchJSON('news',BASE+'/api/news?limit=26&refresh=1',25000).then(function(d){
    _newsItems=d.news||[];
    var src=d.sources||{};
    var L={jin10:'金十数据',wallstreetcn:'见闻快讯',wscn_articles:'见闻深度',wscn_hot:'见闻热文',eastmoney_news:'东方财富',sina_rss:'新浪RSS'};
    var srcHtml='';
    for(var k in L){if(!(k in src))continue;srcHtml+='<span class="'+(src[k]?'source-ok':'source-fail')+'">● '+L[k]+'</span> ';}
    var sel=document.getElementById('newsSourceStatus');
    if(sel)sel.innerHTML='数据源状态: '+srcHtml+' | 获取于 '+(d.fetched_at||'--');
    if(!_newsItems.length){if(el)el.innerHTML='<div class="news-loading">暂无新闻或新闻源暂不可达，请稍后刷新</div>';return;}
    renderNewsChannels();renderNewsList();
  }).catch(function(e){
    var el2=document.getElementById('newsList');
    if(el2)el2.innerHTML='<div class="news-loading">新闻获取失败: '+((e&&e.message)||e)+'</div>';
  });
}
function loadLiveKline(cid,tf){var items=livePanels[cid];if(!items||!serverOnline)return;var chart=echartsInstances[cid];if(chart)chart.showLoading('加载数据',{text:'获取实时行情...',color:'#58a6ff',textColor:'#8b949e',maskColor:'rgba(22,27,34,0.8)'});var promises=items.map(function(it,idx){return _fetchJSON('kline_'+cid+'_'+idx,BASE+'/api/kline?name='+encodeURIComponent(it[0])+'&tf='+tf+'&refresh=1',20000).catch(function(){return null;});});Promise.all(promises).then(function(results){if(chart)chart.hideLoading();var kdata={};var xLabels=[];results.forEach(function(kl,i){if(kl&&kl.length>0){kdata[items[i][1]]=kl;if(xLabels.length===0){xLabels=kl.map(function(k){if(typeof k.time==='number'){var d=new Date(k.time);return(d.getMonth()+1)+'/'+d.getDate()+' '+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0');}return k.time;});}}});chartDataStore[cid].liveKline=kdata;chartDataStore[cid].liveXLabels=xLabels;if(Object.keys(kdata).length>0){renderLiveChart(cid);}}).catch(function(){if(chart)chart.hideLoading();});}
function renderLiveChart(cid){var d=chartDataStore[cid];if(!d||!d.liveKline)return;var chart=echartsInstances[cid];if(!chart){chart=echarts.init(document.getElementById('chart_'+cid));echartsInstances[cid]=chart;}var xLabels=d.liveXLabels||[];var series=[];for(var sn in d.liveKline){var kl=d.liveKline[sn];series.push({name:sn,type:'line',data:kl.map(function(k){return k.close;}),smooth:true,symbol:'none',lineStyle:{width:2}});}var opt={backgroundColor:'transparent',title:{text:d.title,textStyle:{color:'#58a6ff',fontSize:14}},tooltip:{trigger:'axis',axisPointer:{type:'cross'},backgroundColor:'rgba(22,27,34,0.95)',borderColor:'#30363d',textStyle:{color:'#c9d1d9'},formatter:function(p){var s=p[0].axisValue+'<br/>';p.forEach(function(it){var v=it.data;if(Array.isArray(v)){s+=it.marker+it.seriesName+' O:'+v[0].toFixed(4)+' H:'+v[3].toFixed(4)+' L:'+v[2].toFixed(4)+' C:'+v[1].toFixed(4)+'<br/>';}else{s+=it.marker+it.seriesName+' '+parseFloat(v).toFixed(4)+'<br/>';}});return s;}},legend:{data:Object.keys(d.liveKline),textStyle:{color:'#8b949e',fontSize:11},top:30,type:'scroll'},grid:{left:'8%',right:'12%',bottom:'15%',top:80},dataZoom:[{type:'slider',xAxisIndex:0,bottom:10,height:20,backgroundColor:'#161b22',fillerColor:'#30363d',textStyle:{color:'#8b949e'}},{type:'inside'}],xAxis:{type:'category',data:xLabels,axisLine:{lineStyle:{color:'#30363d'}},axisLabel:{color:'#8b949e',fontSize:10}},yAxis:{type:'value',scale:true,axisLine:{lineStyle:{color:'#30363d'}},axisLabel:{color:'#8b949e'},splitLine:{lineStyle:{color:'#21262d'}}},series:series,color:d.colors};chart.setOption(opt,true);if(highlightedSeries[cid]){var sel={};for(var n in d.liveKline){sel[n]=(n===highlightedSeries[cid]);}chart.setOption({legend:{selected:sel}});}}
function toggleAutoUpdate(){var btn=document.getElementById('autoUpdateBtn');if(autoTimer){clearInterval(autoTimer);autoTimer=null;btn.classList.remove('active');document.getElementById('autoBtnText').textContent='自动更新(5分钟)';document.getElementById('liveDot').classList.add('off');}else{if(!serverOnline){alert('服务器未连接！\\n请双击运行「启动全球金融日报APP.bat」启动实时数据服务器, 再点此开启自动更新。');return;}doFullUpdate();autoTimer=setInterval(doFullUpdate,300000);btn.classList.add('active');document.getElementById('autoBtnText').textContent='停止更新';document.getElementById('liveDot').classList.remove('off');}}
function updateHeaderDateFromStatus(){
  if(!serverOnline)return;
  fetch(BASE+'/api/status',{cache:'no-store'}).then(function(r){return r.json();}).then(function(d){
    var dataDate=d.data_date||'';
    var hd=document.getElementById('headerDataDate'); if(hd && dataDate && hd.textContent!==dataDate) hd.textContent=dataDate;
  }).catch(function(e){console.warn('updateHeaderDateFromStatus:',e);});
}
function doFullUpdate(){updateHeaderDateFromStatus();fetchQuotes();fetchCalendar();fetchNetworkTime();fetchMacro();fetchAdvanced();fetchNews();for(var cid in livePanels){var tf=chartTimeframe[cid]||'daily';loadLiveKline(cid,tf);}}
// 切回本标签页时若数据已超过30秒未刷新, 自动补一次刷新(避免看到陈旧行情)
document.addEventListener('visibilitychange',function(){if(!document.hidden&&serverOnline&&(Date.now()-_lastQuotesAt>30000))doFullUpdate();});
function manualUpdate(){if(!serverOnline){alert('服务器未连接！\\n请双击运行「启动全球金融日报APP.bat」, 然后在浏览器打开 http://localhost:8800/');return;}doFullUpdate();}
function fetchCalendar(){
_fetchJSON('calendar',BASE+'/api/calendar?refresh=1',20000).then(function(data){
if(!data||typeof data!=='object')return;
var td=document.getElementById('calTodayDate');if(td&&data.curr_date)td.textContent=data.curr_date;
try{updateCalendarChart(data);}catch(e){console.error('updateCalendarChart error:',e);}
try{renderCalendarTable(data);}catch(e){console.error('renderCalendarTable error:',e);}  // 动态重绘+到点高亮
}).catch(function(e){console.warn('fetchCalendar:',e);});}
// ---- 财经日历表格: 由 /api/calendar 实时数据动态渲染 ----
var _seenReleased = {};
function _calKey(it){return (it.time||'')+'|'+(it.country||'')+'|'+(it.event||'');}
function _calImpactHtml(imp){
  if(imp==='high')return '<span class="tag-high">高</span>';
  if(imp==='medium')return '<span class="tag-mid">中</span>';
  return '<span style="color:#8b949e">低</span>';}
function _calActualHtml(it){
  var a=it.actual, f=it.forecast, u=it.unit||'';
  if(a===null||a===undefined){
    if(it.just_released) return '<span class="flat" style="font-style:italic;color:#e3b341">已到时间·待取数</span>';
    return '<span class="flat" style="font-style:italic">待公布</span>';}
  var cls='flat';
  if(f!==null&&f!==undefined){cls = a>f?'pos':(a<f?'neg':'flat');}
  return '<span class="'+cls+'">'+a+u+'</span>';}
function _calValHtml(v,u){if(v===null||v===undefined)return '<span class="flat">-</span>';return v+(u||'');}
function _calRowHtml(it){
  var u=it.unit||'';
  var flash = (it.just_released && !_seenReleased[_calKey(it)]) ? ' just-released':'';
  if(it.just_released) _seenReleased[_calKey(it)]=true;
  var src = it.source ? '<span class="src-badge" title="官方权威源实时取数">'+it.source+'</span>' : '';
  return '<tr class="cal-row'+flash+'"><td style="white-space:nowrap">'+it.time+'</td><td>'+it.country+'</td><td style="text-align:left">'+src+it.event+'</td><td class="cal-actual" style="font-weight:600">'+_calActualHtml(it)+'</td><td>'+_calValHtml(it.forecast,u)+'</td><td>'+_calValHtml(it.previous,u)+'</td><td>'+_calImpactHtml(it.impact)+'</td><td style="color:#8b949e;font-size:12px;text-align:left">'+(it.note||'')+'</td></tr>';}
function renderCalendarTable(data){
  data = data || (chartDataStore['econ'] && chartDataStore['econ'].calData);
  if(!data)return;
  var map={'today':'cal-tbody-today','week':'cal-tbody-week','future':'cal-tbody-future'};
  ['today','week','future'].forEach(function(sec){
    var tb=document.getElementById(map[sec]);
    if(!tb)return;
    var arr=data[sec]||[];
    tb.innerHTML = arr.map(_calRowHtml).join('');
  });
  // 同步分段按钮计数
  var tN=(data.today||[]).length, wN=(data.week||[]).length, fN=(data.future||[]).length;
  var bAll=document.querySelector('[data-cal-section="all"]'), bT=document.querySelector('[data-cal-section="today"]'), bW=document.querySelector('[data-cal-section="week"]'), bF=document.querySelector('[data-cal-section="future"]');
  if(bAll)bAll.textContent='全部 ('+(tN+wN+fN)+')';
  if(bT)bT.textContent='当日 ('+tN+')';
  if(bW)bW.textContent='已公布 ('+wN+')';
  if(bF)bF.textContent='待公布 ('+fN+')';
  // 实时权威源状态（fxmacrodata: BLS/BEA/Census/EIA 官方口径）
  var ls = data.live_sources && data.live_sources.fxmacrodata;
  var noteEl = document.getElementById('calLiveNote');
  if(noteEl && ls){
    var srcs = Object.keys(ls.sources||{}).map(function(k){return ls.sources[k];}).filter(function(v,i,a){return v&&a.indexOf(v)===i;});
    if(ls.cal_ok || ls.filled>0){
      noteEl.innerHTML = '<span class="mini">LIVE·官方</span> 美国实际值实时取数来源: '+(srcs.join(' / ')||'BLS·BEA·Census·EIA')+' · 本次刷新回填 <b>'+ls.filled+'</b> 项 · 官方发布日历补充 <b>'+ls.added+'</b> 项';
      noteEl.style.display='flex';
    } else {
      noteEl.style.display='none';
    }
  }
}
function initCalendarChart(payload){if(!payload||!payload.today&&!payload.week&&!payload.future){console.warn('initCalendarChart: invalid payload');return;}
chartDataStore['econ']={calData:payload,calSection:'all',calType:'bar',lastLabels:[],lastItems:[]};
var el=document.getElementById('chart_econ');
if(!el){console.warn('chart_econ container not found');return;}
if(!echartsInstances['econ']){echartsInstances['econ']=echarts.init(el);}else if(echartsInstances['econ'].dispose){echartsInstances['econ'].dispose();echartsInstances['econ']=echarts.init(el);}
try{renderCalendarChart('econ');}catch(e){console.error('initCalendarChart render error:',e);}}
function renderCalendarChart(cid){
var st=chartDataStore[cid];if(!st)return;
if((st.calType||'bar')==='line')return renderCalendarLineChart(cid);
var chart=echartsInstances[cid];if(!chart)return;
var section=st.calSection||'all';
var items=section==='today'?st.calData.today:section==='week'?st.calData.week:section==='future'?st.calData.future:st.calData.today.concat(st.calData.week, st.calData.future);
if(!items||items.length===0)return;
var labels=items.map(function(it){
var ev=it.event||'';
var prefix=(it.country||'');
var max=section==='all'?8:12;
if(ev.length>max)ev=ev.substring(0,max)+'…';
return prefix+' '+ev;
});
var prev=items.map(function(it){return(it.previous===null||it.previous===undefined)?null:it.previous;});
var fcast=items.map(function(it){return(it.forecast===null||it.forecast===undefined)?null:it.forecast;});
var act=items.map(function(it){return(it.actual===null||it.actual===undefined)?null:it.actual;});
function barColor(p){var it=items[p.dataIndex];if(!it||it.actual===null||it.actual===undefined)return '#3c4149';
if(it.forecast!==null&&it.forecast!==undefined){if(it.actual>it.forecast)return '#ff4d4f';if(it.actual<it.forecast)return '#52c41a';}
return '#8b949e';}
var tipFmt=function(p){var it=items[p.dataIndex];if(!it)return'';var u=it.unit||'';
var s=(it.time||'')+' '+(it.country||'')+' '+(it.event||'')+'<br/>';
s+='<b>实际:</b> '+(it.actual!==null&&it.actual!==undefined?'<b>'+it.actual+u+'</b>':'<span style="color:#8b949e;font-style:italic">待公布</span>')+'<br/>';
s+='预测: '+(it.forecast!==null&&it.forecast!==undefined?it.forecast+u:'-')+'<br/>';
s+='前值: '+(it.previous!==null&&it.previous!==undefined?it.previous+u:'-')+'<br/>';
s+='影响: '+(it.impact||'')+(it.note?' | '+it.note:'');
return s;};
var maxLen=labels.reduce(function(m,s){return Math.max(m,s.length);},0);
var gridLeft=Math.min(32,Math.max(18,Math.ceil(maxLen*0.8)));
var chartHeight=section==='all'?Math.max(550,items.length*22):Math.max(400,items.length*30);
var el=document.getElementById('chart_'+cid);
if(el){el.style.height=chartHeight+'px';chart.resize();}
var opt={backgroundColor:'transparent',animation:false,
title:{text:'财经日历: 实际值/预测值/前值对比',textStyle:{color:'#58a6ff',fontSize:14}},
tooltip:{trigger:'item',backgroundColor:'rgba(22,27,34,0.95)',borderColor:'#30363d',textStyle:{color:'#c9d1d9'},formatter:tipFmt},
legend:{data:['前值','预测值','实际值'],textStyle:{color:'#8b949e',fontSize:11},top:30},
grid:{left:gridLeft+'%',right:'8%',bottom:'5%',top:70,containLabel:true},
xAxis:{type:'value',axisLine:{lineStyle:{color:'#30363d'}},axisLabel:{color:'#8b949e'},splitLine:{lineStyle:{color:'#21262d'}}},
yAxis:{type:'category',data:labels,axisLine:{lineStyle:{color:'#30363d'}},axisLabel:{color:'#c9d1d9',fontSize:10,interval:0,formatter:function(v){return v;}}},
series:[
{name:'前值',type:'bar',data:prev,itemStyle:{color:'#6e7681'}},
{name:'预测值',type:'bar',data:fcast,itemStyle:{color:'#58a6ff'}},
{name:'实际值',type:'bar',data:act,itemStyle:{color:barColor},label:{show:true,position:'right',color:'#c9d1d9',fontSize:10,formatter:function(p){var it=items[p.dataIndex];if(!it||it.actual===null||it.actual===undefined)return'';return it.actual+(it.unit||'');}}}]};
chart.setOption(opt,true);
st.lastLabels=labels;
st.lastItems=items;}
function switchCalendarSection(cid,section){var st=chartDataStore[cid];if(!st)return;st.calSection=section;
var tb=document.querySelector('[data-toolbar="'+cid+'"]');if(tb)tb.querySelectorAll('[data-cal-section]').forEach(function(b){b.classList.toggle('active',b.dataset.calSection===section);});
renderCalendarChart(cid);}
function switchCalendarType(cid,type){var st=chartDataStore[cid];if(!st)return;st.calType=type;
var tb=document.querySelector('[data-toolbar="'+cid+'"]');if(tb){tb.querySelectorAll('[data-cal-type]').forEach(function(b){b.classList.toggle('active',b.dataset.calType===type);});
var sg=tb.querySelector('[data-cal-section-group]');if(sg){sg.style.display=(type==='bar')?'flex':'none';
sg.querySelectorAll('[data-cal-section]').forEach(function(b){b.classList.toggle('active',b.dataset.calSection===st.calSection);});}}
renderCalendarChart(cid);}
function renderCalendarLineChart(cid){
var st=chartDataStore[cid];if(!st)return;
var chart=echartsInstances[cid];if(!chart)return;
var section=st.calSection||'all';
var allItems=section==='today'?st.calData.today:section==='week'?st.calData.week:section==='future'?st.calData.future:st.calData.today.concat(st.calData.week, st.calData.future);
var histItems=allItems.filter(function(it){return it.history&&Array.isArray(it.history.data)&&it.history.data.length>=2;});
if(!histItems.length){try{chart.clear();}catch(e){}return;}
var dates=[];
histItems.forEach(function(it){(it.history.data||[]).forEach(function(p){if(dates.indexOf(p.date)===-1)dates.push(p.date);});});
dates.sort();
var el=document.getElementById('chart_'+cid);
if(el){el.style.height='500px';chart.resize();}
var baseColors=['#58a6ff','#f0883e','#ff7b72','#d2a8ff','#7ee787','#56d4dd','#ffa657','#e3b341','#a371f7','#79c0ff'];
var series=histItems.map(function(it,idx){
var h=it.history;
var color=h.color||baseColors[idx%baseColors.length];
var pts=(h.data||[]).map(function(p){return[p.date,p.actual===null||p.actual===undefined?null:p.actual];});
var lbl=(it.country||'')+' '+(it.event||'');
return {name:lbl,type:'line',data:pts,smooth:true,symbol:'circle',symbolSize:6,connectNulls:false,lineStyle:{width:2.5,color:color},itemStyle:{color:color},emphasis:{focus:'series'},label:{show:false}};
});
var tipFmt=function(p){var it=histItems[p.seriesIndex];if(!it)return p.name+': '+p.value;var h=it.history;var u=h.unit||'';
var raw=(h.data||[]).filter(function(x){return x.date===p.data[0];})[0]||{};
return'<b>'+(it.country||'')+' '+(it.event||'')+'</b> ('+u+')<br/>'+'日期: '+p.data[0]+'<br/>'+'实际: <b>'+(p.value===null||p.value===undefined?'<span style="color:#8b949e">待公布</span>':p.value+u)+'</b><br/>'+'预测: '+(raw.forecast!==null&&raw.forecast!==undefined?raw.forecast+u:'-');};
var opt={backgroundColor:'transparent',animation:false,
title:{text:'财经日历: 2026 YTD 指标公布趋势',subtext:histItems.length+'个有历史数据的指标 | Jan→Jul 2026',textStyle:{color:'#58a6ff',fontSize:14},subtextStyle:{color:'#8b949e',fontSize:11}},
tooltip:{trigger:'axis',backgroundColor:'rgba(22,27,34,0.95)',borderColor:'#30363d',textStyle:{color:'#c9d1d9'},formatter:tipFmt},
legend:{type:'scroll',top:30,textStyle:{color:'#8b949e',fontSize:11},data:series.map(function(s){return s.name;})},
grid:{left:'8%',right:'8%',bottom:'12%',top:80,containLabel:true},
xAxis:{type:'category',data:dates,axisLine:{lineStyle:{color:'#30363d'}},axisLabel:{color:'#8b949e',fontSize:10,interval:0},splitLine:{lineStyle:{color:'#21262d'}}},
yAxis:{type:'value',axisLine:{lineStyle:{color:'#30363d'}},axisLabel:{color:'#8b949e'},splitLine:{lineStyle:{color:'#21262d'}}},
dataZoom:[{type:'inside',start:0,end:100},{type:'slider',height:18,bottom:30,backgroundColor:'rgba(22,27,34,0.6)',fillerColor:'rgba(88,166,255,0.2)',borderColor:'#30363d',textStyle:{color:'#8b949e'}}],
series:series};
chart.setOption(opt,true);
st.lastLabels=dates;
st.lastItems=histItems;}
function toggleCalendarSeries(cid){
var chart=echartsInstances[cid];if(!chart)return;
var st=chartDataStore[cid];if(!st)return;
var seriesNames=[];
if((st.calType||'bar')==='line'&&st.lastItems){
st.lastItems.forEach(function(it){seriesNames.push((it.country||'')+' '+(it.event||''));});
}else{return;}
var legend=chart.getOption().legend;
if(legend&&legend[0]){
var selected=legend[0].selected||{};
var allSelected=Object.keys(selected).every(function(k){return selected[k]!==false;});
seriesNames.forEach(function(name){selected[name]=allSelected?false:true;});
chart.setOption({legend:{selected:selected}});
}}
function updateCalendarChart(data){
var st=chartDataStore['econ'];
if(!st||!st.calData)return;
if(data.today&&Array.isArray(data.today))st.calData.today=data.today;
if(data.week&&Array.isArray(data.week))st.calData.week=data.week;
if(data.future&&Array.isArray(data.future))st.calData.future=data.future;
try{
if((st.calType||'bar')==='line')renderCalendarLineChart('econ');
else renderCalendarChart('econ');
}catch(e){console.error('Calendar chart render error:',e);}}
function initGauge(cid,title,value,sub){
var el=document.getElementById('chart_'+cid);if(!el)return;
if(!echartsInstances[cid]){echartsInstances[cid]=echarts.init(el);}else if(echartsInstances[cid].dispose){echartsInstances[cid].dispose();echartsInstances[cid]=echarts.init(el);}
var opt={backgroundColor:'transparent',animation:false,
title:{text:title,subtext:sub||'',textStyle:{color:'#58a6ff',fontSize:14},subtextStyle:{color:'#8b949e',fontSize:11},left:'center'},
series:[{type:'gauge',min:0,max:1,splitNumber:10,radius:'78%',center:['50%','60%'],
axisLine:{lineStyle:{color:[[0.45,'#52c41a'],[0.55,'#e3b341'],[1,'#ff4d4f']],width:14}},
pointer:{itemStyle:{color:'#e3b341'},length:'62%'},
axisTick:{distance:-14,length:6,lineStyle:{color:'#0d1117'}},
splitLine:{distance:-20,length:14,lineStyle:{color:'#0d1117',width:2}},
axisLabel:{color:'#8b949e',fontSize:10,distance:26,formatter:function(v){return v.toFixed(1);}},
detail:{formatter:function(v){return v.toFixed(3);},color:'#e3b341',fontSize:20,offsetCenter:[0,'68%']},
data:[{value:value,name:'IBS (0-1)'}]}]};
echartsInstances[cid].setOption(opt,true);}
setTimeout(checkServer,500);
""".replace("__COLORS__", json.dumps(C)).replace("__LIVE_PANELS__", json.dumps(LIVE_PANELS, ensure_ascii=False))
H.append(JS)

# Chart configs — hist panels use real 2026 YTD daily series; others use monthly fallback
hist_panels = [
    ("forex","2026年外汇走势 (年初至今·日线)","hist_forex","chart_forex"),
    ("commodities","2026年大宗商品走势 (年初至今·日线)","hist_commodities","chart_commodities"),
    ("indices","2026年全球股指走势 (年初至今·日线)","hist_indices","chart_indices"),
]
for cid,title,hkey,ckey in hist_panels:
    hd = D.get(hkey) or {}
    if hd.get("dates") and hd.get("series"):
        H.append(f"\ninitHistChart('{cid}', '{title}', {json.dumps(hd['dates'], ensure_ascii=False)}, {json.dumps(hd['series'], ensure_ascii=False)});")
    else:
        H.append(f"\ninitChart('{cid}', '{title}', {json.dumps(D.get(ckey, {}), ensure_ascii=False)});")

chart_configs = [
    ("bonds","2026年主要国债收益率YTD走势 (%)","chart_bonds"),
    ("ois_irs","2026年OIS/IRS利率YTD走势 (%)","chart_ois_irs"),
    ("cb","2026年主要央行政策利率走势 (%)","chart_rates"),
    ("analysis","2026年大类资产YTD综合走势","chart_combined"),
    ("macro","2026年宏观金融指标YTD走势","chart_macro"),
]
for cid,title,ckey in chart_configs:
    cdata = D.get(ckey, {})
    H.append(f"\ninitChart('{cid}', '{title}', {json.dumps(cdata, ensure_ascii=False)});")

# Calendar chart (custom grouped bar chart for financial calendar module)
_cal_chart_payload = {
    "today": _cal_today,
    "week": _cal_week,
    "future": _cal_future,
}
_cal_payload_json = json.dumps(_cal_chart_payload, ensure_ascii=False)
# 关键修复：renderCalendarTable 与 initCalendarChart 解耦。
# 即使 ECharts(CDN)加载失败导致 initCalendarChart 抛错，表格仍用静态payload立即渲染；
# 且采用有参调用，不依赖 chartDataStore 间接引用，保证日历在任何情况下都显示。
H.append(f"\ntry{{initCalendarChart({_cal_payload_json});}}catch(e){{console.error('initCalendarChart error:',e);}}\nrenderCalendarTable({_cal_payload_json});")

# Advanced charts (line/bar/gauge for every section)
def _ext_num(s):
    import re as _re
    if s is None: return None
    if isinstance(s, (int, float)): return float(s)
    _m = _re.search(r'-?\d[\d,]*\.?\d*', str(s))
    return float(_m.group().replace(',', '')) if _m else None

# 进阶数据图表的初始化已移至前端 JS：fetchAdvanced() -> renderAdvanced() 实时填充各容器后调用 initAdvChart。
# 此处不再做构建期静态初始化，避免对尚未渲染的容器初始化 echarts 报错。

H.append('\n</script>\n</body>\n</html>')

html = '\n'.join(H)
with open(HTML_OUT, 'w', encoding='utf-8') as f:
    f.write(html)
print(f"[OK] HTML: {HTML_OUT} ({len(html):,} chars)")

# ===================== Build Excel =====================
import xlsxwriter
wb = xlsxwriter.Workbook(XLSX_OUT, {'strings_to_numbers': False})
fh = wb.add_format({'bold':True,'bg_color':'#1F6FEB','font_color':'#FFFFFF','border':1,'align':'center','valign':'vcenter','font_size':11})
fc_cat = wb.add_format({'bold':True,'border':1,'align':'center','font_size':10,'bg_color':'#F0F0F0'})
fc_t = wb.add_format({'border':1,'align':'left','font_size':10,'text_wrap':True})
fc_c = wb.add_format({'border':1,'align':'center','font_size':10})
fc_n2 = wb.add_format({'border':1,'align':'right','font_size':10,'num_format':'0.00'})
fc_n4 = wb.add_format({'border':1,'align':'right','font_size':10,'num_format':'0.0000'})
fc_p = wb.add_format({'border':1,'align':'right','font_size':10,'num_format':'+0.00;-0.00','font_color':'#FF0000'})
fc_n = wb.add_format({'border':1,'align':'right','font_size':10,'num_format':'+0.00;-0.00','font_color':'#00AA00'})
fc_f = wb.add_format({'border':1,'align':'right','font_size':10,'num_format':'0.00','font_color':'#888888'})
def wn(ws,r,c,v,fmt=None):
    if v is None: ws.write(r,c,"-",fc_c)
    else:
        try: ws.write_number(r,c,float(v),fmt or fc_n2)
        except (ValueError, TypeError): ws.write(r,c,str(v),fc_c)
def wc(ws,r,c,v):
    if v is None: ws.write(r,c,"-",fc_c)
    elif v>0: wn(ws,r,c,v,fc_p)
    elif v<0: wn(ws,r,c,v,fc_n)
    else: wn(ws,r,c,v,fc_f)
def sheet(name, headers, rows, col_widths, row_fn, note=None):
    ws = wb.add_worksheet(name)
    for i,w in enumerate(col_widths): ws.set_column(i,i,w)
    start = 0
    if note:
        nfmt = wb.add_format({'italic':True,'font_color':'#E3B341','align':'left','font_size':10,'bg_color':'#FFF8E1','border':1})
        ws.merge_range(0,0,0,len(headers)-1, note, nfmt)
        start = 1
    for c,h in enumerate(headers): ws.write(start,c,h,fh)
    for r,row in enumerate(rows, start+1): row_fn(ws,r,row)
    if note: ws.freeze_panes(start+1, 0)
    return ws

CO_NOTE = f"数据截止时间: {CUTOFF}"
sheet("全球概览",["类别","品种","价格/收益率","日涨跌幅(%)","备注"],D["overview_items"],[10,28,14,14,35],
    lambda ws,r,x:(ws.write(r,0,x[0],fc_cat),ws.write(r,1,x[1],fc_t),wn(ws,r,2,x[2],fc_n4),wc(ws,r,3,x[3]),ws.write(r,4,x[4],fc_t)), note=CO_NOTE)
sheet("外汇",["品种(中文)","代码","汇率/价格","日变化(%)","方向","分析备注"],D["forex_data"],[22,12,14,12,8,35],
    lambda ws,r,x:(ws.write(r,0,x[0],fc_t),ws.write(r,1,x[1],fc_c),wn(ws,r,2,x[2],fc_n4),wc(ws,r,3,x[3]),ws.write(r,4,"涨" if x[3]>0 else "跌" if x[3]<0 else "平",fc_c),ws.write(r,5,x[4],fc_t)), note=CO_NOTE)
sheet("大宗商品",["品种","代码","价格","涨跌幅(%)","单位","走势","分析备注"],D["commodity_data"],[18,10,14,12,14,8,35],
    lambda ws,r,x:(ws.write(r,0,x[0],fc_t),ws.write(r,1,x[1],fc_c),wn(ws,r,2,x[2],fc_n2),wc(ws,r,3,x[3]),ws.write(r,4,x[4],fc_c),ws.write(r,5,"涨" if x[3]>0 else "跌" if x[3]<0 else "平",fc_c),ws.write(r,6,x[5],fc_t)), note=CO_NOTE)
sheet("债券",["国债品种","代码","收益率(%)","日变化(bp)","走势"],D["bond_data"],[22,10,14,12,10],
    lambda ws,r,x:(ws.write(r,0,x[0],fc_t),ws.write(r,1,x[1],fc_c),wn(ws,r,2,x[2],fc_n4),wc(ws,r,3,x[3]),ws.write(r,4,"上行" if x[3]>0 else "下行" if x[3]<0 else "持平",fc_c)), note=CO_NOTE)
sheet("利率掉期",["利率类型","期限","利率(%)","日变化(bp)","备注"],D["ois_irs_data"],[14,10,14,12,25],
    lambda ws,r,x:(ws.write(r,0,x[0],fc_cat),ws.write(r,1,x[1],fc_c),wn(ws,r,2,x[2],fc_n4),wc(ws,r,3,x[3]),ws.write(r,4,x[4],fc_t)), note=CO_NOTE)
sheet("股指",["指数名称","代码","收盘价","涨跌幅(%)","涨跌","市场","分析备注"],D["index_data"],[24,10,14,12,8,12,35],
    lambda ws,r,x:(ws.write(r,0,x[0],fc_t),ws.write(r,1,x[1],fc_c),wn(ws,r,2,x[2],fc_n2),wc(ws,r,3,x[3]),ws.write(r,4,"涨" if x[3]>0 else "跌" if x[3]<0 else "平",fc_c),ws.write(r,5,x[4],fc_c),ws.write(r,6,x[5],fc_t)), note=CO_NOTE)
_cal = D.get("economic_calendar", {})
_released = _cal.get("released", [])
_upcoming = _cal.get("upcoming", [])
_upcoming_rows = [[it["time"],it["country"],it["event"],it.get("actual"),it.get("forecast"),it.get("previous"),it.get("unit",""),it.get("impact",""),it.get("note","")] for it in _upcoming]
sheet("财经日历-待公布",["时间","国家","事件","实际值","预测值","前值","单位","影响","备注"],_upcoming_rows,[12,10,28,12,12,12,8,6,30],
    lambda ws,r,x:(ws.write(r,0,x[0],fc_c),ws.write(r,1,x[1],fc_c),ws.write(r,2,x[2],fc_t),
    wn(ws,r,3,x[3]) if x[3] is not None else ws.write(r,3,"待公布",fc_c),
    wn(ws,r,4,x[4]) if x[4] is not None else ws.write(r,4,"-",fc_c),
    wn(ws,r,5,x[5]) if x[5] is not None else ws.write(r,5,"-",fc_c),
    ws.write(r,6,x[6],fc_c),ws.write(r,7,x[7],fc_c),ws.write(r,8,x[8],fc_t)),
    note=f"当日 {_cal.get('curr_date','')} 待公布数据")
_released_rows = [[it["time"],it["country"],it["event"],it.get("actual"),it.get("forecast"),it.get("previous"),it.get("unit",""),it.get("impact",""),it.get("note","")] for it in reversed(_released)]
sheet("财经日历-已公布",["时间","国家","事件","实际值","预测值","前值","单位","影响","备注"],_released_rows,[12,10,28,12,12,12,8,6,30],
    lambda ws,r,x:(ws.write(r,0,x[0],fc_c),ws.write(r,1,x[1],fc_c),ws.write(r,2,x[2],fc_t),
    wn(ws,r,3,x[3]) if x[3] is not None else ws.write(r,3,"待公布",fc_c),
    wn(ws,r,4,x[4]) if x[4] is not None else ws.write(r,4,"-",fc_c),
    wn(ws,r,5,x[5]) if x[5] is not None else ws.write(r,5,"-",fc_c),
    ws.write(r,6,x[6],fc_c),ws.write(r,7,x[7],fc_c),ws.write(r,8,x[8],fc_t)),
    note=f"上一工作日 {_cal.get('prev_date','')} 已公布数据")
sheet("央行动态",["央行","核心动态","详细内容","信息来源","备注"],D["central_bank_data"],[18,30,60,18,30],
    lambda ws,r,x:(ws.write(r,0,x[0],fc_cat),ws.write(r,1,x[1],fc_t),ws.write(r,2,x[2],fc_t),ws.write(r,3,x[3],fc_c),ws.write(r,4,x[4],fc_t)))
sheet("宏观数据",["指标名称","数值","日变化","单位","备注"],D["macro_data"],[28,14,12,8,30],
    lambda ws,r,x:(ws.write(r,0,x[0],fc_t),wn(ws,r,1,x[1],fc_n4),wc(ws,r,2,x[2]),ws.write(r,3,x[3],fc_c),ws.write(r,4,x[4],fc_t)), note=CO_NOTE)
sheet("重点提示",["事件","类别","详细描述","影响评估","风险等级"],D["anomaly_data"],[30,14,50,45,8],
    lambda ws,r,x:(ws.write(r,0,x[0],fc_t),ws.write(r,1,x[1],fc_c),ws.write(r,2,x[2],fc_t),ws.write(r,3,x[3],fc_t),ws.write(r,4,x[4],wb.add_format({'border':1,'align':'center','bold':True,'bg_color':'#FF4444' if x[4]=="极高" else '#FFAA00','font_color':'#FFF' if x[4]=="极高" else '#000'}))))

# ===================== Advanced Excel sheets =====================
_tb = D.get("tips_breakeven", {}) or {}
if _tb:
    _tb_rows = []
    for _k, _nm in [("dfii10","10Y TIPS实际收益率"),("t10yie","10Y盈亏平衡通胀")]:
        _seg = _tb.get(_k, {}) or {}
        _tb_rows.append([_nm, _seg.get("latest"), _seg.get("date",""), _seg.get("note","")])
    sheet("进阶-TIPS",["指标","最新值(%)","数据日期","说明"],_tb_rows,[24,14,12,55],
        lambda ws,r,x:(ws.write(r,0,x[0],fc_t),wn(ws,r,1,x[1],fc_n4),ws.write(r,2,x[2],fc_c),ws.write(r,3,x[3],fc_t)),
        note=_tb.get("spread_note",""))
_ibs = D.get("dxy_ibs", {}) or {}
if _ibs:
    _ibs_rows = [["数据日期",_ibs.get("date","")],["最高",_ibs.get("high")],["最低",_ibs.get("low")],["收盘",_ibs.get("close")],["IBS值",_ibs.get("value")],["公式",_ibs.get("formula","")],["区间",_ibs.get("band","")],["说明",_ibs.get("note","")]]
    sheet("进阶-DXY_IBS",["项目","数值"],_ibs_rows,[12,60],
        lambda ws,r,x:(ws.write(r,0,x[0],fc_cat),wn(ws,r,1,x[1],fc_n2) if x[1] is None or isinstance(x[1],(int,float)) else ws.write(r,1,x[1],fc_t)))
_fx = D.get("fx_swap_data", [])
if _fx:
    sheet("进阶-外汇掉期",["货币对","期限","掉期点","备注"],_fx,[14,8,14,60],
        lambda ws,r,x:(ws.write(r,0,x[0],fc_cat),ws.write(r,1,x[1],fc_c),wn(ws,r,2,x[2],fc_n2),ws.write(r,3,x[3],fc_t)),
        note=D.get("fx_swap_note",""))
_eer = D.get("eer_data", [])
if _eer:
    sheet("进阶-BIS有效汇率",["指数名称","最新值","月度变化","基准","备注"],_eer,[24,12,12,10,60],
        lambda ws,r,x:(ws.write(r,0,x[0],fc_t),wn(ws,r,1,x[1],fc_n2),wc(ws,r,2,x[2]),ws.write(r,3,x[3],fc_c),ws.write(r,4,x[4],fc_t)))
_cof = D.get("cofer_data", {}) or {}
if _cof:
    _cof_rows = [[c, p if p is not None else "-", cg if cg is not None else "-", nt] for c, p, cg, nt in _cof.get("items", [])]
    sheet("进阶-COFER",["货币","占比(%)","季度变化(pct pt)","备注"],_cof_rows,[16,12,18,55],
        lambda ws,r,x:(ws.write(r,0,x[0],fc_cat),wn(ws,r,1,x[1],fc_n2),ws.write(r,2,x[2],fc_c),ws.write(r,3,x[3],fc_t)),
        note=f"{_cof.get('date','')} | {_cof.get('total','')} | {_cof.get('note','')}")
_cot = D.get("cot_data", {}) or {}
if _cot:
    _cot_rows = [[a, b, c if c is not None else "-", d if d is not None else "-", e] for a, b, c, d, e in _cot.get("items", [])]
    sheet("进阶-COT持仓",["品种","头寸方向","净头寸","较上周变化","备注"],_cot_rows,[18,10,14,14,55],
        lambda ws,r,x:(ws.write(r,0,x[0],fc_t),ws.write(r,1,x[1],fc_c),wn(ws,r,2,x[2],fc_n2),wn(ws,r,3,x[3],fc_n2),ws.write(r,4,x[4],fc_t)),
        note=f"{_cot.get('date','')} | {_cot.get('note','')}")
_cbg = D.get("cb_gold_data", [])
if _cbg:
    sheet("进阶-央行购金",["期间","数量","同比/环比","备注"],_cbg,[20,14,20,55],
        lambda ws,r,x:(ws.write(r,0,x[0],fc_cat),ws.write(r,1,x[1],fc_c),ws.write(r,2,x[2],fc_c),ws.write(r,3,x[3],fc_t)),
        note=D.get("cb_gold_note",""))
_etf = D.get("etf_gold_data", [])
if _etf:
    sheet("进阶-黄金ETF",["期间","数量","流向","备注"],_etf,[20,14,16,55],
        lambda ws,r,x:(ws.write(r,0,x[0],fc_cat),ws.write(r,1,x[1],fc_c),ws.write(r,2,x[2],fc_c),ws.write(r,3,x[3],fc_t)),
        note=D.get("etf_gold_note",""))
_gd = D.get("gold_demand_data", {}) or {}
if _gd:
    _gd_rows = [[a, b, c, d] for a, b, c, d in _gd.get("items", [])]
    sheet("进阶-黄金需求",["项目","数值","同比/环比","备注"],_gd_rows,[32,16,24,55],
        lambda ws,r,x:(ws.write(r,0,x[0],fc_t),ws.write(r,1,x[1],fc_c),ws.write(r,2,x[2],fc_c),ws.write(r,3,x[3],fc_t)),
        note=f"{_gd.get('date','')} | {_gd.get('outlook','')}")
_oi = D.get("oil_data", {}) or {}
_wk = _oi.get("weekly", {}) or {}
if _wk.get("items"):
    sheet("进阶-EIA周度",["项目","实际值","预期","备注"],_wk["items"],[22,20,20,55],
        lambda ws,r,x:(ws.write(r,0,x[0],fc_t),ws.write(r,1,x[1],fc_c),ws.write(r,2,x[2],fc_c),ws.write(r,3,x[3],fc_t)),
        note=f"{_wk.get('date','')} | {_wk.get('api_note','')}")
_st = _oi.get("steo", {}) or {}
if _st.get("items"):
    sheet("进阶-EIA展望",["项目","预测","7月预测","备注"],_st["items"],[26,24,24,55],
        lambda ws,r,x:(ws.write(r,0,x[0],fc_t),ws.write(r,1,x[1],fc_c),ws.write(r,2,x[2],fc_c),ws.write(r,3,x[3],fc_t)),
        note=_st.get("date",""))
_ie = _oi.get("iea", {}) or {}
if _ie.get("items"):
    sheet("进阶-IEA石油",["项目","数值","对比上月","备注"],_ie["items"],[26,30,26,55],
        lambda ws,r,x:(ws.write(r,0,x[0],fc_t),ws.write(r,1,x[1],fc_c),ws.write(r,2,x[2],fc_c),ws.write(r,3,x[3],fc_t)),
        note=_ie.get("date",""))

wb.close()
xsize = os.path.getsize(XLSX_OUT)
print(f"[OK] Excel: {XLSX_OUT} ({xsize:,} bytes)")
print(f"Done! Date={DATE} | HTML={len(html):,}chars | Excel={xsize:,}bytes")
