import json
import os
from http.server import BaseHTTPRequestHandler

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

SYSTEM_PROMPT = """You are Snakey, the helper bot inside a Snake and Ladder game.
Only answer about the game: rules, dice odds, strategy, and what snakes and ladders do.
Keep every answer under 4 sentences. If asked about anything else,
politely steer the player back to the game."""

MODEL = os.environ.get("OPENAI_MODEL", "gpt-5-nano")
USE_RESPONSES = os.environ.get("OPENAI_USE_RESPONSES", "false").lower() == "true"

llm = ChatOpenAI(model=MODEL, timeout=30, use_responses_api=USE_RESPONSES)


def to_text(content):
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in content if isinstance(b, dict))


class handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        body = json.dumps(payload).encode()
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

        if not message or len(message) > 300:
            return self._send(400, {"error": "message must be 1-300 characters"})

        try:
            result = llm.invoke(
                [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=message)],
                config={
                    "run_name": "snake-chat",
                    "tags": ["snake-ladder"],
                    "metadata": {"source": "game-widget"},
                },
            )
            self._send(200, {"reply": to_text(result.content)})
        except Exception:
            self._send(500, {"error": "bot error"})
