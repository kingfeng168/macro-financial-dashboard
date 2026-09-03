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
| `live_server.py` | 1333 | 实时数据服务器（ThreadingHTTPServer）。九大 API 端点 + HTML 静态服务；服务端对 `/api/advanced`、`/api/macro` 做硬超时兜底与缓存。 |
| `advanced_data.py` | 355 | **进阶数据实时抓取核心**。免密钥源：FRED CSV（TIPS/盈亏平衡/SOFR/WTI/Brent/广义美元）+ BIS SDMX WS_EER（8 经济体 NEER/REER）。无免费实时源的板块回退 `daily_data.json` 快照并标 `live=False`。 |
| `data_aggregator.py` | ~1750 | 多源行情/新闻聚合。Frankfurter(ECB) 外汇、Sina 商品/指数、Yahoo(DXY/BTC/VIX/罗素)、华尔街见闻快讯/文章/热榜、金十快讯、Eastmoney、Tencent、FxMacro/ForexFactory 财经日历 actual 回填。 |
| `generate_report.py` | 1554 | 统一生成器。读 `daily_data.json` → 生成霓虹 HTML 仪表盘 + Excel。含 `neonLine()` 通用霓虹渲染器、13 个 `renderAdv*` 面板、`fetchAdvanced()` 实时拉取。 |
| `calendar_fetcher.py` | 1283 | 财经日历 actual 回填。按 `(country,event,time)` 三元组匹配，应用内置 `_FALLBACK_ACTUALS` + 外部 `calendar_actuals_extra.json`。 |
| `sample_daily_data.json` | — | 示例数据入口（当前 2026-09-01 版）。重命名为 `daily_data.json` 即可让 App 离线跑起来。 |
| `启动全球金融日报APP.bat` / `停止全球金融日报APP.bat` / `open_browser_delayed.bat` | — | Windows 一键启动/停止（pythonw 静默后台，端口 8800，延迟 5s 开浏览器）。 |
| `codebuddy_review_advanced.py` | — | 一键调用腾讯云 CodeBuddy 模型路由对进阶模块做外部审查（读 `CODEBUDDY_BASE_URL` + `CODEBUDDY_API_KEY` 环境变量，OpenAI 兼容 `/chat/completions`，model=`ModelRouter/auto`）。 |

> 运行所需依赖：Python 3.13（标准库即可；`generate_report.py` 生成 Excel 需要 `xlsxwriter`）。**无需第三方密钥**即可获取全部实时行情/宏观数据。

---

## 2. 实时数据服务器（`live_server.py`）

- 启动：`` python live_server.py 8800 ``（默认端口 8800；命令行端口覆盖内存缓存陷阱）。
- 桌面启动器已复制到桌面「启动全球金融日报APP.bat」，双击即可（先 kill 占用 8800 的旧 `live_server.py` 进程再重启，确保新代码生效）。
- HTML 服务：`Handler._html()` 每次 GET 都从 `D:\workbuddy\输出文件` 读取**最新** `全球金融日报_*.html`（排除含 `v7_1`/`backup` 的旧文件），不缓存；所有 API 响应加 `no-cache` 头。
- 前端 `BASE` 自动探测 `http://localhost:8800` 与 `http://127.0.0.1:8800`；离线时显示黄色 banner 每 10s 重试。

### API 端点（九大）

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

**服务端容错**：`get_advanced_realtime` 用 daemon 线程 `join(timeout=25)` 硬兜底，`get_macro_realtime` 缓存 300s（失败仅 60s 后重试）。即使用子模块内 urllib 超时在网络中被静默丢弃，刷新也绝不卡死。

---

## 3. 进阶数据实时模块（`advanced_data.py` + `/api/advanced`）

统一入口 `fetch_advanced_realtime(daily_data, force=False)`，返回 `{ok, fetched_at, source, sections:{...}}`。

### 实时板块（免密钥源）
1. **TIPS / 盈亏平衡 / SOFR** — FRED 单序列 CSV：
   - `DFII10` 10Y TIPS 实际收益率，`T10YIE` 10Y 盈亏平衡通胀，`SOFR` 隔夜担保融资。
   - **关键修复**：FRED 单序列 CSV 首列叫 `observation_date`（多序列才叫 `DATE`），原解析只认 `DATE` → 所有序列静默解析为空 → 全回退快照（这正是"进阶数据不实时"的真因）。现 `_fetch_fred_one` 按列名定位日期列（`date` 或 `observation_date` 任一）。
   - `fetch_fred_all` 改为**逐序列并行** + `cosd` 起始日过滤（多 id 拼接会忽略 `cosd` 返回全历史 6000+ 行，故必须逐序列）。
2. **原油（WTI / Brent）** — FRED `DCOILWTICO` / `DCOILBRENTEU`。
3. **广义美元指数** — FRED `DTWEXBGS`（贸易加权，DXY 权威代理）。
4. **BIS 有效汇率** — BIS SDMX `WS_EER`，8 经济体（US/EA/JP/GB/CH/CA/AU/CN）NEER/REER 月度。
   - **关键修复**：`fetch_bis_eer` 返回 `(date,value)` 元组，但消费端曾按 `(value,date)` 解包 → `neer`/`reer` 变成日期字符串 → 渲染 `toFixed` 崩溃。现统一为 `(val,date)`。

### 实时板块（需 key 或真机可达）
5. **美国 CPI / 失业率** — FRED `CPIAUCSL` / `UNRATE`（取约 2 年月度 → 13 点同比/环比趋势），`days=820` 并行抓取。
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

新闻：华尔街见闻快讯/文章/热榜、金十快讯、Eastmoney、Sina RSS（去重 + 去广告 + 时效性排序）。

---

## 7. 关键技术与用户约定（必读）

- **中国股市惯例**：涨=红、跌=绿（实际值高于预期也用红/绿标识）。
- **剔除人民币数据**：外汇/债券/央行/日历均不含 CNY/PBOC/LPR（用户 2026-08-19 要求）。
- **输出位置**：生成文件统一到 `D:\workbuddy\输出文件`（用户偏好，禁写 C 盘）；预览 `http://localhost:8800/`。可用环境变量 `WORKBUDDY_OUTPUT`（HTML/Excel）、`WORKBUDDY_DATA_DIR`（daily_data.json）覆盖。
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
