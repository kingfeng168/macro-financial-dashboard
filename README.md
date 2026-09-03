# macro-financial-dashboard

宏观金融信息仪表盘「全球金融日报」App 完整版 —— 一套可在单机运行的实时金融数据系统，覆盖外汇、大宗商品、股指、国债收益率、OIS/IRS 利率、央行政策与宏观指标。

## 一句话定位

输入 `daily_data.json`（夜间批处理生成的唯一数据入口），由 `generate_report.py` 产出霓虹风格 HTML 仪表盘 + Excel；再由 `live_server.py`（端口 8800）提供 REST API，让前端每 5 分钟及手动刷新实时拉取行情 / 日历 / 宏观 / 进阶数据，无需重生成 HTML。

## 核心能力

- **6 大核心指标实时化**：美国 CPI、失业率、CFTC COT 持仓、EIA 原油库存、WGC 央行购金、IMF COFER 美元储备份额（CPI/失业率走 FRED、COT 走 CFTC、EIA 走 EIA v2 REST、WGC/COFER 走官方源解析；沙箱无网络时优雅回退 `daily_data.json` 快照）。
- **实时数据服务器** `live_server.py`：提供 `/api/quotes` `/api/news` `/api/kline` `/api/calendar` `/api/time` `/api/status` `/api/macro` `/api/advanced` 九大端点，全部加 no-cache 头，前端自动探测 `localhost:8800` 并离线重试。
- **霓虹仪表盘** `generate_report.py`：ECharts 内联图表，A股惯例红涨绿跌，COT 走势图支持「杠杆净 / 全体净」切换 + 零轴正负着色（正值青、负值品红）。
- **多源行情聚合** `data_aggregator.py`：Frankfurter / Sina / Yahoo / 华尔街见闻 / 金十。
- **财经日历 actual 回填** `calendar_fetcher.py`：三段式（待公布 / 当日 / 当周已公布），实时升档。

## 目录结构

```
macro-financial-dashboard/
├── SKILL.md                  # 技能说明（AI 可读）
├── README.md                 # 本文件
├── LICENSE                   # MIT
├── .gitignore
├── app/                      # 全部可运行源码与脚本
│   ├── live_server.py        # 实时数据服务器 :8800
│   ├── advanced_data.py      # 进阶数据实时抓取（FRED + BIS + EIA + WGC + COFER）
│   ├── generate_report.py    # HTML 霓虹仪表盘 + Excel 生成器
│   ├── data_aggregator.py    # 多源行情聚合
│   ├── calendar_fetcher.py   # 财经日历 actual 回填
│   ├── daily_data.json       # 数据入口（运行期由批处理更新）
│   ├── sample_daily_data.json# 示例数据
│   ├── 启动全球金融日报APP.bat
│   ├── 停止全球金融日报APP.bat
│   └── open_browser_delayed.bat
└── references/
    └── api_schemas.md        # API 字段说明
```

## 安装 / 运行

1. 将本目录整个复制到 `~/.workbuddy/skills/macro-financial-dashboard/`（保持 `SKILL.md` 在根、`app/` 在子目录）。
2. 安装 Python 3.11+（项目使用内置标准库 + 少量纯 Python 依赖；Excel 生成依赖 `xlsxwriter`，HTML 仪表盘无需第三方库）。
3. 双击 `app/启动全球金融日报APP.bat` 启动服务器（默认端口 8800，自动打开 http://localhost:8800/ ）。

> 输出文件统一写到环境变量 `WORKBUDDY_OUTPUT`（默认 `D:\workbuddy\输出文件`）。

## 密钥配置

- **EIA 原油库存**需要免费 API key：到 https://www.eia.gov/opendata/ 申请，然后通过环境变量提供：
  - Windows：`set EIA_API_KEY=你的key`
  - Linux/macOS：`export EIA_API_KEY=你的key`
- 其余实时源（FRED / BIS / CFTC / WGC / IMF COFER）均免密钥；无网络时自动回退 `daily_data.json` 快照。

## 依赖说明

- 运行仪表盘 / 实时服务器：**仅 Python 标准库**（urllib / threading / zipfile 等）。
- 生成 Excel 报告：需 `xlsxwriter`（`pip install xlsxwriter`）；不影响 HTML 仪表盘。
- 无 GUI 依赖，纯后端 + 浏览器前端。

## 免责声明

本项目仅供研究与学习使用，所有行情 / 宏观数据来自公开第三方源，可能存在延迟或误差，**不构成任何投资建议**。使用者须自行核实数据并承担一切交易与决策风险。

## License

[MIT](./LICENSE) © kingfeng168
