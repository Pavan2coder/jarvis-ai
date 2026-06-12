import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

from backend.api.routes import status, command
from backend.websocket.events import router as ws_router
from backend.utils import logger

app = FastAPI(title="J.A.R.V.I.S API Server", version="3.5.0")

# Enable CORS for frontend integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    import asyncio
    from backend.websocket.socket_manager import manager
    loop = asyncio.get_running_loop()
    manager.set_loop(loop)
    logger.info("FastAPI application instance started successfully. WebSocket loop bound.")

# Register routes
app.include_router(status.router, tags=["Status"])
app.include_router(command.router, tags=["Command"])
app.include_router(ws_router, tags=["WebSocket"])


# Setup static files paths
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
dist_dir = os.path.join(root_dir, "frontend", "dist")
fallback_hud_path = os.path.join(root_dir, "jarvis_hud.html")

def _load_hud_fallback():
    try:
        with open(fallback_hud_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Could not load fallback HUD HTML: {e}")
        return "<html><body><h1>J.A.R.V.I.S HUD Fallback</h1></body></html>"

@app.get("/", response_class=HTMLResponse)
@app.get("/hud", response_class=HTMLResponse)
async def serve_index():
    index_path = os.path.join(dist_dir, "index.html")
    if os.path.exists(index_path):
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading index.html: {e}")
    return _load_hud_fallback()

# Mount the static resources folder if built
if os.path.exists(dist_dir):
    app.mount("/", StaticFiles(directory=dist_dir), name="static")
else:
    logger.warning("Vite distribution folder not found. Running in HTML Fallback mode.")
