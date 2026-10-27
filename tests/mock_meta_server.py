"""Offline mock of the two Meta Model API endpoints used by the connection check (for testing only)."""
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
MODE = sys.argv[2] if len(sys.argv) > 2 else "ok"
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code)
        self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if MODE == "401": return self._send(401, {"error": {"message": "invalid key"}})
        self._send(200, {"object": "list", "data": [{"id": "muse-spark-1.3"}, {"id": "sam-3.1"}]})
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert body["response_format"]["type"] == "json_schema"
        content = json.dumps({"status": "ok", "model_role": "mock", "observation_count": 3})
        if MODE == "badjson": content = "not json"
        self._send(200, {"model": body["model"], "choices": [{"message": {"content": content}}], "usage": {"total_tokens": 1}})
HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
