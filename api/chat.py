import json
import os
from http.server import BaseHTTPRequestHandler

SYSTEM_PROMPT = (
    "You are Snakey, the helper bot inside a Snake and Ladder game. "
    "Only answer about the game: rules, dice odds, strategy, and what snakes "
    "and ladders do. Keep every answer under 4 sentences. If asked about "
    "anything else, politely steer the player back to the game."
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


def get_answer(message):
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import SystemMessage, HumanMessage

    model = (os.environ.get("OPENAI_MODEL") or "gpt-5-nano").strip()
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    llm = ChatOpenAI(model=model, api_key=api_key, timeout=30, max_retries=1)
    result = llm.invoke(
        [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=message)],
        config={
            "run_name": "snake-chat",
            "tags": ["snake-ladder"],
            "metadata": {"source": "game-widget"},
        },
    )
    return to_text(result.content)


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
            self._send(200, {"reply": get_answer(message)})
        except Exception as e:
            # Log the details privately (Vercel logs), never send them to visitors.
            print("bot error:", type(e).__name__, str(e)[:300])
            self._send(500, {"error": "bot error"})
