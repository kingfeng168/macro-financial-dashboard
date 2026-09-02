# -*- coding: utf-8 -*-
"""一键调用 CodeBuddy（腾讯云模型路由 CMR）审查/优化「进阶数据实时模块」。

用法（在用户机器上）：
  set CODEBUDDY_BASE_URL=https://<你的模型路由实例域名>/v1
  set CODEBUDDY_API_KEY=ck_xxxxxxxx
  python codebuddy_review_advanced.py

说明：
  - 仅用 Python 标准库，无需第三方依赖。
  - API Key 从环境变量读取，不写死在脚本里（敏感凭证不外泄）。
  - 端点为 OpenAI 兼容：{BASE_URL}/chat/completions，模型名默认 ModelRouter/auto。
  - 收集 advanced_data.py / live_server.py(/api/advanced 段) / generate_report.py(进阶 JS 段) 送检。
"""
import os
import sys
import json
import urllib.request

BASE = os.environ.get("CODEBUDDY_BASE_URL", "").rstrip("/")
KEY = os.environ.get("CODEBUDDY_API_KEY", "")

if not BASE or not KEY:
    print("✗ 缺少环境变量，无法调用 CodeBuddy。请先设置：")
    print('    set CODEBUDDY_BASE_URL=https://<你的模型路由实例域名>/v1')
    print('    set CODEBUDDY_API_KEY=ck_xxxx')
    print("实例域名在腾讯云控制台 console.cloud.tencent.com/clb/model-router 的实例配置中查看。")
    sys.exit(1)

PROJECT = os.path.dirname(os.path.abspath(__file__))


def _read(path, limit=16000):
    try:
        t = open(os.path.join(PROJECT, path), encoding="utf-8").read()
        return t[:limit]
    except Exception as e:
        return f"(读取失败: {e})"


segments = {
    "advanced_data.py (实时抓取核心)": _read("advanced_data.py"),
    "live_server.py (/api/advanced 路由段)": _read("live_server.py"),
    "generate_report.py (进阶面板 JS 段)": _read("generate_report.py"),
}

code_blob = "\n\n".join(
    f"===== {label} =====\n{text}" for label, text in segments.items()
)

prompt = (
    "你是资深 Python/前端工程师。请审查以下「全球金融日报」系统的【进阶数据实时模块】代码，"
    "该模块把原本 100% 静态快照的面板改造为实时（FRED 公开CSV + BIS SDMX，均免密钥）。目标：\n"
    "1. 评估 advanced_data.py 的 FRED 单次多序列请求 + BIS 并行抓取、容错回退（FRED 不可达回退 tips_breakeven 快照、BIS 不可达回退 eer_data 快照）的健壮性与性能；\n"
    "2. 评估前端 generate_report.py 中 fetchAdvanced 及 13 个 renderAdv* 渲染函数的正确性与边界处理（空值、缺字段、图表初始化失败）；\n"
    "3. 指出潜在 bug、异常/内存风险、可优化点；\n"
    "4. 若发现明确改进，给出具体 diff 或重写片段（保持中文注释、不引入第三方依赖、不改动 daily_data 快照数据结构）。\n"
    "只输出【审查结论 + 关键改进代码】，不要复述原代码全文。\n\n"
    + code_blob
)

payload = {
    "model": "ModelRouter/auto",
    "messages": [{"role": "user", "content": prompt}],
    "temperature": 0.3,
    "stream": False,
}

req = urllib.request.Request(
    BASE + "/chat/completions",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"},
)

print("→ 正在调用 CodeBuddy (%s) ...\n" % BASE)
try:
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.loads(r.read().decode("utf-8"))
    msg = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    print(msg)
    # 同时落盘，便于对比
    out = os.path.join(PROJECT, "codebuddy_advanced_review.md")
    open(out, "w", encoding="utf-8").write(msg)
    print("\n✓ 审查结果已保存至:", out)
except Exception as e:
    print("✗ 调用失败:", e)
    sys.exit(2)
