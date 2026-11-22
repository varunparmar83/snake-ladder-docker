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
    from langchain_mcp_adapters.client import MultiServerMCPClient
    from langchain_core.messages import SystemMessage, HumanMessage

    url = os.environ.get("MCP_SERVER_URL", "").strip()
    if not url:
        raise RuntimeError("MCP_SERVER_URL is not set")

    llm, _model = make_llm()

    # 1. Connect to the separate MCP server and ask which tools it has.
    client = MultiServerMCPClient({"dice": {"url": url, "transport": "streamable_http"}})
    tools = await client.get_tools()
    by_name = {t.name: t for t in tools}

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
