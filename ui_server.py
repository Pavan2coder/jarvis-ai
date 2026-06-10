import os
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import system_ops

ui_state = {
    "status": "idle",        # idle | listening | thinking | speaking
    "message": "Standing by...",
    "wake_source": "",
    "command": "",
    "response": "",
}

MINIMAL_HUD_FALLBACK = """<!DOCTYPE html>
<html>
<head><title>J.A.R.V.I.S — HUD Fallback</title></head>
<body style="background:#010a12;color:#00d4ff;font-family:sans-serif;padding:40px;text-align:center;">
<h1>J.A.R.V.I.S HUD</h1>
<p>HUD loaded in fallback mode. Please place <code>jarvis_hud.html</code> in the project directory.</p>
</body>
</html>"""

def _hud_html():
    """Serve the cinematic HUD from jarvis_hud.html (next to this script) if it
    exists; otherwise fall back to the embedded HUD so the app always works."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis_hud.html")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return MINIMAL_HUD_FALLBACK

class UIHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    def do_GET(self):
        if self.path == "/state":
            self._send_json(ui_state)
        elif self.path == "/stats":
            self._send_json(system_ops.get_live_stats())
        elif self.path in ("/", "/hud"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(_hud_html().encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress server logs

def start_ui_server():
    server = HTTPServer(("localhost", 5050), UIHandler)
    server.serve_forever()

def set_ui(status, message="", command="", response="", wake_source=""):
    ui_state["status"]     = status
    ui_state["message"]    = message or ui_state["message"]
    ui_state["command"]    = command
    ui_state["response"]   = response
    ui_state["wake_source"] = wake_source
