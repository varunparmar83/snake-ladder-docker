import asyncio
import json
import os
import re
from http.server import BaseHTTPRequestHandler

SYSTEM_PROMPT = (
    "You are Snakey, the helper bot inside a Snake and Ladder game. "
    "Only answer about the game: rules, dice odds, strategy, and what snakes "
    "and ladders do. Keep every answer under 4 sentences. If asked about "
    "anything else, politely steer the player back to the game."
)

MCP_SYSTEM_PROMPT = (
    "You are Snakey, the helper bot inside a Snake and Ladder game. "
    "For dice questions you must use the dice tools. After you get the tool "
    "result, explain it in under 4 sentences and say the numbers came from "
    "the dice tool."
)

# Words that mean "this is a dice question" -> use the MCP server, not the plain LLM.
DICE_WORDS = re.compile(
    r"\b(dice|die|roll|rolls|rolled|rolling|ludo|odds|probability|chance|chances)\b",
    re.IGNORECASE,
)


def to_text(content):
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, dict) and "text" in block:
            parts.append(block["text"])
        elif isinstance(block, str):
            parts.append(block)
    return "".join(parts)


def make_llm():
    from langchain_litellm import ChatLiteLLM

    model = (os.environ.get("LLM_MODEL") or "openai/gpt-5-nano").strip()
    api_key = (os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip()
    llm = ChatLiteLLM(model=model, api_key=api_key, request_timeout=30, max_retries=1)
    return llm, model


class McpClient:
    """Tiny MCP client over HTTP (JSON-RPC 2.0): initialize, tools/list, tools/call."""

    def __init__(self, url, timeout=20):
        self.url = url
        self.timeout = timeout
        self.session_id = None
        self._next_id = 0

    async def _rpc(self, http, method, params=None, notify=False):
        payload = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        if not notify:
            self._next_id += 1
            payload["id"] = self._next_id
        headers = {"Accept": "application/json, text/event-stream"}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        resp = await http.post(self.url, json=payload, headers=headers)
        resp.raise_for_status()
        if resp.headers.get("Mcp-Session-Id"):
            self.session_id = resp.headers["Mcp-Session-Id"]
        if notify or resp.status_code == 202 or not resp.content:
            return None
        if "text/event-stream" in resp.headers.get("content-type", ""):
            last = None
            for line in resp.text.splitlines():
                if line.startswith("data:"):
                    last = json.loads(line[5:].strip())
            data = last or {}
        else:
            data = resp.json()
        if "error" in data:
            raise RuntimeError("MCP error: " + str(data["error"].get("message")))
        return data.get("result")

    async def load_tools(self):
        """Handshake with the server and return its tools as LangChain tools."""
        import httpx
        from langchain_core.tools import StructuredTool, ToolException

        http = httpx.AsyncClient(timeout=self.timeout)
        await self._rpc(http, "initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "snakey-chat", "version": "1.0.0"},
        })
        await self._rpc(http, "notifications/initialized", notify=True)
        listed = await self._rpc(http, "tools/list", {})

        def wrap(spec):
            async def run(**kwargs):
                result = await self._rpc(http, "tools/call", {"name": spec["name"], "arguments": kwargs})
                text = "".join(b.get("text", "") for b in result.get("content", []))
                if result.get("isError"):
                    raise ToolException(text)
                return text

            return StructuredTool.from_function(
                coroutine=run,
                name=spec["name"],
                description=spec.get("description", ""),
                args_schema=spec.get("inputSchema") or {"type": "object", "properties": {}},
                handle_tool_error=True,
            )

        tools = [wrap(t) for t in listed.get("tools", [])]
        return tools, http


def plain_answer(message):
    from langchain_core.messages import SystemMessage, HumanMessage

    llm, model = make_llm()
    result = llm.invoke(
        [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=message)],
        config={
            "run_name": "snake-chat",
            "tags": ["snake-ladder", "litellm", "plain-llm"],
            "metadata": {"source": "game-widget", "route": "plain", "model": model},
        },
    )
    return to_text(result.content)


async def mcp_flow(message, config=None):
    from langchain_core.messages import SystemMessage, HumanMessage

    url = os.environ.get("MCP_SERVER_URL", "").strip()
    if not url:
        raise RuntimeError("MCP_SERVER_URL is not set")

    llm, _model = make_llm()

    # 1. Connect to the separate MCP server and ask which tools it has.
    tools, http = await McpClient(url).load_tools()
    by_name = {t.name: t for t in tools}

    try:
        # 2. Let the model pick a tool and its arguments (it must pick one).
        msgs = [SystemMessage(content=MCP_SYSTEM_PROMPT), HumanMessage(content=message)]
        ai = await llm.bind_tools(tools, tool_choice="required").ainvoke(msgs, config=config)
        if not ai.tool_calls:
            return {"reply": to_text(ai.content), "tools": []}
        msgs.append(ai)

        # 3. Run each chosen tool on the MCP server (each shows up as a tool run in LangSmith).
        used = []
        for call in ai.tool_calls:
            tool = by_name.get(call["name"])
            if tool is None:
                continue
            msgs.append(await tool.ainvoke(call, config=config))
            used.append(call["name"])

        # 4. Let the model explain the tool result to the player.
        final = await llm.ainvoke(msgs, config=config)
        return {"reply": to_text(final.content), "tools": used}
    finally:
        await http.aclose()


def mcp_answer(message):
    from langchain_core.runnables import RunnableLambda

    url = os.environ.get("MCP_SERVER_URL", "").strip()
    flow = RunnableLambda(mcp_flow)
    return asyncio.run(
        flow.ainvoke(
            message,
            config={
                "run_name": "snake-chat-mcp",
                "tags": ["snake-ladder", "litellm", "mcp"],
                "metadata": {"source": "game-widget", "route": "mcp", "mcp_server": url},
            },
        )
    )


class handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length) or b"{}")
            message = str(data.get("message", "")).strip()
        except Exception:
            return self._send(400, {"error": "bad request"})

        if not 1 <= len(message) <= 300:
            return self._send(400, {"error": "message must be 1-300 characters"})

        try:
            if DICE_WORDS.search(message):
                try:
                    out = mcp_answer(message)
                    return self._send(200, {"reply": out["reply"], "via": "mcp", "tools": out["tools"]})
                except Exception as e:
                    print("mcp error, falling back:", type(e).__name__, str(e)[:300])
                    return self._send(200, {"reply": plain_answer(message), "via": "llm-fallback"})
            self._send(200, {"reply": plain_answer(message), "via": "llm"})
        except Exception as e:
            print("bot error:", type(e).__name__, str(e)[:300])
            self._send(500, {"error": "bot error"})
