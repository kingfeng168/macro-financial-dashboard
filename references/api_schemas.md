# API Payload 契约（前端对接参考）

所有端点返回 JSON，`Content-Type: application/json; charset=utf-8`，带 `no-cache` 头。

## GET /api/advanced?refresh=1
```jsonc
{
  "ok": true,
  "fetched_at": "2026-09-01 22:01:00",
  "source": "FRED + BIS",
  "sections": {
    "tips": {
      "live": true,
      "fetched_at": "...",
      "dfii10": {"value": 2.44, "date": "2026-09-01"},
      "t10yie": {"value": 2.31, "date": "2026-09-01"},
      "sofr":   {"value": 3.68, "date": "2026-09-01"},
      "spread_note": "10Y 盈亏平衡通胀 2.31% − 10Y TIPS 实际收益率 2.44% = 利差 -0.13% ...",
      "series": {
        "TIPS实际收益率(DFII10)": [["2026-08-03", 2.5], ...],
        "盈亏平衡通胀(T10YIE)":   [["2026-08-03", 2.3], ...]
      }
    },
    "oil":      {"live":true, "wti":{"value":83.9,"date":"..."}, "brent":{"value":87.1,"date":"..."},
                 "series":{"WTI原油":[[date,val],...],"Brent原油":[[date,val],...]}},
    "usd_index":{"live":true, "value":118.75, "date":"...",
                 "series":{"广义美元指数(DTWEXBGS)":[[date,val],...]},
                 "note":"DTWEXBGS = 贸易加权广义美元指数，DXY 权威代理"},
    "eer":      {"live":true,
                 "areas":[{"code":"US","name":"美元","neer":102.6,"neer_date":"2026-07",
                           "reer":108.2,"reer_date":"2026-07",
                           "neer_series":[[t,v],...],"reer_series":[[t,v],...]}, ... ],
                 "note":"BIS 有效汇率指数(2020=100)，月度"},
    // 以下均为 live:false 快照（来自 daily_data.json）
    "fx_swap":{}, "cofer":{}, "cot":{}, "cb_gold":{}, "etf_gold":{},
    "gold_demand":{}, "eia_oil":{}, "dxy_ibs":{}, "eia_iea_oil":{}
  }
}
```

## GET /api/macro?refresh=1
```jsonc
{
  "ok": true,
  "source": "BIS WS_CBPOL + World Bank API",
  "fetched_at": "...",
  "policy_rates": [{"country":"美元","code":"US","rate":4.5,"date":"2026-07","unit":"%"}, ...],
  "gdp_growth":   [{"country":"美元","code":"US","value":2.1,"date":"2025","unit":"%"}, ...],
  "cpi":          [{"country":"美元","code":"US","value":3.1,"date":"2026-06","unit":"%"}, ...]
}
```
注意：BIS 对欧洲央行代码是 **`XM`**（非 `EU`）；GDP 仅年度（无月度序列）。

## GET /api/calendar?refresh=1
```jsonc
{
  "today":  [ {time,country,flag,event,actual,forecast,previous,unit,impact,note,just_released?}, ... ],
  "week":   [ ... ],   // 当周已公布（本周一~周日）
  "future": [ ... ]    // 次日及以后待公布
}
```
前端 `fetchCalendar()` 把三数组渲染进 `cal-tbody-today/week/future` 三个 tbody；`actual` 为 `null` 且已过发布时间显示「已到时间·待取数」。

## GET /api/quotes?refresh=1
```jsonc
{
  "quotes": { "EUR/USD": {"price":1.085,"prevClose":1.084,"change":0.001,"changePct":0.09}, ... },
  "sources": {...}, "health": {...}, "fetched_at": "..."
}
```

## GET /api/itick
```jsonc
{
  "status": "ok",
  "state": {
    "enabled": true,          // false = 未配 ITICK_TOKEN，该源整体禁用
    "running": true,          // 后台轮询线程存活
    "base": "https://api-free.itick.org",
    "rpm": 5,                 // 每分钟调用上限（免费套餐 5）
    "symbols": 23,            // 已映射品种总数
    "cached": 23,             // 已缓存（有数据）品种数
    "ok": 35, "fail": 0, "throttled": 0,
    "last_error": "",
    "newest_age_sec": 12,     // 最新一条数据的年龄
    "oldest_age_sec": 128     // 最旧一条数据的年龄
  },
  "quotes": {
    "现货黄金": {
      "price": 4469.621, "prevClose": 4472.967, "change": -3.346, "changePct": -0.07,
      "source": "itick", "fetched_at": "2026-09-04 11:40:00",
      "itick_code": "XAUUSD", "itick_high": 4487.545, "itick_low": 4467.125,
      "itick_open": 4476.075, "itick_volume": 478567.1, "itick_ts": 1788492381002,
      "staleSec": 60
    }
  }
}
```

### `quote.itick` 子对象（挂在 `/api/quotes` 每个品种下）
| 字段 | 说明 |
|------|------|
| `price` / `code` | iTick 报价与品种代码 |
| `divPct` | 相对主源的涨跌分歧（%）。`null` 表示无法比对 |
| `preferred` | `true` = 该品种以 iTick 现货口径为准（已覆盖主源，见 `PREFER`） |
| `filled` | `true` = 主源全挂，由 iTick 补位 |
| `altPrice` / `altSource` | 仅 `preferred=true` 时存在：被覆盖的主源价及其来源（保留可比对） |
| `staleSec` | 快照年龄（秒） |

> `preferred` 仅对 `PREFER` 集合（现货黄金/现货白银）生效，且要求 `staleSec <= PREFER_MAX_STALE(600)`；
> 快照过期自动回落主源，不会因 iTick 限流导致行情中断。

## 前端约定（generate_report.py）
- `seriesMap` 标准格式：`{name:[[date, val], ...]}`（进阶/行情图通用）。
- `neonLine(cid, seriesMap, opt)`：`opt={colors:[...], yName, suffix, areaTop, height, glowColor, markLast}`。
- 自动刷新：`doFullUpdate()` 每 5 分钟触发 `fetchQuotes/fetchCalendar/fetchNetworkTime/fetchMacro/fetchAdvanced/fetchNews`；手动按钮各自独立触发。
- 红涨绿跌（中国惯例）；实时面板霓虹、快照面板素色。
