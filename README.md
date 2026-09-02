# macro-financial-dashboard（宏观金融信息仪表盘 / 全球金融日报）

一套**免密钥、可离线运行**的宏观金融信息实时仪表盘系统。打包了完整可运行源码，开箱即用：一行命令生成 HTML 霓虹仪表盘 + Excel，再启一个实时服务器即可在前端自动刷新行情 / 日历 / 宏观经济 / 进阶数据。

## 功能清单

| 模块 | 文件 | 说明 |
|------|------|------|
| 实时数据服务器 | `app/live_server.py` | 端口 8800，九大 API 端点（`/api/quotes` `/news` `/kline` `/calendar` `/time` `/status` `/macro` `/advanced`），服务端硬超时兜底 |
| 进阶数据实时抓取 | `app/advanced_data.py` | 免密钥源：FRED CSV（TIPS / 盈亏平衡 / SOFR / WTI / Brent / 广义美元）+ BIS SDMX 有效汇率（8 经济体 NEER/REER） |
| 多源行情/新闻聚合 | `app/data_aggregator.py` | Frankfurter(ECB) 外汇、Sina 商品/指数、Yahoo(DXY/BTC/VIX)、华尔街见闻/金十快讯 |
| 报告生成器 | `app/generate_report.py` | 读 `daily_data.json` → 霓虹 HTML 仪表盘 + Excel（含 `neonLine` 通用霓虹渲染器、13 个实时面板） |
| 财经日历回填 | `app/calendar_fetcher.py` | 按 `(country,event,time)` 三元组回填 actual |
| 示例数据 | `app/sample_daily_data.json` | 重命名为 `daily_data.json` 即可离线运行 |
| 一键启停 | `app/*.bat` | Windows 静默后台启动 / 停止 |
| 外部审查 | `app/codebuddy_review_advanced.py` | 调用腾讯云 CodeBuddy 模型路由审查进阶模块（需环境变量） |

## 目录结构

```
macro-financial-dashboard/
├── SKILL.md                  # 技能文档（架构 / 端点 / 约定 / 修复日志 / 扩展指南）
├── README.md                 # 本文件
├── LICENSE                   # MIT
├── .gitignore
├── app/                      # 完整可运行源码
│   ├── live_server.py
│   ├── advanced_data.py
│   ├── data_aggregator.py
│   ├── generate_report.py
│   ├── calendar_fetcher.py
│   ├── sample_daily_data.json
│   ├── *.bat / codebuddy_review_advanced.py
│   └── README.md
└── references/
    └── api_schemas.md        # API payload 契约（前端对接参考）
```

## 安装到 WorkBuddy（作为技能）

```bash
# 复制整个目录到技能目录
cp -r macro-financial-dashboard ~/.workbuddy/skills/
```

## 独立运行

```bash
cd app
pip install xlsxwriter          # 仅 Excel 产出需要；行情/宏观/HTML 全用标准库
cp sample_daily_data.json daily_data.json
python generate_report.py      # → ./output/全球金融日报_<日期>.html (+ _V9.xlsx)
python live_server.py 8800     # 浏览器开 http://localhost:8800/
```

## 路径配置

默认把 HTML/Excel 写到 `./output`（已脱敏，原默认 `D:\workbuddy\输出文件`）。可用环境变量覆盖：

```bash
export WORKBUDDY_OUTPUT="/your/output/dir"
export WORKBUDDY_DATA_DIR="/path/to/app"
```

## 数据来源与免责声明

- 实时行情/宏观数据来自 **FRED、BIS、Frankfurter(ECB)、Sina、Yahoo** 等公开免费接口，**无需任何 API key**。
- 财经日历 actual 值部分来自夜间批处理回填与公开检索，仅供参考，不构成投资建议。
- 红涨绿跌遵循中国 A 股惯例；已剔除人民币资产（按原设计约定）。

## License

MIT © 2026 FENG.JIN
