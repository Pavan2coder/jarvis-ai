import os
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from backend.system import system_ops

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
    """Serve the cinematic HUD from jarvis_hud.html (in project root) if it
    exists; otherwise fall back to the embedded HUD so the app always works."""
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(root_dir, "jarvis_hud.html")
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
        elif self.path.startswith("/command?"):
            from urllib.parse import urlparse, parse_qs
            import threading
            from backend.assistant import commands
            query = parse_qs(urlparse(self.path).query)
            text = query.get("text", [""])[0]
            if text:
                set_ui("thinking", message="Processing command...", command=text)
                threading.Thread(target=commands.handle_command, args=(text,), daemon=True).start()
                self._send_json({"status": "ok", "message": f"Command '{text}' queued."})
            else:
                self.send_response(400)
                self.end_headers()
        else:
            # Serve static files from frontend/dist
            clean_path = self.path.split('?')[0]
            if clean_path in ("/", "/hud"):
                clean_path = "/index.html"
            
            root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            dist_dir = os.path.join(root_dir, "frontend", "dist")
            file_path = os.path.join(dist_dir, clean_path.lstrip("/"))
            
            if os.path.exists(file_path) and os.path.isfile(file_path):
                self.send_response(200)
                ext = os.path.splitext(file_path)[1].lower()
                mime = {
                    ".html": "text/html",
                    ".js": "application/javascript",
                    ".css": "text/css",
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".svg": "image/svg+xml",
                    ".ico": "image/x-icon",
                    ".json": "application/json"
                }.get(ext, "application/octet-stream")
                self.send_header("Content-Type", mime)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                try:
                    with open(file_path, "rb") as f:
                        self.wfile.write(f.read())
                except Exception:
                    pass
            else:
                # Zero-Downtime Fallback to serve standalone jarvis_hud.html
                if clean_path == "/index.html":
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
