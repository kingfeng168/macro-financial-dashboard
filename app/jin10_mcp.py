# -*- coding: utf-8 -*-
"""金十数据 MCP 客户端（标准 MCP Streamable HTTP + Bearer Token）。

标准 MCP 流程：
    initialize -> notifications/initialized -> tools/list|resources/list -> tools/call

实现要点（均已实测验证）：
- 协议版本 2025-11-25
- 响应为 SSE（Content-Type: text/event-stream），必须从 `data:` 行提取 JSON，
  直接 json.loads(body) 会失败
- 服务端不返回 Mcp-Session-Id → 按**无状态模式**处理，每次请求独立带 Bearer，
  无需维护会话；握手只需在每个进程内做一次
- 结果优先读 result.structuredContent；result.content 仅作可读文本补充，
  不作为机器解析来源
- 列表分页：请求参数 cursor / 响应 data.next_cursor / data.has_more

限流：每个工具每天 1500 次（北京时间自然日统计，次日重置）。
超出后返回业务错误 "今日该工具调用次数已达上限，请明日再试"。
"""
import json
import os
import ssl
import threading
import urllib.request
import urllib.error

MCP_URL = "https://mcp.jin10.com/mcp"
PROTOCOL_VERSION = "2025-11-25"

# 公开分发版：Token 仅通过环境变量 JIN10_MCP_TOKEN 提供，不在代码中硬编码。
#   设置： Windows: set JIN10_MCP_TOKEN=你的token   Linux/Mac: export JIN10_MCP_TOKEN=你的token
#   未设置时金十快讯自动回退 flash_newest.js 抓取通道，仍保持实时（仅丢失详情页 url）。
JIN10_TOKEN = os.environ.get("JIN10_MCP_TOKEN") or ""

DEFAULT_TIMEOUT = 20


class Jin10MCPError(Exception):
    """MCP 协议错误（JSON-RPC error）或工具业务错误（isError=true）。"""


class Jin10MCP:
    """金十 MCP 客户端。首次调用任意方法时自动完成握手。"""

    def __init__(self, token=None, url=None, timeout=DEFAULT_TIMEOUT):
        self.token = (token or JIN10_TOKEN or "").strip()
        self.url = url or MCP_URL
        self.timeout = timeout
        self._seq = 0
        self._ready = False
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        self._ssl = ctx

    # ---------------- 传输层 ----------------
    def _next_id(self):
        self._seq += 1
        return self._seq

    def _post(self, payload):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.url, data=data, method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "Authorization": "Bearer " + self.token,
                "User-Agent": "workbuddy-jin10-mcp/1.0",
            })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self._ssl) as r:
                return r.status, r.headers.get("Content-Type", ""), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get("Content-Type", ""), e.read().decode("utf-8", "replace")

    @staticmethod
    def _decode(status, content_type, body):
        """SSE 或 JSON 响应 → dict。SSE 时从 `data:` 行提取 JSON。"""
        if "text/event-stream" in (content_type or ""):
            for line in body.split("\n"):
                if line.startswith("data:"):
                    payload = line[5:].strip()
                    if payload:
                        try:
                            return json.loads(payload)
                        except ValueError:
                            continue
            raise Jin10MCPError("SSE 响应未找到可解析的 data 行 (status=%s)" % status)
        try:
            return json.loads(body)
        except ValueError:
            raise Jin10MCPError("响应非 JSON (status=%s): %s" % (status, body[:200]))

    def _rpc(self, method, params=None, notify=False):
        payload = {"jsonrpc": "2.0", "method": method}
        if not notify:
            payload["id"] = self._next_id()
        if params is not None:
            payload["params"] = params
        status, ct, body = self._post(payload)
        if notify:
            # 通知无响应体；服务端一般回 202 Accepted
            if status >= 400:
                raise Jin10MCPError("通知 %s 被拒 (status=%s)" % (method, status))
            return {"ok": True}
        msg = self._decode(status, ct, body) if body.strip() else {}
        if msg.get("error"):
            err = msg["error"]
            raise Jin10MCPError("JSON-RPC error %s: %s" % (err.get("code"), err.get("message")))
        return msg.get("result", {})

    # ---------------- 握手 ----------------
    def initialize(self):
        result = self._rpc("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "workbuddy-financial-daily", "version": "1.0.0"},
        })
        self._rpc("notifications/initialized", notify=True)
        self._ready = True
        return result

    def _ensure_ready(self):
        if not self._ready:
            if not self.token:
                raise Jin10MCPError("未配置 JIN10_MCP_TOKEN")
            self.initialize()

    # ---------------- 能力发现 ----------------
    def list_tools(self):
        self._ensure_ready()
        return self._rpc("tools/list").get("tools", [])

    def list_resources(self):
        self._ensure_ready()
        return self._rpc("resources/list").get("resources", [])

    # ---------------- 调用 ----------------
    def call_tool(self, name, arguments=None):
        """调用工具，返回 result.structuredContent（dict）。

        structuredContent 缺失时抛错——按约定 content 仅作可读补充，
        不作为机器解析来源，故不静默降级为文本。
        """
        self._ensure_ready()
        result = self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
        if result.get("isError"):
            text = "\n".join(
                c.get("text", "") for c in result.get("content", []) if isinstance(c, dict))
            raise Jin10MCPError("工具 %s 业务错误: %s" % (name, text[:200]))
        sc = result.get("structuredContent")
        if isinstance(sc, dict):
            return sc
        text = "\n".join(
            c.get("text", "") for c in result.get("content", []) if isinstance(c, dict))
        raise Jin10MCPError("工具 %s 未返回 structuredContent；文本: %s" % (name, text[:200]))

    def read_resource(self, uri):
        """读取资源，返回文本正文。"""
        self._ensure_ready()
        result = self._rpc("resources/read", {"uri": uri})
        contents = result.get("contents", []) or []
        return contents[0].get("text", "") if contents else ""

    # ---------------- 分页遍历 ----------------
    def iter_paged(self, tool, max_pages=3, extra_args=None, item_key="items"):
        """按 cursor / next_cursor / has_more 约定翻页遍历列表类工具，产出原始 item。

        max_pages 控制最多翻多少页（list_flash 实测 20 条/页）。
        """
        cursor = None
        for _ in range(max(1, int(max_pages))):
            args = dict(extra_args or {})
            if cursor:
                args["cursor"] = cursor
            data = self.call_tool(tool, args).get("data", {}) or {}
            for it in data.get(item_key, []) or []:
                yield it
            if not data.get("has_more") or not data.get("next_cursor"):
                break
            cursor = data["next_cursor"]


# ---------------- 客户端实例复用 ----------------
# 握手（initialize + notifications/initialized）每进程只需一次。
# live_server 常驻且自动更新每 5 分钟触发一次，若每次新建实例会多一次无谓往返；
# 注意限流只针对 tools/call，握手不计入，但省下的往返能明显降低刷新延迟。
_CLIENT = None
_CLIENT_LOCK = threading.Lock()


def _get_client(timeout=DEFAULT_TIMEOUT):
    """获取（必要时创建）共享客户端实例，线程安全。"""
    global _CLIENT
    if _CLIENT is None:
        with _CLIENT_LOCK:
            if _CLIENT is None:
                _CLIENT = Jin10MCP(timeout=timeout)
    return _CLIENT


def _reset_client():
    """调用失败时丢弃实例，下次重新握手（避免复用处于坏状态的连接）。"""
    global _CLIENT
    with _CLIENT_LOCK:
        _CLIENT = None


# ---------------- 模块级便利函数 ----------------
def fetch_flash_raw(limit=20, max_pages=3, timeout=DEFAULT_TIMEOUT):
    """取金十快讯原始 item 列表（最多 max_pages 页后截断到 limit 条）。

    返回 ([raw_item, ...], err)。raw_item 形如 {content, time, url}。
    """
    try:
        cli = _get_client(timeout)
        out = []
        for it in cli.iter_paged("list_flash", max_pages=max_pages):
            out.append(it)
            if len(out) >= limit:
                break
        return out, None
    except Exception as e:
        _reset_client()
        return [], str(e)


def fetch_calendar_raw(timeout=DEFAULT_TIMEOUT):
    """取金十财经日历（当前自然周）。返回 (list, err)。"""
    try:
        data = _get_client(timeout).call_tool("list_calendar", {}).get("data", [])
        return (data if isinstance(data, list) else []), None
    except Exception as e:
        _reset_client()
        return [], str(e)


def fetch_quote_raw(code, timeout=DEFAULT_TIMEOUT):
    """取单个品种实时行情。返回 (dict, err)。"""
    try:
        d = _get_client(timeout).call_tool("get_quote", {"code": code}).get("data", {})
        return (d or {}), None
    except Exception as e:
        _reset_client()
        return {}, str(e)


if __name__ == "__main__":
    # 冒烟测试：握手 + 快讯 + 行情
    c = Jin10MCP()
    info = c.initialize()
    print("server:", info.get("serverInfo", {}).get("name"),
          "| protocol:", info.get("protocolVersion"))
    print("tools:", [t.get("name") for t in c.list_tools()])
    items, err = fetch_flash_raw(limit=5)
    print("flash err:", err, "| count:", len(items))
    for it in items[:3]:
        print("   -", (it.get("time") or "")[:19], "|", (it.get("content") or "")[:52])
    q, qerr = fetch_quote_raw("XAUUSD")
    print("quote err:", qerr, "| XAUUSD:", q.get("close"), q.get("name"))
