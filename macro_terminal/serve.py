"""Local server (127.0.0.1) that serves output/site/ and answers POST /api/ask; the public page shows preset answers."""

from __future__ import annotations

import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from . import config
from .ask import ask_live

_calls = {"n": 0}


class Handler(SimpleHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        if self.path != "/api/ask":
            self.send_error(404)
            return
        try:
            body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 4000)) or b"{}")
            question = str(body.get("question", "")).strip()
            if not 3 <= len(question) <= 300:
                raise ValueError("question must have 3 to 300 characters")
            if _calls["n"] >= config.SERVE_MAX_CALLS:
                raise RuntimeError(f"limit of {config.SERVE_MAX_CALLS} questions per server session reached")
            _calls["n"] += 1
            res, code = ask_live(question), 200
        except Exception as e:  # noqa: BLE001
            res, code = {"error": f"{type(e).__name__}: {str(e)[:200]}"}, 400
        data = json.dumps(res, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def serve(port: int = 8899) -> None:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=str(config.SITE)))
    print(f"Macro Terminal on http://127.0.0.1:{port}/  (live questions in the ASK tab; Ctrl+C to stop)")
    httpd.serve_forever()
