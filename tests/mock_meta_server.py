"""OFFLINE mock of the Meta Model API used for testing only (NOT the real API).
Modes: ok | 401 | badjson | investigation (returns a schema-shaped investigation that cites the
first evidence IDs it receives, clearly marked as MOCK)."""
import json, re, sys
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
        if MODE == "investigation":
            import time; time.sleep(3)          # lets the dashboard show the "analysing" state
            ids = re.findall(r'"evidence_id": "([^"]+)"', body["messages"][1]["content"])[:4] or ["none"]
            content = json.dumps({
                "summary": "MOCK RESPONSE (offline test server) - not produced by Muse Spark.",
                "situation": "MOCK situation text from the offline test server.",
                "scenarios": [{"scenario": "MOCK scenario", "how_it_could_develop": "mock", "plausibility": "possible",
                               "supporting_evidence_ids": ids[:1], "weakening_evidence_ids": ids[2:3],
                               "what_would_confirm": "mock"}],
                "limitations": ["MOCK limitation"],
                "observed_facts": [{"statement": "MOCK fact", "evidence_ids": ids[:2]}],
                "hypotheses": [{"cause": "MOCK hypothesis", "category": "other", "plausibility": "low",
                                "reasoning": "mock", "supporting_evidence_ids": ids[:1],
                                "contradicting_evidence_ids": ids[2:3], "how_to_verify": "mock"}],
                "escalation_pathway": [{"step": "MOCK step", "condition": "mock", "evidence_ids": ids[:1]}],
                "risk_assessment": {"ai_priority": "warning", "agrees_with_rule_severity": False, "rationale": "mock"},
                "missing_information": [{"item": "mock", "why_it_matters": "mock"}],
                "recommended_actions": [{"action": "MOCK action", "urgency": "within_24h", "reason": "mock",
                                         "evidence_ids": ids[:1] + ["not-a-real-id"], "responsible_role": "mock"}],
                "uncertainty": "mock"})
        else:
            content = json.dumps({"status": "ok", "model_role": "mock", "observation_count": 3})
            if MODE == "badjson": content = "not json"
        self._send(200, {"model": body["model"], "choices": [{"message": {"content": content}}], "usage": {"total_tokens": 1}})


HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
