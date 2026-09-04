---
name: macro-financial-dashboard
description: "宏观金融信息仪表盘（全球金融日报）App 完整版。覆盖实时数据服务器 live_server.py（端口 8800，提供 /api/quotes /api/news /api/kline /api/calendar /api/time /api/status /api/macro /api/advanced 九大端点）、进阶数据实时抓取模块 advanced_data.py（FRED + BIS SDMX 免密钥实时源；EIA v2 REST 需免费 key；WGC 文章解析；IMF COFER SDMX 3.0 真机实时）；六大核心指标（CPI / 失业率 / COT / EIA 原油库存 / WGC 央行购金 / IMF COFER）已全部实时化、统一报告生成器 generate_report.py（HTML 霓虹仪表盘 + Excel 双产出）、多源行情聚合 data_aggregator.py（Frankfurter/Sina/Yahoo/华尔街见闻/金十）、财经日历 actual 回填 calendar_fetcher.py，以及三时段财经日历、实时宏观卡片、TIPS 利差/原油/广义美元/EER 四个霓虹实时图。本 skill 打包了本版本全部源码与示例数据，可直接运行。触发场景：生成全球金融日报、启动/重启实时服务器、查询或新增 API 端点、修改进阶数据/霓虹图表/财经日历/宏观模块、配置每日 22:00 自动化、排查 FRED/BIS 抓取问题。关键词：全球金融日报、live_server、advanced_data、generate_report、daily_data.json、财经日历、霓虹图表、FRED、BIS、宏观实时。"
agent_created: true
---

# 宏观金融信息仪表盘（全球金融日报）App — 完整版

> 本 skill 是「全球金融日报」实时仪表盘系统的**完整快照**，打包了当前（2026-09 版）全部可运行源码、示例数据与运行脚本。目标：让 AI 或用户能在一台新机器上**原样复现**这套宏观金融信息 App，并能基于它增删模块。

---

## 0. 一句话架构

```
daily_data.json  ──┐  (夜间批处理生成/更新, 唯一数据入口)
                    ├──▶  generate_report.py  ──▶  D:\workbuddy\输出文件\全球金融日报_<日期>.html (+ _V9.xlsx)
live_server.py   ──┘  (实时数据服务器 :8800)
   │  /api/quotes  /api/news  /api/kline  /api/calendar  /api/time
   │  /api/status  /api/macro  /api/advanced
   └─ 前端 HTML 每 5 分钟 + 手动按钮 → 拉取这些端点 → 局部刷新 (霓虹图表/卡片/日历)
```

- **构建期**：`generate_report.py` 读 `daily_data.json`，套模板生成静态 HTML + Excel（含 ECharts 内联 JS）。
- **运行期**：`live_server.py` 把最新 HTML 喂给浏览器，并暴露 REST API 让前端**实时刷新**行情/日历/宏观/进阶数据，无需重生成 HTML。

---

## 1. 文件清单（全部已打包在 `app/`）

| 文件 | 行数 | 职责 |
|------|------|------|
| `live_server.py` | 1403 | 实时数据服务器（ThreadingHTTPServer）。十大 API 端点 + HTML 静态服务；服务端对 `/api/advanced`、`/api/macro` 做硬超时兜底与缓存；启动时拉起 iTick 后台轮询。 |
| `advanced_data.py` | 845 | **进阶数据实时抓取核心**。FRED 双通道（官方 JSON API 优先，需可选 `FRED_API_KEY`；未配自动回退公开 CSV，仍实时）：TIPS/盈亏平衡/SOFR/WTI/Brent/广义美元/CPI/失业率；BIS SDMX WS_EER（8 经济体 NEER/REER）。无免费实时源的板块回退 `daily_data.json` 快照并标 `live=False`。 |
| `data_aggregator.py` | 1966 | 多源行情/新闻聚合。Frankfurter(ECB) 外汇、Sina 商品/指数、Yahoo(DXY/BTC/VIX/罗素)、华尔街见闻快讯/文章/热榜、**金十快讯双通道（官方 MCP 优先，回退 flash_newest.js）**、Eastmoney、Tencent、FxMacro/ForexFactory 财经日历 actual 回填、**iTick 三重作用（口径优先 / 缺口补位 / 交叉校验）**。 |
| `itick_data.py` | 605 | **iTick 行情源**（2026-09-04 新增）。后台常驻轮询 + 内存快照架构，绕开免费套餐 5 次/分钟限流。滑动窗口令牌桶限流（含 `ITICK_RESERVE` 额度预留）、按权重轮转刷新（贵金属/能源权重 2）、429 自动退避、快照落盘、kline 按需兜底（2h/4h 用 1h 聚合）。见 §6.1。 |
| `jin10_mcp.py` | 261 | **金十数据 MCP 客户端**（2026-09-04 新增）。标准 MCP Streamable HTTP + Bearer：`initialize` → `notifications/initialized` → `tools/list` / `resources/list` → `tools/call`；协议 `2025-11-25`；SSE 响应解析；优先读 `structuredContent`；按 `cursor` / `next_cursor` / `has_more` 分页。需可选 `JIN10_MCP_TOKEN`。 |
| `generate_report.py` | 1666 | 统一生成器。读 `daily_data.json` → 生成霓虹 HTML 仪表盘 + Excel。含 `neonLine()` 通用霓虹渲染器、13 个 `renderAdv*` 面板、`fetchAdvanced()` 实时拉取、`_itickBadge()` 来源徽章。 |
| `calendar_fetcher.py` | 1283 | 财经日历 actual 回填。按 `(country,event,time)` 三元组匹配，应用内置 `_FALLBACK_ACTUALS` + 外部 `calendar_actuals_extra.json`。 |
| `sample_daily_data.json` | — | 示例数据入口（当前 2026-09-01 版）。重命名为 `daily_data.json` 即可让 App 离线跑起来。 |
| `启动全球金融日报APP.bat` / `停止全球金融日报APP.bat` / `open_browser_delayed.bat` | — | Windows 一键启动/停止（pythonw 静默后台，端口 8800，延迟 5s 开浏览器）。 |
| `codebuddy_review_advanced.py` | — | 一键调用腾讯云 CodeBuddy 模型路由对进阶模块做外部审查（读 `CODEBUDDY_BASE_URL` + `CODEBUDDY_API_KEY` 环境变量，OpenAI 兼容 `/chat/completions`，model=`ModelRouter/auto`）。 |

> 运行所需依赖：Python 3.13（标准库即可；`generate_report.py` 生成 Excel 需要 `xlsxwriter`）。**无需第三方密钥**即可获取全部实时行情/宏观数据；`FRED_API_KEY` / `EIA_API_KEY` / `JIN10_MCP_TOKEN` / `ITICK_TOKEN` 均为**可选增强**，不配也有回退通道。

---

## 2. 实时数据服务器（`live_server.py`）

- 启动：`` python live_server.py 8800 ``（默认端口 8800；命令行端口覆盖内存缓存陷阱）。
- 桌面启动器已复制到桌面「启动全球金融日报APP.bat」，双击即可（先 kill 占用 8800 的旧 `live_server.py` 进程再重启，确保新代码生效）。
- HTML 服务：`Handler._html()` 每次 GET 都从 `D:\workbuddy\输出文件` 读取**最新** `全球金融日报_*.html`（排除含 `v7_1`/`backup` 的旧文件），不缓存；所有 API 响应加 `no-cache` 头。
- 前端 `BASE` 自动探测 `http://localhost:8800` 与 `http://127.0.0.1:8800`；离线时显示黄色 banner 每 10s 重试。

### API 端点（十大）

| 端点 | 调用函数 | 返回内容 |
|------|----------|----------|
| `GET /` | `_html()` | 最新仪表盘 HTML |
| `/api/quotes?refresh=1` | `get_quotes_with_meta()` | 40+ 品种报价 + 来源/健康度/fetched_at |
| `/api/news?limit=15` | `data_aggregator.fetch_all_news()` | 聚合财经快讯/文章 |
| `/api/kline?name=XXX&tf=1h\|4h\|1d` | `get_kline()` | K 线（优先内存 30s 累积，回退 daily_data.json 月度 OHLC） |
| `/api/calendar?refresh=1` | `get_calendar()` | 三时段财经日历（见 §4） |
| `/api/time` | `fetch_network_time()` | 网络北京时间 |
| `/api/status` | — | 服务状态、品种数、数据源健康 |
| `/api/macro?refresh=1` | `get_macro_realtime()` | 6 经济体政策利率/GDP增速/CPI（BIS + World Bank） |
| `/api/advanced?refresh=1` | `get_advanced_realtime()` | 进阶数据（见 §3） |
| `/api/itick` | `itick_data.status()` + `get_snapshot()` | iTick 后台轮询状态（限流/成功/失败/缓存龄）与全部快照报价 |

**服务端容错**：`get_advanced_realtime` 用 daemon 线程 `join(timeout=25)` 硬兜底，`get_macro_realtime` 缓存 300s（失败仅 60s 后重试）。即使用子模块内 urllib 超时在网络中被静默丢弃，刷新也绝不卡死。

---

## 3. 进阶数据实时模块（`advanced_data.py` + `/api/advanced`）

统一入口 `fetch_advanced_realtime(daily_data, force=False)`，返回 `{ok, fetched_at, source, sections:{...}}`。

### 实时板块（免密钥源；FRED 可选 key 走官方 API）
1. **TIPS / 盈亏平衡 / SOFR** — FRED **双通道**（`_fetch_fred_one`）：
   - `DFII10` 10Y TIPS 实际收益率，`T10YIE` 10Y 盈亏平衡通胀，`SOFR` 隔夜担保融资。
   - **通道1（优先）官方 JSON API**：配置了 `FRED_API_KEY` 时走 `api.stlouisfed.org/fred/series/observations`，`observation_start` 精确过滤、结构化 JSON、专用数据端点更稳定。
   - **通道2（回退）公开 CSV**：未配 key 或 API 失败时走 `fredgraph.csv`，**仍然实时**，功能不降级。
   - `fetch_fred_all` 逐序列并行 + 起始日过滤（多 id 拼接会忽略 `cosd` 返回全历史 6000+ 行，故必须逐序列）。
   - **历史修复**：单序列 CSV 首列叫 `observation_date`（多序列才叫 `DATE`），原解析只认 `DATE` → 全序列静默为空 → 全回退快照（"进阶数据不实时"的真因）。CSV 通道按列名定位日期列；API 通道天然无此歧义。
2. **原油（WTI / Brent）** — FRED `DCOILWTICO` / `DCOILBRENTEU`。
3. **广义美元指数** — FRED `DTWEXBGS`（贸易加权，DXY 权威代理）。
4. **BIS 有效汇率** — BIS SDMX `WS_EER`，8 经济体（US/EA/JP/GB/CH/CA/AU/CN）NEER/REER 月度。
   - **关键修复**：`fetch_bis_eer` 返回 `(date,value)` 元组，但消费端曾按 `(value,date)` 解包 → `neer`/`reer` 变成日期字符串 → 渲染 `toFixed` 崩溃。现统一为 `(val,date)`。

### 实时板块（需 key 或真机可达）
5. **美国 CPI / 失业率** — FRED `CPIAUCSL` / `UNRATE`（取约 2 年月度 → 13 点同比/环比趋势），`days=820` 并行抓取。**同走 FRED 双通道，非必须 key**。
6. **CFTC COT 持仓** — CFTC TFF 周报（8 币种杠杆基金净 + 全体净），`fetch_cot()` 解析。
7. **EIA 原油库存** — EIA v2 REST `petroleum/stoc/wstk/data` + `facets[series][]=WCRSTUS1`（美国商业原油库存·千桶·周度），**需免费 `EIA_API_KEY`**（已环境变量化，无硬编码）。
8. **WGC 央行购金** — 解析 `www.gold.org` Gold Demand Trends 文章叙述文本，提取最新季度净购金 / H1 合计（沙箱仅 www.gold.org 可达，api.gold.org 被拦）。
9. **IMF COFER 外汇储备份额** — IMF SDMX 3.0 `Q.G001.AFXRA.CI_USD+CI_EUR+CI_JPY+CI_GBP+CI_CNY.SHRO_PT`（美元/欧元/人民币/日元/英镑份额%），双端点容灾（www.imf.org / api.imf.org）；**真机实时、沙箱因 Akamai WAF 403 自动回退快照**。

### 快照板块（仍无免费实时源，标 `live=False`，用 `daily_data.json` 快照）
`fx_swap` 外汇掉期 / `etf_gold` 黄金 ETF / `gold_demand` 黄金需求 / `dxy_ibs` DXY-IBS / `eia_iea_oil` EIA/IEA 原油。

### 前端霓虹图表（实时面板霓虹，快照面板素色）
- 通用 `neonLine(cid, seriesMap, opt)`：发光描边（`shadowBlur`/`shadowColor`）、线性渐变填充、末端 `markPoint` 辉光高亮最新值、霓虹 tooltip + dataZoom、1300ms 入场动画；每次 `dispose+reinit`（规避旧实例刷新不重绘）。
- **TIPS 利差图**：青 `#00f0ff` 实际收益率 / 品红 `#ff2d95` 盈亏平衡通胀 / 绿 `#00ff9d` **计算利差(DFII10−T10YIE)** 三条霓虹线。
- **原油霓虹图**：琥珀 `#ffa940` WTI / 橙 `#ff6b35` Brent。
- **广义美元指数霓虹图**：蓝 `#4dabf7`。
- **多国 EER 对比图**：7 国 REER 霓虹多线（品红起头的霓虹调色板）。
- **COT 净头寸走势图（v1.1.0 增强）**：「杠杆基金净 / 全体净」一键切换；零轴正负着色——**正值 = 青 `#00f0ff` · 负值 = 品红 `#ff2d95`**（用 `neonLine` 的 `posNeg` + ECharts `visualMap` 按 y 符号分段），净多 / 净空一目了然。
- 设计取舍：**实时面板=霓虹，快照面板=素色** → "霓虹=实时"视觉信号。

---

## 4. 财经日历（三时段 + 实时升档）

- 数据源：`daily_data.json` → `economic_calendar`（`released`/`upcoming` 两段，由 `live_server.get_calendar` 按**真实北京时间**动态重分类为 `today`/`week`/`future`）。
- 三区块：
  - **待公布**（次日及以后）
  - **当日**（今日公布 + 今日待公布）
  - **当周已公布**（本周一~周日）
- **实时升档**：发布时间 ≤ 当前北京时间 的 `upcoming` 事件，立即升档到「当日/当周」并标 `just_released:true` 高亮 2s；`?refresh=1` 绕过 300s 内存缓存实时对比归类。解决"过期事件消失"的 bug。
- 每条：time、country、flag、event、actual、forecast、previous、unit、impact(high/medium/low)、note。
- 底部图表：ECharts 水平分组柱状图（前值/预测/实际，实际值红=超预期·绿=低于预期·灰=待公布）+ 可切换「2026 YTD 折线」；`actual` 仍来自 `daily_data.json`（夜间批处理/人工回填），点到后揭示并高亮。

---

## 5. 实时宏观（BIS + World Bank，`/api/macro`）

- 聚焦 6 经济体：`_MACRO_ECONOMIES` = 美联储 US / 欧洲央行 XM（**BIS 代码是 `XM` 非 `EU`**）/ 英国 GB / 日本 JP / 澳洲 AU / 韩国 KR。
- `get_macro_realtime()` 内存缓存：成功快照 300s，失败仅 60s 后重试。
- 政策利率 `_bis_policy_rates()` → BIS `WS_CBPOL`，`M.US+XM+GB+JP+AU+KR?lastNObservations=1`（key 不能用 `M.*.*`，会 404）。
- CPI `_bis_cpi_yoy()`（新增）→ BIS `WS_LONG_CPI`，`M.{area}.771`，取各国最新月。
- GDP：仅年度（全球无月度序列），World Bank `NY.GDP.MKTP.KD.ZG` 年增速（按 ISO3）。
- 前端：央行动态 Tab「实时宏观数据」三块霓虹蓝卡片网格 + 「刷新实时宏观」按钮，离线/失败提示「显示下方静态快照」。

---

## 6. 多源行情聚合（`data_aggregator.py`）

数据源优先级（严谨，以 API 实时为准，WebSearch 仅兜底）：
1. **Frankfurter API (ECB)**：外汇汇率，含前日；`curl -sL` 跟随 301。
2. **Sina Finance**：商品(5)+指数(15)，GBK 编码。
3. `daily_data.json`：报价/回退。
4. **Yahoo Finance**：仅 DXY/BTC/VIX/罗素，常 403。
5. 内存价格历史：30s 累积，支持 1h/4h/1d K 线聚合。

新闻：华尔街见闻快讯/文章/热榜、**金十快讯（双通道）**、Eastmoney、Sina RSS（去重 + 去广告 + 时效性排序）。

### 金十快讯双通道（`fetch_jin10_flash`）
| 通道 | 依赖 | 数据来源 | 特点 |
|------|------|----------|------|
| 1（优先） | `JIN10_MCP_TOKEN` | 官方 MCP `list_flash` | 结构化字段、**真实详情页 url**（`flash.jin10.com/detail/...`）、ISO 标准时间，无需正则逆向 |
| 2（回退） | 无 | `flash_newest.js` 抓取 | 无需密钥仍保持实时；url 为写死首页 `https://www.jin10.com/` |

- MCP 通道实现要点（`jin10_mcp.py`，均已实测验证）：
  - 服务端**不返回 `Mcp-Session-Id`** → 按**无状态模式**处理，每次请求独立带 Bearer，握手每进程一次即可
  - 响应是 **SSE**（`Content-Type: text/event-stream`），必须从 `data:` 行提取 JSON；直接 `json.loads(body)` 会解析失败
  - 结果优先读 `result.structuredContent`；`result.content` 仅作可读补充，**不作为机器解析来源**
  - 分页：请求 `cursor` / 响应 `data.next_cursor` / `data.has_more`；`list_flash` 实测 20 条/页
  - 限流：每个工具 1500 次/天（北京时间自然日统计），超限返回业务错误而非 JSON-RPC 错误
  - **客户端实例复用**：`fetch_flash_raw` 等共用一个模块级单例（加锁、线程安全），握手每进程仅一次——首次 0.54s、后续 0.15s；调用失败时 `_reset_client()` 丢弃实例以便下次重新握手
  - **限额核算**：前端自动更新间隔为 5 分钟 → 约 288 次/天，远低于 1500 限额；且握手不占用 `tools/call` 配额
- 配额说明：`fetch_all_news` 对金十设单源上限 `max(5, limit*0.40)`（2026-09-04 由 `0.30` 上调至 `0.40`）。
  前端实际按 `limit=26` 请求 → 配额 `max(5,10)=10` 条，**实测金十稳定出 10 条且全部为 MCP 详情页链接**
  （调整前为 5 条）。MCP 调用成本不受影响（一次 `list_flash` 即覆盖该配额）。
  单源上限的目的是避免刷屏、保证多视角，上调后仍保留华尔街见闻 12 条 / 见闻深度 4 条的多样性。

### 6.1 iTick 行情源（`itick_data.py`，2026-09-04 新增）

#### 为什么必须走「后台轮询 + 快照」而不是请求链路
iTick **免费套餐实测硬性限流 5 次/分钟**（第 6 次起返回 `429 {"code":429,"msg":"request limit exceeded"}`，
按分钟窗口重置）。若把 iTick 放进 `/api/quotes` 请求链路，每次刷新都会被限流击穿且拖慢响应。

因此采用架构：
- 守护线程（`daemon=True`，不阻塞进程退出）按**滑动窗口令牌桶**（62s 窗口 / 5 次）轮转刷新；
- 请求路径只读 `get_snapshot()` 内存快照 → **零 API 调用、零网络延迟、永不触发 429**；
- 启动时 `bootstrap()` 同步预热 1 分钟额度（默认 5 次），保证首屏即有数据；
- 429 → `_note_throttle()` 退避到下一窗口；其它失败 → 指数退避（上限 10 分钟）；
- **快照落盘**（`itick_cache.json`，与 `daily_data.json` 同目录）：重启后先读盘恢复，
  再启动后台轮询。桌面 bat 每次启动都会重启进程，若上一实例刚用掉当分钟额度会导致
  bootstrap 拿 429、缓存为空；落盘后**重启可立即恢复上次快照**，贵金属不会闪回期货价。
  实测：重启后 12 秒内恢复 10 条，贵金属立刻保持现货口径。

#### API 契约（2026-09-04 实测，易踩坑处）
| 项 | 结论 |
|----|------|
| 认证域名 | **`https://api-free.itick.org`**（免费版专用）。免费 Token 打 `https://api.itick.org` 会返回 `401 {"message":"Invalid API key in request"}` |
| 认证方式 | 请求头 `token: <KEY>` + `accept: application/json` |
| 实时报价 | `GET /forex/quote?region=GB&code=XAUUSD` |
| region | 外汇/贵金属/能源**统一为 `GB`**。写成 `FX` 会返回 `data:null`（不报错，静默空值） |
| 批量 | **不支持**：`code=EURUSD,GBPUSD` 返回 `data:null`，必须一品种一次调用 |
| 逐笔 | `GET /forex/tick?region=GB&code=XAUUSD` |
| K 线 | `GET /forex/kline?region=GB&code=XAUUSD&kType=8&limit=100`；kType `1=1分 2=5分 3=15分 4=30分 5=1时 6=2时 7=4时 8=日 9=周 10=月` |
| 品种清单 | `GET /symbol/list?type=forex&region=GB`（330 个，**代码字段是 `c` 不是 `s`**，`s` 恒为 null） |
| 响应 | `{"code":0,"msg":null,"data":{...}}`，**`code=0` 才是业务成功**（与 HTTP 200 区分） |
| data 字段 | `s`代码 / `ld`最新价 / `p`前收 / `o,h,l` / `ch`涨跌 / `chp`涨跌% / `v`量 / `tu`额 / `t`毫秒戳 / `r`市场 |

品种代码（已对照 symbol list 核实）：`XAUUSD` 现货黄金、`XAGUSD` 现货白银、`USOIL` WTI原油、
`UKOIL` 布伦特原油、`XNGUSD` 天然气，加 18 个主要货币对/交叉盘。**按项目约定剔除人民币相关品种**。

#### 三重作用（`fetch_all_quotes` Phase 3）
| 作用 | 触发条件 | 行为 |
|------|----------|------|
| ① 缺口补位 | 主源全挂 | 直接用 iTick 报价，`itick.filled=True` |
| ② **口径优先** | 品种在 `PREFER` 集合且快照龄 ≤ `PREFER_MAX_STALE`(600s) | 以 iTick 现货价**覆盖**主源；被覆盖价存入 `itick.altPrice/altSource` 保留可比对 |
| ③ 交叉校验 | 其余品种 | 挂 `quote["itick"] = {price, code, divPct, staleSec}`，`divPct` 为与主源的相对分歧% |

**口径优先的由来（重要）**：日报里「现货黄金」「现货白银」标注为现货，但新浪 `hf_GC`/`hf_SI`
实际取的是 **COMEX 期货**合约价，实测与现货差约 **1%**（2026-09-04：黄金期货 4515.67 vs 现货 4469.62）。
用户为**现货交易者**，MT4 实盘报价是 `XAUUSD`/`XAGUSD` 现货 CFD，因此贵金属改用 iTick 现货口径。
原油/天然气保持新浪期货（WTI/布伦特期货本身即国际基准，且日报未标注"现货"）。
佐证：**欧元/美元分歧仅 0.077%**（Frankfurter ECB 与 iTick 都是真现货），说明分歧来自口径而非数据错误。

> 想改回期货口径：把 `itick_data.PREFER` 清空即可；想让能源也走现货：把对应品种名加进 `PREFER`。

**为什么 `PREFER_MAX_STALE` 定 600s 而不是 300s**：23 个品种按 5 次/分钟轮转时，个别时刻数据龄
会拉长到 300s 以上（实测最旧 341s）。阈值若卡 300s，贵金属会在「现货价」与「期货价」之间来回跳变，
造成约 **1% 的价格闪跳**。而这两者**根本不是同一标的**——回落并不会得到"更新鲜的现货价"。
对现货交易者而言，宁可要稍旧的现货价，也不要实时的期货价，故放宽到 600s。

#### 实测指标（23 品种 / 5 次每分钟）
- 轮转权重：贵金属与能源 `weight=2`，其余 `weight=1`；选品得分 `= 陈旧秒数 × 权重`。
- 结果：**23/23 全部缓存，核心品种平均陈旧 ~95s，其余 ~128s；累计 35 次调用 0 失败 0 限流**。
- 重启时若上一实例刚用掉当分钟额度，bootstrap 会拿到 429 → 自动退避约 62s 后由 worker 补齐，
  期间贵金属**自动回落新浪期货**（兜底生效，行情不中断）。

#### K 线接入（`live_server.get_kline()` 第 2.5 层）
链路：`1 新浪(仅外汇)` → `2 Yahoo(全品种, 常 403)` → **`2.5 iTick（仅 PREFER）`** → `3 内存历史` → `4 daily_data 兜底`。
- **仅 PREFER 品种（现货黄金/白银）用 iTick**，保证 K 线与报价同为现货口径。
- **不要给其他品种兜底**（踩过坑）：曾实现为"前面都失败就用 iTick"，结果原油上
  报价 91.65（新浪期货）vs K 线末根 92.23（iTick USOIL 现货）、
  布伦特 95.64 vs 97.74 —— 重演了口径打架。非 PREFER 品种保持期货口径，
  应继续走「内存历史（期货价累积）→ daily_data（同期货口径）」。
- 非阻塞 + 有兜底：拿不到额度就静默跳过继续走原链路。

实测（限定范围后）：现货黄金报价 4474.53 / K 线末根 4474.13 ✓；现货白银 66.77 / 66.77 ✓。
原油/天然气剩余差异来自 `daily_data` 快照的**时点陈旧**（同口径不同时间戳），非口径冲突。

**踩坑：`kType=6`(2h) / `7`(4h) 在外汇上返回「成功但 data 为空」**——不是限流也不是报错
（`ok` 计数会 +1，极易误判）。因此这两个周期直接用 **1h 聚合**（`_aggregate()`），只花 1 次调用。

#### 额度预留：`ITICK_RESERVE`（默认 1，关键）
**踩过的坑**：后台轮询会占满 5 次/分钟窗口，而按需 K 线请求用 `block=False`（不等待），
结果**永远拿不到额度**——表现为黄金 K 线始终回落到 Yahoo 期货价，与报价面板的现货价打架。
修复：后台轮询最多用 `RPM - RESERVE` 次，窗口里始终留名额给按需请求。
- 后台轮询 4 次/分钟，按需请求恒有 1 次立即可用；
- 代价：23 品种轮转周期 4.6 分钟 → 5.8 分钟，核心品种仍 ~95s；
- 不需要 K 线时设 `ITICK_RESERVE=0` 可让报价刷新更快。

#### 口径一致性：`record_price(name, price, source)`
**踩过的坑**：口径切换后，内存价格历史会同时混入新浪期货价(~4515) 与 iTick 现货价(~4470)，
聚合出的 1 小时 K 线在两个标的之间跳变。
修复：**PREFER 品种只记录 `source=itick` 的价格**——既然以现货为准，走势图就只画现货价，
iTick 暂不可用时不更新，也不混入期货价。非 PREFER 品种行为不变。

#### 前端展示（`generate_report.py`）
- `_itickBadge(q)` 三态徽章：`itick-pref`（青色霓虹「iTick现货」，hover 显示被覆盖的期货价与分歧）、
  `itick-warn`（琥珀色，分歧 ≥0.5% 时高亮）、`itick-ok`（灰色，正常参考价）。
- 数据源状态栏新增 `● iTick 10/23`，hover 显示限流/成功/失败/缓存龄。

---

## 7. 关键技术与用户约定（必读）

- **中国股市惯例**：涨=红、跌=绿（实际值高于预期也用红/绿标识）。
- **剔除人民币数据**：外汇/债券/央行/日历均不含 CNY/PBOC/LPR（用户 2026-08-19 要求）。
- **输出位置**：生成文件统一到 `D:\workbuddy\输出文件`（用户偏好，禁写 C 盘）；预览 `http://localhost:8800/`。可用环境变量 `WORKBUDDY_OUTPUT`（HTML/Excel）、`WORKBUDDY_DATA_DIR`（daily_data.json）覆盖。
- **API 密钥（可选，均环境变量化，公开副本无硬编码）**：
  - `FRED_API_KEY` 走 FRED 官方 JSON API —— **不配也能用**，自动回退公开 CSV 通道、仍保持实时；
  - `EIA_API_KEY` 取 EIA 原油库存 —— **不配则该板块回退快照**；
  - `JIN10_MCP_TOKEN` 走金十官方 MCP 快讯 —— **不配也能用**，自动回退 `flash_newest.js` 抓取，仍实时（仅丢失详情页 url）；
  - `ITICK_TOKEN` 走 iTick 行情源 —— **不配则该源整体禁用**（模块 `enabled=False`，主源照常工作，行情不中断）。
    可选配 `ITICK_BASE`（默认 `https://api-free.itick.org`，付费版改 `https://api.itick.org`）、
    `ITICK_RPM`（默认 5，付费套餐可设 120/600/1200）、
    `ITICK_RESERVE`（默认 1，给按需请求预留的额度；设 0 则后台轮询占满全部额度）。
  - 设置：Windows `set FRED_API_KEY=你的key`，Linux/Mac `export FRED_API_KEY=你的key`。
  - 另：本机 `~/.workbuddy/mcp.json` 已配置 `jin10` MCP 服务器（供 WorkBuddy 会话直接调用 8 个工具），需在连接器管理页点「信任」后生效。
- **Python 环境**：managed `python 3.13.12`；生成 Excel 必须用 venv `envs/default`（含 `xlsxwriter 3.2.9`），managed 环境缺该依赖。
- **Excel 生成**：通过 `xlsxwriter`；若缺失则用纯标准库 `zipfile`+`xml` 兜底（见其他技能约定）。
- **编码**：`live_server.py` 中文以 `\uXXXX` 转义存储（直接 Edit 改含中文字典会匹配失败，须脚本替换）。
- **硬超时加固**：`/api/advanced` 服务端 25s 兜底 + 模块内 15/18s；`/api/macro` 300s 缓存。
- **旧进程陷阱**：`live_server.py` 仅在启动时 import 模块，改代码后必须 kill 旧进程重启才能让新端点/新逻辑生效。

---

## 8. 每日自动化（22:00 流水线）

> `automation-1787210241342` (ACTIVE)：每日 22:00 运行
> `fetch_history.py` + `fetch_history_fix.py` → 更新 `daily_data.json`(2026 YTD 日线)
> → `backfill_calendar_actuals.py` 回填日历 actual（应用 `_FALLBACK_ACTUALS` + 外部 `calendar_actuals_extra.json`，gaps 用 WebSearch 核实后 `add_calendar_actual.py` 写入）
> → `generate_report.py` 生成 HTML+Excel
> → 重启 `live_server.py`
> → 向用户呈现报告（含本次日历回填情况）。

注意：本流水线**仅更新行情日线，不自动回填日历 actual**——日历 actual 缺失是"已到时间·待取数"的根因；回填依赖外部 `calendar_fetcher._FALLBACK_ACTUALS` + 夜间 WebSearch。

---

## 9. 如何运行（新机器复现）

```bash
# 1) 准备（一次性）
pip install xlsxwriter        # 仅 Excel 产出需要；行情/宏观/HTML 全用标准库
cp app/sample_daily_data.json app/daily_data.json

# 2) 生成今日报告（HTML + Excel）
cd app
python generate_report.py
# 输出: D:\workbuddy\输出文件\全球金融日报_<日期>.html (+ _V9.xlsx)

# 3) 启动实时服务器（新终端）
python live_server.py 8800
# 浏览器打开 http://localhost:8800/

# 4) 手动刷新进阶/宏观/日历：仪表盘内按钮 或 前端每 5 分钟自动刷新
```

Windows 用户直接双击桌面「启动全球金融日报APP.bat」即可（静默后台 + 自动开浏览器）。

---

## 10. 扩展指南（增删模块的标准姿势）

- **新增实时端点**：在 `live_server.py` 加 `elif path == "/api/xxx"` + 对应 `get_xxx()`，并在 `advanced_data.py` 或 `data_aggregator.py` 实现抓取；前端加 `fetchXxx()` + `renderXxx()` + 容器 div + 在 `doFullUpdate()` 挂接。
- **新增霓虹图**：调用 `neonLine(cid, seriesMap, {colors:[...], yName, suffix, areaTop, height, glowColor, markLast})`，seriesMap 格式 `{name:[[date,val],...]}`。
- **新增 FRED 序列**：在 `advanced_data.FRED_SERIES` 与 `_fred_ids` 加 id，解析逻辑复用 `_fetch_fred_one`（已兼容两种表头）。
- **新增 BIS 指标**：参考 `_bis_policy_rates`/`_bis_cpi_yoy` 的 SDMX 调用（注意 key 格式与 ECB 代码映射）。
- **新增受限流约束的数据源**（如 iTick 5 次/分钟）：**绝不能放进请求链路**。照 `itick_data.py` 的姿势做：
  ① 模块内实现滑动窗口令牌桶 + 429 自动退避；② 后台 `daemon` 线程按权重轮转刷新写入内存缓存；
  ③ 对外部只暴露 `get_snapshot()` 读缓存；④ 启动时 `bootstrap()` 同步预热保证首屏有数据；
  ⑤ 聚合器侧用**延迟 import + try/except** 包裹，源失效绝不拖垮主流程。
- **修改后必做**：kill 占用 8800 的旧 `live_server.py` 进程后重启；验证端点 `curl -s "http://127.0.0.1:8800/api/xxx?refresh=1"`。

---

## 11. 已知修复日志（本版本已解决）

| 问题 | 根因 | 修复 |
|------|------|------|
| 进阶数据不实时 | FRED CSV 首列 `observation_date`，原解析只认 `DATE` → 全序列 0 点回退快照 | `_fetch_fred_one` 按列名定位日期列 |
| EER 面板崩溃 | `fetch_bis_eer` 返回 `(date,value)`，消费端按 `(value,date)` 解包，`toFixed` 抛错 | 统一为 `(val,date)` |
| 抓取偶发卡死（>40s） | urllib 内部 timeout 受限网络不触发 | 模块内 `result(15/18)` + 服务端 `Thread.join(25)` |
| FRED 多 id 忽略 cosd | 返回全历史 6000+ 行 | 改逐序列并行 + cosd |
| 图表刷新不重绘 | JS 同作用域函数声明遮蔽 + 旧 echarts 实例未 dispose | 删重复 `initAdvChart`；`neonLine` 每次 dispose+reinit |
| 日历过期事件消失 | 仅按 daily_data 过期 curr_date 比对 | 改用真实北京时间动态重分类 + 升档 |

详细实现见 `app/` 源码与 `references/`。
