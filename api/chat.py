import json
import os
import traceback
from http.server import BaseHTTPRequestHandler

SYSTEM_PROMPT = """You are Snakey, the helper bot inside a Snake and Ladder game.
Only answer about the game: rules, dice odds, strategy, and what snakes and ladders do.
Keep every answer under 4 sentences. If asked about anything else,
politely steer the player back to the game."""


def to_text(content):
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in content if isinstance(b, dict))


def get_answer(message):
    # imports and client setup happen here so any error is caught and reported
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import SystemMessage, HumanMessage

    model = os.environ.get("OPENAI_MODEL", "gpt-5-nano")
    use_responses = os.environ.get("OPENAI_USE_RESPONSES", "false").lower() == "true"
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    llm = ChatOpenAI(model=model, api_key=api_key, timeout=30, max_retries=1, use_responses_api=use_responses)
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
            self._send(200, {"reply": get_answer(message)})
        except Exception as e:
            print("bot error:", type(e).__name__, "cause:", type(e.__cause__).__name__)
            # TEMPORARY: "detail" is for debugging. Remove it once the bot works.
            k = os.environ.get("OPENAI_API_KEY", "")
            diag = {
                "cause_type": type(e.__cause__).__name__,
                "key_len": len(k),
                "key_has_edge_whitespace": k != k.strip(),
                "key_is_ascii": k.isascii(),
                "key_starts_with_sk": k.startswith("sk-"),
            }
            self._send(500, {"error": "bot error", "type": type(e).__name__, "detail": str(e)[:300], "diag": diag})
