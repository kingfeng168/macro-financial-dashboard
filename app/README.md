# 宏观金融信息仪表盘 App — 运行包

本目录是「全球金融日报」实时仪表盘的**完整可运行副本**（2026-09 版）。

## 文件
- `live_server.py` — 实时数据服务器（端口 8800，九大 API 端点）
- `advanced_data.py` — 进阶数据实时抓取（FRED + BIS，免密钥）
- `data_aggregator.py` — 多源行情/新闻聚合
- `generate_report.py` — HTML 霓虹仪表盘 + Excel 生成器
- `calendar_fetcher.py` — 财经日历 actual 回填
- `sample_daily_data.json` — 示例数据（重命名为 `daily_data.json` 即可离线运行）
- `启动/停止全球金融日报APP.bat`、`open_browser_delayed.bat` — Windows 一键启停
- `codebuddy_review_advanced.py` — 调用 CodeBuddy 模型路由做外部审查（需 `CODEBUDDY_BASE_URL`+`CODEBUDDY_API_KEY`）

## 快速开始
```bash
pip install xlsxwriter            # 仅 Excel 产出需要
cp sample_daily_data.json daily_data.json
python generate_report.py        # → ./output\全球金融日报_<日期>.html
python live_server.py 8800       # 浏览器开 http://localhost:8800/
```

## 路径配置（重要）
- 代码默认把 HTML/Excel 写到 `./output`。换机器用环境变量覆盖：
  ```bash
  export WORKBUDDY_OUTPUT="/your/output/dir"
  export WORKBUDDY_DATA_DIR="/path/to/this/app"
  ```
- `live_server.py` 读取自身目录下的 `daily_data.json`；`generate_report.py` 默认读 `WORKBUDDY_DATA_DIR` 或自身目录下的 `daily_data.json`。
- `.bat` 启停脚本内 `cd` 与 pythonw 路径是**本机绝对路径**，换机器需改为本机路径（或直接用上面的 `python live_server.py 8800` 命令）。

## 改动后必做
- 改了 `live_server.py` / `advanced_data.py` / `data_aggregator.py` 后，**必须 kill 占用 8800 的旧进程再重启**，否则新代码不生效。
- 验证：`curl -s "http://127.0.0.1:8800/api/advanced?refresh=1"` 应返回 `"ok":true,"source":"FRED + BIS"`。
