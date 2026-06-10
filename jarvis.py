"""
╔══════════════════════════════════════════════════════════════╗
║         J.A.R.V.I.S  —  Just A Rather Very Intelligent System ║
║              Full Version — with UI + Spotify + Folders        ║
╚══════════════════════════════════════════════════════════════╝

INSTALL:
    pip install speechrecognition pyaudio pyttsx3 numpy flask flask-cors

If pyaudio fails on Windows:
    pip install pipwin && pipwin install pyaudio

RUN:
    python jarvis.py
    Then open jarvis_ui.html in your browser (keep both running!)
"""

import speech_recognition as sr
import pyttsx3
import numpy as np
import pyaudio
import threading
import time
import datetime
import subprocess
import sys
import os
import random
import webbrowser
import json
import ctypes
from http.server import HTTPServer, BaseHTTPRequestHandler

# Force UTF-8 console output so the emoji / box-drawing prints never crash on
# a Windows cp1252 codepage (and so logs survive being piped to a file).
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# ══════════════════════════════════════════════
# ⚙️  CONFIGURATION
# ══════════════════════════════════════════════

WAKE_WORD          = "jarvis"
CLAP_COOLDOWN      = 0.20   # min seconds between the two claps
DOUBLE_CLAP_WINDOW = 1.20   # max seconds between the two claps
YOUR_NAME          = "Boss"
YOUR_CITY          = "Hyderabad"

# 🗣️  WAKE-WORD-FREE MODE
#    True  → just say the command ("open youtube", "what time is it") and it runs.
#            No need to say "Jarvis" first. (Clap + "Jarvis" still work too.)
#    False → classic mode: you must wake it with a clap or "Jarvis" first.
ALWAYS_LISTEN  = True
#    With ALWAYS_LISTEN, only act on phrases that contain a command/question word
#    below — this stops Jarvis reacting to every bit of background chatter.
#    Set REQUIRE_TRIGGER = False to act on absolutely everything you say.
REQUIRE_TRIGGER = True
COMMAND_TRIGGERS = [
    # actions
    "open", "close", "launch", "start", "kill", "shut", "shutdown", "restart",
    "reboot", "lock", "sleep", "play", "pause", "search", "google", "youtube",
    "spotify", "music", "song", "playlist", "screenshot", "mute", "silence",
    "volume", "louder", "quieter", "brightness", "dim",
    # info / system
    "time", "clock", "date", "today", "weather", "temperature", "forecast",
    "battery", "cpu", "processor", "ram", "memory", "gpu", "graphics", "ip",
    "joke", "funny",
    # apps / folders
    "notepad", "calculator", "calc", "paint", "word", "excel", "powerpoint",
    "chrome", "edge", "firefox", "browser", "settings", "camera", "explorer",
    "task manager", "powershell", "cmd", "folder", "directory", "desktop",
    "downloads", "documents", "pictures", "videos", "vs code", "vscode",
    # conversation / questions (lets you just ask Jarvis things)
    "what", "who", "how", "why", "when", "where", "which", "tell me", "tell",
    "can you", "do you", "explain", "define", "calculate", "translate",
    "hello", "hey", "goodbye", "bye", "exit", "quit",
]

def has_command_trigger(text):
    """True if the phrase contains a trigger word as a WHOLE word — so 'day'
    won't fire on 'yesterday', and 'play' won't fire on 'player'."""
    import re
    for k in COMMAND_TRIGGERS:
        if re.search(r"\b" + re.escape(k) + r"\b", text):
            return True
    return False

# 🎧 AUDIO — these are AUTO-CALIBRATED at startup from your room's noise.
#    The values below are only fallbacks if calibration fails.
SAMPLE_RATE        = 16000
CHUNK              = 1024
SPEECH_THRESHOLD   = 350     # auto-tuned at boot
CLAP_THRESHOLD     = 3000    # auto-tuned at boot

# 🧠 GEMINI AI BRAIN
#    Get a free key at:  https://aistudio.google.com/app/apikey
#    Put it in a .env file next to this script:  GEMINI_API_KEY=your_key_here

def _load_dotenv():
    """Tiny .env loader (no extra package). Reads KEY=VALUE lines."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                val = val.strip().strip('"').strip("'")
                os.environ.setdefault(key.strip(), val)
    except Exception as e:
        print(f"  ⚠️  Could not read .env: {e}")

_load_dotenv()
GEMINI_API_KEY     = os.environ.get("GEMINI_API_KEY", "")   # loaded from .env above
GEMINI_MODEL       = "gemini-2.5-flash"   # auto-corrected at boot if unavailable

# 🖥️ APP SHORTCUTS — friendly name → how to launch it (Windows)
APPS = {
    "chrome":      "chrome",
    "edge":        "msedge",
    "firefox":     "firefox",
    "notepad":     "notepad",
    "calculator":  "calc",
    "paint":       "mspaint",
    "word":        "winword",
    "excel":       "excel",
    "powerpoint":  "powerpnt",
    "explorer":    "explorer",
    "file manager":"explorer",
    "cmd":         "cmd",
    "command prompt":"cmd",
    "powershell":  "powershell",
    "task manager":"taskmgr",
    "settings":    "ms-settings:",
    "camera":      "microsoft.windows.camera:",
    "spotify":     "spotify",
    "vs code":     "code",
    "vscode":      "code",
}

# ❌ CLOSE SHORTCUTS — friendly name → Windows process image name(s) to kill.
#    (explorer is deliberately NOT here — killing explorer.exe crashes the desktop.)
CLOSE_PROCESSES = {
    "chrome":       ["chrome.exe"],
    "edge":         ["msedge.exe"],
    "firefox":      ["firefox.exe"],
    "browser":      ["chrome.exe", "msedge.exe", "firefox.exe"],
    "notepad":      ["notepad.exe"],
    "calculator":   ["CalculatorApp.exe", "Calculator.exe"],
    "calc":         ["CalculatorApp.exe", "Calculator.exe"],
    "paint":        ["mspaint.exe"],
    "word":         ["winword.exe"],
    "excel":        ["excel.exe"],
    "powerpoint":   ["powerpnt.exe"],
    "cmd":          ["cmd.exe"],
    "command prompt":["cmd.exe"],
    "powershell":   ["powershell.exe"],
    "task manager": ["taskmgr.exe"],
    "spotify":      ["spotify.exe"],
    "vs code":      ["Code.exe"],
    "vscode":       ["Code.exe"],
    "camera":       ["WindowsCamera.exe"],
}

# Things that live as a browser TAB, not a standalone process. "Closing" these
# means closing the currently-focused browser tab (Ctrl+W).
WEB_TAB_WORDS = ["youtube", "google", "gmail", "tab", "website", "web page", "webpage"]

# 📁 FOLDER SHORTCUTS — edit these to your actual paths!
FOLDERS = {
    "desktop":   os.path.join(os.path.expanduser("~"), "Desktop"),
    "downloads": os.path.join(os.path.expanduser("~"), "Downloads"),
    "documents": os.path.join(os.path.expanduser("~"), "Documents"),
    "pictures":  os.path.join(os.path.expanduser("~"), "Pictures"),
    "music":     os.path.join(os.path.expanduser("~"), "Music"),
    "videos":    os.path.join(os.path.expanduser("~"), "Videos"),
    "projects":  os.path.join(os.path.expanduser("~"), "Projects"),  # change if needed
}

# 🎵 SPOTIFY — set your playlist/song URLs here
SPOTIFY_PLAYLISTS = {
    "chill":    "https://open.spotify.com/playlist/37i9dQZF1DX4WYpdgoIcn6",
    "focus":    "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",
    "workout":  "https://open.spotify.com/playlist/37i9dQZF1DX76Wlfdnj7AP",
    "party":    "https://open.spotify.com/playlist/37i9dQZF1DXaXB8fQg7xif",
    "sleep":    "https://open.spotify.com/playlist/37i9dQZF1DWZd79rJ6a7lp",
    "default":  "https://open.spotify.com/",
}

# ══════════════════════════════════════════════
# 🌐  UI BRIDGE SERVER (talks to jarvis_ui.html)
# ══════════════════════════════════════════════

ui_state = {
    "status": "idle",        # idle | listening | thinking | speaking
    "message": "Standing by...",
    "wake_source": "",
    "command": "",
    "response": "",
}

# ── EMBEDDED HUD HTML (no external file needed!) ──
JARVIS_HUD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>J.A.R.V.I.S — HUD Interface</title>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700;900&family=Share+Tech+Mono&display=swap" rel="stylesheet"/>
<style>
* { margin:0; padding:0; box-sizing:border-box; }

:root {
  --blue:   #00d4ff;
  --blue2:  #0088cc;
  --gold:   #f0c040;
  --red:    #ff3333;
  --green:  #00ff88;
  --dark:   #010a12;
  --panel:  rgba(0,30,50,0.7);
  --border: rgba(0,212,255,0.25);
}

html, body {
  width:100%; height:100%;
  background: var(--dark);
  overflow: hidden;
  font-family: 'Share Tech Mono', monospace;
  color: var(--blue);
  cursor: crosshair;
}

/* ── CANVAS BG ── */
canvas#bg {
  position: fixed;
  inset: 0;
  z-index: 0;
}

/* ── SCANLINES ── */
body::after {
  content:'';
  position:fixed; inset:0;
  background: repeating-linear-gradient(
    0deg,
    transparent,
    transparent 2px,
    rgba(0,0,0,0.08) 2px,
    rgba(0,0,0,0.08) 4px
  );
  pointer-events:none;
  z-index: 100;
}

/* ── MAIN LAYOUT ── */
.hud {
  position: relative;
  width: 100vw;
  height: 100vh;
  z-index: 10;
  display: grid;
  grid-template-rows: 60px 1fr 80px;
  grid-template-columns: 220px 1fr 220px;
  gap: 0;
  padding: 10px;
}

/* ── TOP BAR ── */
.top-bar {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--border);
  padding: 0 16px;
  margin-bottom: 8px;
}

.logo {
  font-family: 'Orbitron', sans-serif;
  font-size: 1.4rem;
  font-weight: 900;
  letter-spacing: 8px;
  color: #fff;
  text-shadow: 0 0 20px var(--blue), 0 0 40px rgba(0,212,255,0.3);
}

.logo span { color: var(--gold); }

.top-info {
  display: flex;
  gap: 30px;
  font-size: 0.7rem;
  letter-spacing: 2px;
  opacity: 0.7;
}

.top-info .val { color: #fff; }

/* ── SIDE PANELS ── */
.panel-left, .panel-right {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 4px;
}

.widget {
  background: var(--panel);
  border: 1px solid var(--border);
  padding: 12px;
  position: relative;
  clip-path: polygon(0 0, calc(100% - 10px) 0, 100% 10px, 100% 100%, 10px 100%, 0 calc(100% - 10px));
  backdrop-filter: blur(4px);
}

.widget-title {
  font-size: 0.6rem;
  letter-spacing: 3px;
  color: var(--blue);
  opacity: 0.6;
  margin-bottom: 8px;
  text-transform: uppercase;
}

/* ── ARC REACTOR (CENTER) ── */
.center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  position: relative;
  gap: 20px;
}

/* Outer ring system */
.rings {
  position: relative;
  width: 280px;
  height: 280px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.ring {
  position: absolute;
  border-radius: 50%;
  border: 1px solid var(--blue);
  opacity: 0.4;
  animation: spin linear infinite;
}

.ring:nth-child(1) { width:280px; height:280px; animation-duration:20s; border-style:dashed; }
.ring:nth-child(2) { width:240px; height:240px; animation-duration:14s; animation-direction:reverse; border-color:rgba(0,212,255,0.6); opacity:0.5; }
.ring:nth-child(3) { width:200px; height:200px; animation-duration:9s;  border-color:var(--gold); opacity:0.3; }
.ring:nth-child(4) { width:165px; height:165px; animation-duration:5s;  animation-direction:reverse; }

/* Tick marks on ring 1 */
.ring:nth-child(1)::before {
  content:'';
  position:absolute;
  top:-3px; left:50%;
  transform:translateX(-50%);
  width:6px; height:6px;
  border-radius:50%;
  background: var(--blue);
  box-shadow: 0 0 10px var(--blue);
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}

/* Core */
.core {
  position: relative;
  width: 120px;
  height: 120px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 5;
}

.core-glow {
  position: absolute;
  inset: -20px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(0,212,255,0.15) 0%, transparent 70%);
  animation: breathe 3s ease-in-out infinite;
}

.core-ring {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 2px solid var(--blue);
  box-shadow: 0 0 20px var(--blue), inset 0 0 20px rgba(0,212,255,0.2);
}

.core-inner {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: radial-gradient(circle at 35% 35%, #00aacc, #003355, #010a12);
  box-shadow: 0 0 40px rgba(0,212,255,0.8), inset 0 0 20px rgba(0,50,80,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: 'Orbitron', sans-serif;
  font-size: 0.45rem;
  font-weight: 700;
  letter-spacing: 1px;
  color: rgba(255,255,255,0.5);
  animation: breathe 3s ease-in-out infinite;
}

@keyframes breathe {
  0%,100% { opacity:1; transform:scale(1); }
  50%      { opacity:0.7; transform:scale(0.97); }
}

/* ── STATUS DISPLAY ── */
.status-wrap {
  text-align: center;
  width: 100%;
}

.status-label {
  font-size: 0.6rem;
  letter-spacing: 4px;
  opacity: 0.5;
  margin-bottom: 6px;
}

.status-text {
  font-family: 'Orbitron', sans-serif;
  font-size: 1.1rem;
  font-weight: 700;
  letter-spacing: 3px;
  color: #fff;
  text-shadow: 0 0 15px var(--blue);
  min-height: 1.5rem;
  transition: all 0.4s ease;
}

.status-text.active  { color: var(--green); text-shadow: 0 0 20px var(--green); }
.status-text.listen  { color: var(--gold);  text-shadow: 0 0 20px var(--gold); }
.status-text.speak   { color: var(--blue);  text-shadow: 0 0 20px var(--blue); animation: flicker 0.1s infinite; }
.status-text.think   { color: #ff9500;      text-shadow: 0 0 20px #ff9500; }

@keyframes flicker {
  0%,100% { opacity:1; }
  50%      { opacity:0.85; }
}

/* ── COMMAND / RESPONSE DISPLAY ── */
.cmd-display {
  width: 100%;
  max-width: 420px;
  text-align: center;
}

.cmd-box {
  background: rgba(0,212,255,0.05);
  border: 1px solid var(--border);
  padding: 8px 14px;
  font-size: 0.72rem;
  margin-bottom: 6px;
  min-height: 30px;
  letter-spacing: 1px;
  transition: all 0.3s;
  word-break: break-word;
}

.cmd-box .label {
  font-size: 0.55rem;
  opacity: 0.5;
  letter-spacing: 3px;
  display:block;
  margin-bottom:4px;
}

/* ── WAVEFORM ── */
.waveform {
  display: flex;
  align-items: center;
  gap: 3px;
  height: 40px;
  justify-content: center;
}

.wave-bar {
  width: 3px;
  background: var(--blue);
  border-radius: 2px;
  transition: height 0.1s ease;
  box-shadow: 0 0 4px var(--blue);
  opacity: 0.7;
}

/* ── PROGRESS BARS ── */
.bar-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 0.65rem;
  letter-spacing: 1px;
}

.bar-label { width: 30px; opacity: 0.6; flex-shrink:0; }

.bar-track {
  flex:1;
  height: 4px;
  background: rgba(0,212,255,0.1);
  border: 1px solid rgba(0,212,255,0.2);
  border-radius: 1px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  background: linear-gradient(to right, var(--blue2), var(--blue));
  box-shadow: 0 0 6px var(--blue);
  border-radius: 1px;
  transition: width 1s ease;
}

.bar-val { width: 32px; text-align:right; opacity:0.8; font-size:0.6rem; }

/* ── COMMAND LIST ── */
.cmd-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.cmd-item {
  font-size: 0.62rem;
  padding: 4px 6px;
  border-left: 2px solid rgba(0,212,255,0.3);
  opacity: 0.7;
  letter-spacing: 0.5px;
  transition: all 0.2s;
}

.cmd-item:hover {
  opacity: 1;
  border-left-color: var(--blue);
  background: rgba(0,212,255,0.05);
}

.cmd-item .key { color: var(--gold); }

/* ── WAKE SOURCE INDICATOR ── */
.wake-badge {
  font-size: 0.6rem;
  letter-spacing: 2px;
  padding: 3px 10px;
  border: 1px solid rgba(0,255,136,0.3);
  color: var(--green);
  display: inline-block;
  opacity: 0;
  transition: opacity 0.4s;
}

.wake-badge.show { opacity: 1; }

/* ── BOTTOM BAR ── */
.bottom-bar {
  grid-column: 1 / -1;
  border-top: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  font-size: 0.6rem;
  letter-spacing: 2px;
  opacity: 0.5;
  margin-top: 8px;
}

/* ── CORNER DECORATIONS ── */
.corner {
  position: fixed;
  width: 40px;
  height: 40px;
  z-index: 200;
}

.corner-tl { top:10px; left:10px; border-top:2px solid var(--blue); border-left:2px solid var(--blue); }
.corner-tr { top:10px; right:10px; border-top:2px solid var(--blue); border-right:2px solid var(--blue); }
.corner-bl { bottom:10px; left:10px; border-bottom:2px solid var(--blue); border-left:2px solid var(--blue); }
.corner-br { bottom:10px; right:10px; border-bottom:2px solid var(--blue); border-right:2px solid var(--blue); }

/* ── ALERT FLASH ── */
.alert-ring {
  position: absolute;
  inset: -30px;
  border-radius: 50%;
  border: 3px solid transparent;
  pointer-events: none;
  transition: all 0.3s;
}

.alert-ring.active-flash {
  border-color: var(--green);
  box-shadow: 0 0 40px var(--green), inset 0 0 40px rgba(0,255,136,0.1);
  animation: flash-pulse 0.6s ease-out forwards;
}

.alert-ring.listen-flash {
  border-color: var(--gold);
  box-shadow: 0 0 40px var(--gold);
  animation: flash-pulse 0.6s ease-out forwards;
}

@keyframes flash-pulse {
  0%   { opacity:1; transform:scale(1); }
  100% { opacity:0; transform:scale(1.3); }
}

/* ── CLOCK ── */
.clock {
  font-family:'Orbitron',sans-serif;
  font-size:1rem;
  letter-spacing:3px;
  color:#fff;
  opacity:0.8;
}

/* ── SPOTIFY WIDGET ── */
.spotify-icon {
  display:inline-block;
  width:8px; height:8px;
  border-radius:50%;
  background:#1db954;
  box-shadow:0 0 6px #1db954;
  margin-right:6px;
}
</style>
</head>
<body>

<!-- Canvas particle background -->
<canvas id="bg"></canvas>

<!-- Corner decorations -->
<div class="corner corner-tl"></div>
<div class="corner corner-tr"></div>
<div class="corner corner-bl"></div>
<div class="corner corner-br"></div>

<div class="hud">

  <!-- TOP BAR -->
  <div class="top-bar">
    <div class="logo">J.A.R.V.I.<span>S</span></div>
    <div class="top-info">
      <span>SYS <span class="val" id="clock">--:--:--</span></span>
      <span>STATUS <span class="val" id="top-status">ONLINE</span></span>
      <span>CORE <span class="val" style="color:var(--green)">ACTIVE</span></span>
    </div>
  </div>

  <!-- LEFT PANEL -->
  <div class="panel-left">

    <div class="widget">
      <div class="widget-title">// System Load</div>
      <div class="bar-row">
        <span class="bar-label">CPU</span>
        <div class="bar-track"><div class="bar-fill" id="cpu-bar" style="width:42%"></div></div>
        <span class="bar-val" id="cpu-val">42%</span>
      </div>
      <div class="bar-row">
        <span class="bar-label">RAM</span>
        <div class="bar-track"><div class="bar-fill" id="ram-bar" style="width:67%"></div></div>
        <span class="bar-val" id="ram-val">67%</span>
      </div>
      <div class="bar-row">
        <span class="bar-label">NET</span>
        <div class="bar-track"><div class="bar-fill" id="net-bar" style="width:30%;background:linear-gradient(to right,#004488,var(--blue))"></div></div>
        <span class="bar-val" id="net-val">30%</span>
      </div>
    </div>

    <div class="widget" style="flex:1;">
      <div class="widget-title">// Voice Commands</div>
      <div class="cmd-list">
        <div class="cmd-item"><span class="key">"Jarvis"</span> → Wake</div>
        <div class="cmd-item"><span class="key">👏👏</span> → Clap wake</div>
        <div class="cmd-item"><span class="key">"time/date"</span> → Info</div>
        <div class="cmd-item"><span class="key">"search X"</span> → Google</div>
        <div class="cmd-item"><span class="key">"youtube X"</span> → YT</div>
        <div class="cmd-item"><span class="key">"play chill"</span> → Spotify</div>
        <div class="cmd-item"><span class="key">"open desktop"</span> → Folder</div>
        <div class="cmd-item"><span class="key">"screenshot"</span> → Snap</div>
        <div class="cmd-item"><span class="key">"volume up/down"</span></div>
        <div class="cmd-item"><span class="key">"joke"</span> → Humor</div>
        <div class="cmd-item"><span class="key">"weather"</span> → Forecast</div>
        <div class="cmd-item"><span class="key">"goodbye"</span> → Shutdown</div>
      </div>
    </div>

  </div>

  <!-- CENTER -->
  <div class="center">

    <!-- Arc Reactor -->
    <div class="rings" id="rings">
      <div class="ring"></div>
      <div class="ring"></div>
      <div class="ring"></div>
      <div class="ring"></div>
      <div class="alert-ring" id="alert-ring"></div>
      <div class="core">
        <div class="core-glow"></div>
        <div class="core-ring"></div>
        <div class="core-inner" id="core-text">JARVIS</div>
      </div>
    </div>

    <!-- Wake source -->
    <div class="wake-badge" id="wake-badge">── VOICE ACTIVATED ──</div>

    <!-- Status -->
    <div class="status-wrap">
      <div class="status-label">// SYSTEM STATUS</div>
      <div class="status-text" id="status-text">STANDING BY</div>
    </div>

    <!-- Waveform -->
    <div class="waveform" id="waveform">
      <!-- bars injected by JS -->
    </div>

    <!-- Command / Response -->
    <div class="cmd-display">
      <div class="cmd-box" id="cmd-box">
        <span class="label">// YOU SAID</span>
        <span id="cmd-text">—</span>
      </div>
      <div class="cmd-box" id="res-box" style="border-color:rgba(0,255,136,0.2);color:var(--green);">
        <span class="label">// JARVIS RESPONSE</span>
        <span id="res-text">Awaiting input...</span>
      </div>
    </div>

  </div>

  <!-- RIGHT PANEL -->
  <div class="panel-right">

    <div class="widget">
      <div class="widget-title">// Network</div>
      <div style="font-size:0.65rem;line-height:2;opacity:0.8;">
        <div>UPLINK &nbsp;<span style="color:var(--green)">SECURE</span></div>
        <div>PING &nbsp;&nbsp;<span style="color:#fff" id="ping-val">—</span></div>
        <div>MODE &nbsp;&nbsp;<span style="color:var(--blue)">LOCAL</span></div>
      </div>
    </div>

    <div class="widget">
      <div class="widget-title">// Modules</div>
      <div style="font-size:0.63rem;line-height:2.2;">
        <div>🎤 SPEECH &nbsp;&nbsp;<span style="color:var(--green)">ON</span></div>
        <div>🔊 TTS &nbsp;&nbsp;&nbsp;&nbsp;<span style="color:var(--green)">ON</span></div>
        <div>👏 CLAP &nbsp;&nbsp;&nbsp;<span style="color:var(--green)">ON</span></div>
        <div><span class="spotify-icon"></span>SPOTIFY &nbsp;<span style="color:var(--green)">ON</span></div>
        <div>📁 FOLDERS &nbsp;<span style="color:var(--green)">ON</span></div>
        <div>🧠 AI BRAIN &nbsp;<span style="color:#666">PHASE 2</span></div>
      </div>
    </div>

    <div class="widget" style="flex:1;">
      <div class="widget-title">// Activity Log</div>
      <div id="log" style="font-size:0.6rem;line-height:1.9;opacity:0.7;overflow:hidden;max-height:200px;"></div>
    </div>

    <div class="widget">
      <div class="widget-title">// Spotify Quick Launch</div>
      <div style="display:flex;flex-direction:column;gap:5px;">
        <a href="https://open.spotify.com/playlist/37i9dQZF1DX4WYpdgoIcn6" target="_blank"
           style="font-size:0.62rem;color:var(--blue);text-decoration:none;padding:4px 6px;border:1px solid var(--border);display:block;transition:all 0.2s;"
           onmouseover="this.style.background='rgba(0,212,255,0.1)'" onmouseout="this.style.background=''">
          🎵 Chill playlist
        </a>
        <a href="https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M" target="_blank"
           style="font-size:0.62rem;color:var(--blue);text-decoration:none;padding:4px 6px;border:1px solid var(--border);display:block;transition:all 0.2s;"
           onmouseover="this.style.background='rgba(0,212,255,0.1)'" onmouseout="this.style.background=''">
          🎵 Focus playlist
        </a>
        <a href="https://open.spotify.com/playlist/37i9dQZF1DX76Wlfdnj7AP" target="_blank"
           style="font-size:0.62rem;color:var(--blue);text-decoration:none;padding:4px 6px;border:1px solid var(--border);display:block;transition:all 0.2s;"
           onmouseover="this.style.background='rgba(0,212,255,0.1)'" onmouseout="this.style.background=''">
          🎵 Workout playlist
        </a>
      </div>
    </div>

  </div>

  <!-- BOTTOM BAR -->
  <div class="bottom-bar">
    <span>J.A.R.V.I.S v2.0 — PERSONAL AI ASSISTANT</span>
    <span id="date-display">——</span>
    <span>STARK INDUSTRIES — ALL SYSTEMS NOMINAL</span>
  </div>

</div>

<script>
// ══════════════════════════════════════
// PARTICLE BACKGROUND
// ══════════════════════════════════════
const canvas = document.getElementById('bg');
const ctx    = canvas.getContext('2d');
canvas.width  = window.innerWidth;
canvas.height = window.innerHeight;

const particles = Array.from({length: 80}, () => ({
  x: Math.random() * canvas.width,
  y: Math.random() * canvas.height,
  r: Math.random() * 1.2 + 0.3,
  vx: (Math.random() - 0.5) * 0.3,
  vy: (Math.random() - 0.5) * 0.3,
  a: Math.random() * 0.5 + 0.1,
}));

function drawParticles() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  particles.forEach(p => {
    p.x += p.vx; p.y += p.vy;
    if (p.x < 0) p.x = canvas.width;
    if (p.x > canvas.width) p.x = 0;
    if (p.y < 0) p.y = canvas.height;
    if (p.y > canvas.height) p.y = 0;
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(0,180,220,${p.a})`;
    ctx.fill();
  });
  // Connection lines
  for (let i = 0; i < particles.length; i++) {
    for (let j = i+1; j < particles.length; j++) {
      const dx = particles[i].x - particles[j].x;
      const dy = particles[i].y - particles[j].y;
      const dist = Math.sqrt(dx*dx + dy*dy);
      if (dist < 100) {
        ctx.beginPath();
        ctx.moveTo(particles[i].x, particles[i].y);
        ctx.lineTo(particles[j].x, particles[j].y);
        ctx.strokeStyle = `rgba(0,180,220,${0.08 * (1 - dist/100)})`;
        ctx.lineWidth = 0.5;
        ctx.stroke();
      }
    }
  }
  requestAnimationFrame(drawParticles);
}
drawParticles();

// ══════════════════════════════════════
// WAVEFORM BARS
// ══════════════════════════════════════
const waveform = document.getElementById('waveform');
const BARS = 28;
for (let i = 0; i < BARS; i++) {
  const b = document.createElement('div');
  b.className = 'wave-bar';
  b.style.height = '4px';
  waveform.appendChild(b);
}

let waveActive = false;
function animateWave() {
  const bars = waveform.querySelectorAll('.wave-bar');
  bars.forEach((b, i) => {
    const h = waveActive
      ? (Math.sin(Date.now() / 120 + i * 0.5) * 0.5 + 0.5) * 34 + 4
      : 4;
    b.style.height = h + 'px';
  });
  requestAnimationFrame(animateWave);
}
animateWave();

// ══════════════════════════════════════
// CLOCK
// ══════════════════════════════════════
function updateClock() {
  const now = new Date();
  const t = now.toLocaleTimeString('en-US', {hour12:false});
  const d = now.toLocaleDateString('en-US', {weekday:'short', month:'short', day:'numeric', year:'numeric'});
  document.getElementById('clock').textContent = t;
  document.getElementById('date-display').textContent = d.toUpperCase();
}
setInterval(updateClock, 1000);
updateClock();

// ══════════════════════════════════════
// FAKE SYSTEM STATS ANIMATION
// ══════════════════════════════════════
function randomBetween(a, b) { return Math.floor(Math.random() * (b-a) + a); }

function updateStats() {
  const cpu = randomBetween(20, 80);
  const ram = randomBetween(40, 85);
  const net = randomBetween(10, 60);
  document.getElementById('cpu-bar').style.width = cpu + '%';
  document.getElementById('cpu-val').textContent  = cpu + '%';
  document.getElementById('ram-bar').style.width = ram + '%';
  document.getElementById('ram-val').textContent  = ram + '%';
  document.getElementById('net-bar').style.width = net + '%';
  document.getElementById('net-val').textContent  = net + '%';
  document.getElementById('ping-val').textContent = randomBetween(8,40) + 'ms';
}
setInterval(updateStats, 3000);

// ══════════════════════════════════════
// ACTIVITY LOG
// ══════════════════════════════════════
const logEl = document.getElementById('log');
function addLog(msg, color='var(--blue)') {
  const t = new Date().toLocaleTimeString('en-US',{hour12:false});
  const line = document.createElement('div');
  line.style.color = color;
  line.textContent = `[${t}] ${msg}`;
  logEl.insertBefore(line, logEl.firstChild);
  if (logEl.children.length > 12) logEl.removeChild(logEl.lastChild);
}
addLog('System boot complete', 'var(--green)');
addLog('Clap detection: active');
addLog('Wake word listener: active');
addLog('Spotify module: loaded', '#1db954');
addLog('Folder module: loaded');

// ══════════════════════════════════════
// STATE MACHINE — poll jarvis.py server
// ══════════════════════════════════════
const statusEl = document.getElementById('status-text');
const cmdEl    = document.getElementById('cmd-text');
const resEl    = document.getElementById('res-text');
const coreEl   = document.getElementById('core-text');
const alertEl  = document.getElementById('alert-ring');
const badgeEl  = document.getElementById('wake-badge');
const topEl    = document.getElementById('top-status');

let lastStatus = '';
let lastCmd    = '';
let lastRes    = '';

function applyState(state) {
  const { status, message, command, response, wake_source } = state;

  // Status text + class
  statusEl.className = 'status-text';
  if (status === 'idle') {
    statusEl.textContent = 'STANDING BY';
    coreEl.textContent   = 'JARVIS';
    waveActive = false;
    topEl.textContent = 'ONLINE';
    topEl.style.color = 'var(--blue)';
  } else if (status === 'active') {
    statusEl.textContent = 'ACTIVATED';
    statusEl.classList.add('active');
    coreEl.textContent   = 'AWAKE';
    waveActive = false;
    topEl.textContent = 'ACTIVE';
    topEl.style.color = 'var(--green)';
    // Flash ring
    alertEl.className = 'alert-ring ' + (wake_source === 'clap' ? 'active-flash' : 'active-flash');
    setTimeout(() => alertEl.className = 'alert-ring', 700);
    // Badge
    badgeEl.textContent = wake_source === 'clap' ? '── 👏 CLAP ACTIVATED ──' : '── 🎙️ VOICE ACTIVATED ──';
    badgeEl.classList.add('show');
    setTimeout(() => badgeEl.classList.remove('show'), 3000);
    addLog(`Activated via ${wake_source}`, 'var(--green)');
  } else if (status === 'listening') {
    statusEl.textContent = 'LISTENING...';
    statusEl.classList.add('listen');
    coreEl.textContent   = 'HEAR';
    waveActive = true;
    topEl.textContent = 'LISTENING';
    topEl.style.color = 'var(--gold)';
    alertEl.className = 'alert-ring listen-flash';
    setTimeout(() => alertEl.className = 'alert-ring', 700);
  } else if (status === 'thinking') {
    statusEl.textContent = 'PROCESSING...';
    statusEl.classList.add('think');
    coreEl.textContent   = 'THINK';
    waveActive = false;
    topEl.textContent = 'PROCESSING';
    topEl.style.color = '#ff9500';
  } else if (status === 'speaking') {
    statusEl.textContent = 'RESPONDING';
    statusEl.classList.add('speak');
    coreEl.textContent   = 'SPEAK';
    waveActive = true;
    topEl.textContent = 'SPEAKING';
    topEl.style.color = 'var(--blue)';
  }

  // Command update
  if (command && command !== lastCmd) {
    cmdEl.textContent = command;
    addLog(`CMD: ${command}`, 'var(--gold)');
    lastCmd = command;
  }

  // Response update
  if (response && response !== lastRes) {
    resEl.textContent = response;
    addLog(`RSP: ${response.slice(0,40)}...`, 'var(--green)');
    lastRes = response;
  }
}

// Poll the Python server every 400ms
async function pollServer() {
  try {
    const res  = await fetch('http://localhost:5050/state');
    const data = await res.json();
    applyState(data);
  } catch(e) {
    // jarvis.py not running — show demo mode
    if (lastStatus !== 'demo') {
      statusEl.textContent = 'DEMO MODE';
      resEl.textContent    = 'Run jarvis.py to connect live!';
      lastStatus = 'demo';
    }
  }
}

setInterval(pollServer, 400);
pollServer();
</script>
</body>
</html>
"""

def _hud_html():
    """Serve the cinematic HUD from jarvis_hud.html (next to this script) if it
    exists; otherwise fall back to the embedded HUD so the app always works."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis_hud.html")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return JARVIS_HUD_HTML

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
            self._send_json(get_live_stats())
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

# ══════════════════════════════════════════════
# 🔊  TEXT TO SPEECH
# ══════════════════════════════════════════════

import gc

# pyttsx3 has a well-known bug: a single engine speaks only ONCE, then every
# later runAndWait() goes silent. So we build a FRESH engine for each utterance
# (and release it) — this keeps every response audible, on any thread.
speak_lock = threading.Lock()

def _make_engine():
    eng = pyttsx3.init()
    eng.setProperty('rate', 170)
    eng.setProperty('volume', 1.0)
    for voice in eng.getProperty('voices'):
        if any(w in voice.name.lower() for w in ['david', 'mark', 'male', 'george']):
            eng.setProperty('voice', voice.id)
            break
    return eng

def speak(text):
    print(f"\n  🤖 JARVIS » {text}")
    set_ui("speaking", message=text, response=text)
    with speak_lock:
        try:
            eng = _make_engine()
            eng.say(text)
            eng.runAndWait()
            eng.stop()
            del eng
            gc.collect()   # release so the next speak() gets a fresh engine
        except Exception as e:
            print(f"  ⚠️  TTS error: {e}")
    set_ui("idle", message="Standing by...")

# ══════════════════════════════════════════════
# 🎤  LISTEN
# ══════════════════════════════════════════════

def listen(timeout=6, phrase_limit=8):
    """Capture one spoken phrase. Uses the shared mic engine if it's running
    (so we never open the microphone twice), otherwise falls back to a
    one-shot recognizer (used when testing without the engine)."""
    # Preferred path — reuse the single shared stream
    if ENGINE is not None:
        text = ENGINE.capture_phrase(start_timeout=timeout, max_seconds=phrase_limit)
        if text:
            print(f"  👤 You » {text}")
            set_ui("thinking", message="Processing...", command=text)
        return text or ""

    # Fallback path — no engine (e.g. typed-command session)
    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 300
    recognizer.dynamic_energy_threshold = True
    set_ui("listening", message="Listening...")
    try:
        with sr.Microphone() as source:
            print("\n  🎤 Listening...")
            recognizer.adjust_for_ambient_noise(source, duration=0.4)
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
            text = recognizer.recognize_google(audio).lower()
            print(f"  👤 You » {text}")
            set_ui("thinking", message="Processing...", command=text)
            return text
    except Exception:
        return ""

# ══════════════════════════════════════════════
# 📁  FOLDER OPENER
# ══════════════════════════════════════════════

def open_folder(path):
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception as e:
        print(f"  ⚠️  Folder error: {e}")
        return False

def handle_folder_command(command):
    for name, path in FOLDERS.items():
        if name in command:
            if os.path.exists(path):
                speak(f"Opening your {name} folder.")
                open_folder(path)
            else:
                speak(f"I couldn't find the {name} folder at {path}. Please update the path in the config.")
            return True

    # Custom path: "open folder C:/Users/..."
    if "open folder" in command or "open directory" in command:
        parts = command.replace("open folder", "").replace("open directory", "").strip()
        if parts:
            if os.path.exists(parts):
                speak(f"Opening {parts}.")
                open_folder(parts)
            else:
                speak(f"I couldn't find that folder path.")
        else:
            speak("Which folder would you like to open? Desktop, Downloads, Documents, Pictures, Music, or Videos?")
        return True

    return False

# ══════════════════════════════════════════════
# 🎵  SPOTIFY
# ══════════════════════════════════════════════

def handle_spotify_command(command):
    if not any(w in command for w in ["spotify", "music", "play", "song", "playlist"]):
        return False

    # Check for playlist keywords
    for mood, url in SPOTIFY_PLAYLISTS.items():
        if mood in command and mood != "default":
            speak(f"Opening {mood} playlist on Spotify.")
            webbrowser.open(url)
            return True

    # Generic play command
    if "open spotify" in command or "launch spotify" in command:
        speak("Opening Spotify.")
        webbrowser.open(SPOTIFY_PLAYLISTS["default"])
        return True

    # Search for song/artist
    search_terms = (command
        .replace("play", "").replace("spotify", "")
        .replace("music", "").replace("song", "")
        .replace("search for", "").strip())

    if search_terms:
        speak(f"Searching Spotify for {search_terms}.")
        webbrowser.open(f"https://open.spotify.com/search/{search_terms.replace(' ', '%20')}")
        return True

    # Fallback
    speak("Opening Spotify.")
    webbrowser.open(SPOTIFY_PLAYLISTS["default"])
    return True

# ══════════════════════════════════════════════
# 🧠  GEMINI AI BRAIN
# ══════════════════════════════════════════════

# Short conversation memory so Jarvis can follow up
chat_history = []        # list of {"role": "user"/"model", "text": ...}
MAX_HISTORY  = 8

SYSTEM_PROMPT = (
    f"You are JARVIS, a witty, concise personal AI assistant for {YOUR_NAME}. "
    "Answer in 1-3 short spoken sentences. No markdown, no bullet points, no emojis "
    "— your reply is read aloud by a text-to-speech voice. Be helpful and direct."
)

def gemini_ready():
    return bool(GEMINI_API_KEY)

def _gemini_can_call(model):
    """Real probe: does a tiny generateContent succeed (200) on this model?
    Catches free-tier 'limit: 0' models that exist but can't actually be used."""
    import requests
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={GEMINI_API_KEY}")
    try:
        r = requests.post(url, json={"contents": [{"parts": [{"text": "hi"}]}],
                                     "generationConfig": {"maxOutputTokens": 5}}, timeout=15)
        return r.status_code, r.text[:140]
    except Exception as e:
        return None, str(e)

def verify_gemini():
    """Pick a model the key can ACTUALLY call (not just one that exists)."""
    global GEMINI_MODEL
    if not gemini_ready():
        return False, "No Gemini API key set (.env GEMINI_API_KEY is empty)."
    try:
        import requests
    except ImportError:
        return False, "The 'requests' package is missing. Run: pip install requests"

    # Try the configured model first, then known free-tier-friendly fallbacks
    candidates = [GEMINI_MODEL, "gemini-2.5-flash", "gemini-2.5-flash-lite",
                  "gemini-flash-latest", "gemini-flash-lite-latest"]
    seen, last = [], ""
    for mdl in candidates:
        if mdl in seen:
            continue
        seen.append(mdl)
        code, body = _gemini_can_call(mdl)
        if code == 200:
            GEMINI_MODEL = mdl
            return True, f"Gemini online — using model '{GEMINI_MODEL}'."
        last = f"{mdl}: {code}"
        # 429 = quota/limit 0 on this model → just try the next one
    return False, (f"Key is valid but every model was blocked (last: {last}). "
                   "Your free-tier quota may be exhausted — try again later or check billing.")

def ask_gemini(prompt):
    """Send prompt (+ short history) to Gemini and return the spoken answer."""
    if not gemini_ready():
        return ("My AI brain is offline — I need a Gemini API key. "
                "Get one free at Google AI Studio and set it in the config.")
    try:
        import requests
    except ImportError:
        return "I need the requests package for my AI brain. Run pip install requests."

    # Build the contents array: system + recent history + new prompt
    contents = []
    for turn in chat_history[-MAX_HISTORY:]:
        contents.append({"role": turn["role"], "parts": [{"text": turn["text"]}]})
    contents.append({"role": "user", "parts": [{"text": prompt}]})

    body = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 256},
    }
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}")
    try:
        r = requests.post(url, json=body, timeout=20)
        if r.status_code != 200:
            return f"My AI brain returned an error, code {r.status_code}."
        data = r.json()
        answer = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        # Remember the exchange
        chat_history.append({"role": "user",  "text": prompt})
        chat_history.append({"role": "model", "text": answer})
        return answer
    except Exception as e:
        print(f"  ⚠️  Gemini error: {e}")
        return "Sorry, I couldn't reach my AI brain just now."

# ══════════════════════════════════════════════
# 🖥️  SYSTEM CONTROL  (Windows)
# ══════════════════════════════════════════════

# Pending shutdown/restart guard — must be confirmed before it fires
pending_power = {"action": None}

def launch_app(name):
    """Open an app by friendly name, falling back to launching the raw name."""
    name = name.strip().lower()
    target = APPS.get(name)
    try:
        if target is None:
            # Unknown app — try launching whatever they said via the shell
            target = name
        if target.endswith(":"):                 # URI like ms-settings:
            os.startfile(target)
        else:
            # 'start' resolves apps on PATH and registered App Paths
            subprocess.Popen(["cmd", "/c", "start", "", target], shell=False)
        return True
    except Exception as e:
        print(f"  ⚠️  App launch error: {e}")
        return False

def kill_processes(image_names):
    """taskkill one or more process images. Returns True if anything was killed."""
    killed = False
    for img in image_names:
        try:
            r = subprocess.run(["taskkill", "/f", "/im", img],
                               capture_output=True, text=True)
            # returncode 0 = killed; 128 = not running
            if r.returncode == 0:
                killed = True
        except Exception as e:
            print(f"  ⚠️  Close error for {img}: {e}")
    return killed

def close_active_browser_tab():
    """Close whatever browser tab is currently focused (Ctrl+W)."""
    try:
        import pyautogui
        pyautogui.hotkey("ctrl", "w")
        return True
    except Exception:
        return False

def handle_close_command(command):
    """Handle 'close X' / 'kill X'. Returns True if it handled the command.
    Must run BEFORE the youtube/google branches, or 'close youtube' re-opens it."""
    if "close" not in command and "kill" not in command:
        return False

    target = (command.replace("close", "").replace("kill", "")
                     .replace("the", "").replace("app", "").replace("window", "")
                     .replace("please", "").strip())

    # "close" / "close this" with no real target → close the focused window's tab
    if not target or target in ("this", "it", "that"):
        if close_active_browser_tab():
            speak("Closing the active tab.")
        else:
            speak("Install pyautogui so I can close tabs. Run pip install pyautogui.")
        return True

    # A website / browser tab (YouTube, Gmail, etc.) — close the focused tab.
    # ("browser" itself is a real process, handled below — exclude it here.)
    if any(w in target for w in WEB_TAB_WORDS) and "browser" not in target:
        if close_active_browser_tab():
            speak(f"Closing the {target} tab. Make sure the browser is in focus.")
        else:
            speak("Install pyautogui so I can close browser tabs. Run pip install pyautogui.")
        return True

    # A real app → taskkill its process.
    procs = CLOSE_PROCESSES.get(target)
    if procs is None:
        for name, imgs in CLOSE_PROCESSES.items():
            if name in target or target in name:
                procs = imgs
                break
    if procs is None:
        # Last resort — guess the image name from the first word.
        procs = [target.split()[0] + ".exe"]

    if kill_processes(procs):
        speak(f"Closed {target}.")
    else:
        speak(f"{target} doesn't seem to be running.")
    return True

def set_volume_percent(pct):
    """Set master volume 0-100 using pycaw if available."""
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        vol = cast(interface, POINTER(IAudioEndpointVolume))
        vol.SetMasterVolumeLevelScalar(max(0.0, min(1.0, pct / 100.0)), None)
        return True
    except Exception:
        return False

def set_brightness_percent(pct):
    try:
        import screen_brightness_control as sbc
        sbc.set_brightness(max(0, min(100, int(pct))))
        return True
    except Exception:
        return False

def battery_status():
    try:
        import psutil
        b = psutil.sensors_battery()
        if b is None:
            return "I couldn't read the battery — this might be a desktop."
        plugged = "charging" if b.power_plugged else "on battery"
        return f"Battery is at {int(b.percent)} percent, {plugged}."
    except ImportError:
        return "Install psutil for battery info. Run pip install psutil."
    except Exception:
        return "I couldn't read the battery status."

def gpu_status():
    """GPU load + memory. Tries GPUtil, then nvidia-smi (NVIDIA only)."""
    # 1) GPUtil — works for NVIDIA if installed
    try:
        import GPUtil
        gpus = GPUtil.getGPUs()
        if gpus:
            g = gpus[0]
            return (f"GPU {g.name} is at {int(g.load * 100)} percent load, "
                    f"using {int(g.memoryUsed)} of {int(g.memoryTotal)} megabytes of video memory, "
                    f"at {int(g.temperature)} degrees.")
    except Exception:
        pass
    # 2) nvidia-smi — present with any NVIDIA driver, no extra package
    try:
        out = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=8)
        if out.returncode == 0 and out.stdout.strip():
            load, used, total, temp = [x.strip() for x in out.stdout.strip().splitlines()[0].split(",")]
            return (f"GPU is at {load} percent load, using {used} of {total} "
                    f"megabytes of video memory, at {temp} degrees.")
    except Exception:
        pass
    return ("I couldn't read the GPU. For NVIDIA cards install GPUtil "
            "with pip install gputil, or make sure nvidia-smi is available.")

def system_stats_report(command):
    """Build a spoken report for whichever of CPU / memory / GPU was asked.
    If none is named specifically (e.g. 'system info'), report all of them."""
    try:
        import psutil
    except ImportError:
        return "Install psutil for system stats. Run pip install psutil."

    wants_cpu = any(w in command for w in ["cpu", "processor"])
    wants_mem = any(w in command for w in ["memory", "ram"])
    wants_gpu = any(w in command for w in ["gpu", "graphics", "video card"])
    # "system info", "how much is being used", etc. → everything
    if not (wants_cpu or wants_mem or wants_gpu):
        wants_cpu = wants_mem = wants_gpu = True

    parts = []
    if wants_cpu:
        parts.append(f"CPU is at {psutil.cpu_percent(interval=1)} percent")
    if wants_mem:
        m = psutil.virtual_memory()
        used_gb  = m.used  / (1024 ** 3)
        total_gb = m.total / (1024 ** 3)
        parts.append(f"memory is at {m.percent} percent, "
                     f"{used_gb:.1f} of {total_gb:.1f} gigabytes used")
    if wants_gpu:
        parts.append(gpu_status())

    return ". ".join(parts) + "."

# Live numeric stats for the HUD gauges (cached GPU so we don't spawn
# nvidia-smi on every poll).
_gpu_cache = {"t": 0.0, "data": {"gpu": None, "gpu_mem_used": None, "gpu_mem_total": None}}

def _gpu_numeric():
    now = time.time()
    if now - _gpu_cache["t"] < 3.0:
        return _gpu_cache["data"]
    data = {"gpu": None, "gpu_mem_used": None, "gpu_mem_total": None}
    try:
        import GPUtil
        gpus = GPUtil.getGPUs()
        if gpus:
            g = gpus[0]
            data = {"gpu": round(g.load * 100), "gpu_mem_used": round(g.memoryUsed),
                    "gpu_mem_total": round(g.memoryTotal)}
    except Exception:
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=6)
            if out.returncode == 0 and out.stdout.strip():
                load, used, total = [x.strip() for x in out.stdout.strip().splitlines()[0].split(",")]
                data = {"gpu": int(load), "gpu_mem_used": int(used), "gpu_mem_total": int(total)}
        except Exception:
            pass
    _gpu_cache["t"], _gpu_cache["data"] = now, data
    return data

def get_live_stats():
    """Real CPU / RAM / GPU / battery numbers for the HUD gauges."""
    stats = {"cpu": None, "ram": None, "ram_used": None, "ram_total": None,
             "battery": None, "gpu": None, "gpu_mem_used": None, "gpu_mem_total": None}
    try:
        import psutil
        stats["cpu"] = psutil.cpu_percent(interval=None)   # non-blocking
        m = psutil.virtual_memory()
        stats["ram"]       = m.percent
        stats["ram_used"]  = round(m.used  / (1024 ** 3), 1)
        stats["ram_total"] = round(m.total / (1024 ** 3), 1)
        b = psutil.sensors_battery()
        if b is not None:
            stats["battery"] = int(b.percent)
    except Exception:
        pass
    stats.update(_gpu_numeric())
    return stats

def handle_system_command(command):
    """Returns True if it handled a system/app command."""
    global pending_power

    # ── confirm / cancel a pending power action ──
    if pending_power["action"]:
        if any(w in command for w in ["yes", "confirm", "do it", "go ahead", "sure"]):
            act = pending_power["action"]
            pending_power = {"action": None}
            if act == "shutdown":
                speak("Confirmed. Shutting down in 15 seconds. Say cancel shutdown to stop.")
                subprocess.Popen(["shutdown", "/s", "/t", "15"])
            elif act == "restart":
                speak("Confirmed. Restarting in 15 seconds. Say cancel shutdown to stop.")
                subprocess.Popen(["shutdown", "/r", "/t", "15"])
            return True
        if any(w in command for w in ["no", "cancel", "stop", "don't", "abort"]):
            pending_power = {"action": None}
            speak("Cancelled. Staying on.")
            return True

    # ── cancel an already-scheduled shutdown ──
    if any(w in command for w in ["cancel shutdown", "abort shutdown", "stop shutdown"]):
        try:
            subprocess.Popen(["shutdown", "/a"])
            speak("Shutdown cancelled.")
        except Exception:
            speak("There was no shutdown to cancel.")
        return True

    # ── shutdown / restart (require confirmation) ──
    if any(w in command for w in ["shut down", "shutdown", "turn off computer", "turn off the computer"]):
        pending_power = {"action": "shutdown"}
        speak("Are you sure you want to shut down? Say yes to confirm or no to cancel.")
        return True
    if any(w in command for w in ["restart", "reboot"]):
        pending_power = {"action": "restart"}
        speak("Are you sure you want to restart? Say yes to confirm or no to cancel.")
        return True

    # ── lock / sleep ──
    if "lock" in command and ("pc" in command or "computer" in command or "screen" in command):
        speak("Locking your PC.")
        try: ctypes.windll.user32.LockWorkStation()
        except Exception: pass
        return True
    if any(w in command for w in ["sleep", "go to sleep", "suspend"]) and "computer" in command or "put the pc to sleep" in command:
        speak("Putting the computer to sleep.")
        try: subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
        except Exception: pass
        return True

    # ── battery ──
    if "battery" in command:
        speak(battery_status())
        return True

    # ── brightness ──
    if "brightness" in command:
        import re
        m = re.search(r"(\d{1,3})", command)
        if m:
            pct = int(m.group(1))
            speak(f"Setting brightness to {pct} percent." if set_brightness_percent(pct)
                  else "Install screen-brightness-control for brightness. Run pip install screen-brightness-control.")
        elif any(w in command for w in ["up", "increase", "brighter", "max"]):
            speak("Brightness to max." if set_brightness_percent(100) else "I can't control brightness on this display.")
        elif any(w in command for w in ["down", "decrease", "dim", "lower"]):
            speak("Dimming the screen." if set_brightness_percent(30) else "I can't control brightness on this display.")
        else:
            speak("Tell me a brightness level, like set brightness to 50.")
        return True

    # ── set volume to a number ──
    if "volume" in command:
        import re
        m = re.search(r"(\d{1,3})", command)
        if m:
            pct = int(m.group(1))
            if set_volume_percent(pct):
                speak(f"Volume set to {pct} percent.")
            else:
                speak("For exact volume levels install pycaw. Run pip install pycaw.")
            return True
        # else fall through to the up/down/mute handlers in handle_command

    # ── open an app ──
    if command.startswith("open ") or command.startswith("launch ") or command.startswith("start "):
        app = (command.replace("open", "", 1).replace("launch", "", 1)
                      .replace("start", "", 1).replace("the app", "").replace("app", "").strip())
        # Don't hijack folder/browser/spotify/web words handled elsewhere.
        # Returning False lets the YouTube/Google web branches in handle_command run.
        web_words = ("youtube", "google", "browser", "chrome browser")
        if app and app not in FOLDERS and not any(w in app for w in web_words):
            if launch_app(app):
                speak(f"Opening {app}.")
            else:
                speak(f"I couldn't open {app}.")
            return True

    return False

# ══════════════════════════════════════════════
# 💬  COMMAND HANDLER
# ══════════════════════════════════════════════

jokes = [
    "Why don't scientists trust atoms? Because they make up everything!",
    "Why do programmers prefer dark mode? Because light attracts bugs!",
    "How many programmers does it take to change a light bulb? None. That's a hardware problem.",
    "I told my computer I needed a break. Now it won't stop sending me Kit-Kat ads.",
]

def handle_command(command):
    if not command:
        speak("I didn't catch that. Call me again.")
        return

    # ── Close / kill an app or tab ── (MUST be first so "close youtube"
    #    can't fall through to the "youtube" branch and re-open it)
    if handle_close_command(command):
        return

    # ── Spotify / Music ──
    if handle_spotify_command(command):
        return

    # ── Folders ──
    if handle_folder_command(command):
        return

    # ── System control / app launch ──
    if handle_system_command(command):
        return

    # ── Greetings ──
    if any(w in command for w in ["hello", "hi ", "hey", "what's up"]):
        speak(random.choice([
            f"Hello {YOUR_NAME}! All systems go. How can I help?",
            f"Hey {YOUR_NAME}! Ready and waiting.",
            f"Good to see you, {YOUR_NAME}. What do you need?",
        ]))

    # ── Time ──
    elif any(w in command for w in ["time", "clock"]):
        now = datetime.datetime.now().strftime("%I:%M %p")
        speak(f"It's {now}, {YOUR_NAME}.")

    # ── Date ──
    elif any(w in command for w in ["date", "today", "day is it"]):
        today = datetime.datetime.now().strftime("%A, %B %d, %Y")
        speak(f"Today is {today}.")

    # ── Browser ──
    elif any(w in command for w in ["open browser", "open chrome", "launch browser"]):
        speak("Opening browser.")
        webbrowser.open("https://www.google.com")

    # ── Google Search ──
    elif "search" in command or "google" in command:
        query = (command.replace("search for","").replace("search","")
                        .replace("google","").strip())
        if not query:
            speak("What should I search for?")
            query = listen(timeout=5)
        if query:
            speak(f"Searching for {query}.")
            webbrowser.open(f"https://www.google.com/search?q={query.replace(' ','+')}")

    # ── YouTube ──
    elif "youtube" in command:
        query = (command.replace("youtube","").replace("play","")
                        .replace("search","").replace("open","")
                        .replace("launch","").replace("start","").strip())
        if query:
            speak(f"Opening YouTube for {query}.")
            webbrowser.open(f"https://www.youtube.com/results?search_query={query.replace(' ','+')}")
        else:
            speak("Opening YouTube.")
            webbrowser.open("https://www.youtube.com")

    # ── Notepad ──
    elif any(w in command for w in ["notepad", "text editor", "open notes"]):
        speak("Opening Notepad.")
        if sys.platform == "win32":   subprocess.Popen(["notepad.exe"])
        elif sys.platform == "darwin": subprocess.Popen(["open", "-a", "TextEdit"])
        else:                          subprocess.Popen(["gedit"])

    # ── Calculator ──
    elif any(w in command for w in ["calculator", "calc"]):
        speak("Opening Calculator.")
        if sys.platform == "win32":   subprocess.Popen(["calc.exe"])
        elif sys.platform == "darwin": subprocess.Popen(["open", "-a", "Calculator"])
        else:                          subprocess.Popen(["gnome-calculator"])

    # ── Screenshot ──
    elif any(w in command for w in ["screenshot", "screen capture"]):
        try:
            import pyautogui
            fname = f"screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            path  = os.path.join(os.path.expanduser("~"), "Desktop", fname)
            pyautogui.screenshot(path)
            speak(f"Screenshot saved to Desktop as {fname}.")
        except ImportError:
            speak("Install pyautogui first. Run: pip install pyautogui")

    # ── Volume ──
    elif any(w in command for w in ["volume up", "louder"]):
        speak("Turning it up.")
        try:
            import pyautogui
            for _ in range(5): pyautogui.press('volumeup')
        except: speak("Install pyautogui for volume control.")

    elif any(w in command for w in ["volume down", "quieter", "lower volume"]):
        speak("Turning it down.")
        try:
            import pyautogui
            for _ in range(5): pyautogui.press('volumedown')
        except: speak("Install pyautogui for volume control.")

    elif any(w in command for w in ["mute", "silence"]):
        speak("Muting.")
        try:
            import pyautogui
            pyautogui.press('volumemute')
        except: pass

    # ── Joke ──
    elif any(w in command for w in ["joke", "funny", "make me laugh"]):
        speak(random.choice(jokes))

    # ── Weather ──
    elif any(w in command for w in ["weather", "temperature", "forecast"]):
        speak(f"Opening weather for {YOUR_CITY}.")
        webbrowser.open(f"https://www.google.com/search?q=weather+{YOUR_CITY.replace(' ','+')}")

    # ── System Info (CPU / memory / GPU) ──
    elif any(w in command for w in ["cpu", "processor", "ram", "memory",
                                     "gpu", "graphics", "video card", "system info"]):
        speak(system_stats_report(command))

    # ── IP ──
    elif "ip" in command:
        import socket
        try:
            ip = socket.gethostbyname(socket.gethostname())
            speak(f"Your local IP is {ip}.")
        except: speak("Couldn't get your IP.")

    # ── Who are you ──
    elif any(w in command for w in ["who are you", "what are you", "introduce"]):
        speak(f"I am Jarvis — Just A Rather Very Intelligent System. Personal AI assistant for {YOUR_NAME}.")

    # ── Shutdown Jarvis ──
    elif any(w in command for w in ["goodbye", "bye", "exit", "quit", "shutdown jarvis"]):
        speak(f"Goodbye {YOUR_NAME}. Jarvis signing off.")
        set_ui("idle", message="Offline.")
        os._exit(0)

    # ── Anything else → ask the Gemini AI brain ──
    else:
        set_ui("thinking", message="Thinking...", command=command)
        answer = ask_gemini(command)
        speak(answer)

# ══════════════════════════════════════════════
# 🎧  UNIFIED AUDIO ENGINE  (one mic stream = no conflict)
# ══════════════════════════════════════════════
#
#   ONE microphone stream does BOTH jobs:
#     • Clap detection  (double-clap = wake)
#     • Wake word        ("jarvis", "hey jarvis", ...)
#   The old version opened the mic twice (clap thread + wake thread),
#   which fights for the device on Windows. This fixes that.

WAKE_PHRASES = ["jarvis", "hey jarvis", "ok jarvis", "okay jarvis",
                "yo jarvis", "hi jarvis", "jarvis wake up", "jervis", "service"]

ENGINE = None          # set in boot — the single shared mic owner

def _rms(data):
    return float(np.abs(np.frombuffer(data, dtype=np.int16)).mean())

class AudioEngine:
    def __init__(self):
        self.pa = pyaudio.PyAudio()
        # Windows often has NO "default" recording device set (esp. when the mic
        # is a Bluetooth earbud that isn't marked default). Opening the default
        # then fails with -9996/-9999. So we probe every input-capable device,
        # actually read a chunk from each, and keep the first that works.
        self.stream = self._open_working_input()
        self.ambient    = 80.0
        self.speech_thr = SPEECH_THRESHOLD
        self.clap_thr   = CLAP_THRESHOLD
        self.busy       = False           # True while handling a command
        self.clap_times = []
        self.last_edge  = 0.0
        self.prev_loud  = False
        # chunks of silence that mark the end of a phrase (~0.7s)
        self.silence_chunks = max(6, int(0.7 * SAMPLE_RATE / CHUNK))
        self.start_chunks   = max(1, int(SAMPLE_RATE / CHUNK))   # ~1s to start

    # ── find & open a microphone that ACTUALLY works ──
    def _try_open(self, index, rate):
        s = self.pa.open(format=pyaudio.paInt16, channels=1, rate=rate,
                         input=True, input_device_index=index,
                         frames_per_buffer=CHUNK)
        s.read(CHUNK, exception_on_overflow=False)   # prove it really reads
        return s

    def _open_working_input(self):
        global SAMPLE_RATE
        # 1) the Windows default, if one is set (fast path)
        order = []
        try:
            order.append(self.pa.get_default_input_device_info()["index"])
        except Exception:
            pass
        # 2) then every other input-capable device, any host API
        for i in range(self.pa.get_device_count()):
            try:
                if self.pa.get_device_info_by_index(i)["maxInputChannels"] > 0 \
                        and i not in order:
                    order.append(i)
            except Exception:
                pass

        for idx in order:
            try:
                info = self.pa.get_device_info_by_index(idx)
            except Exception:
                continue
            name = str(info.get("name", "?"))[:40]
            # Prefer our working rate; fall back to the device's native rate.
            for rate in (SAMPLE_RATE, int(info.get("defaultSampleRate", SAMPLE_RATE))):
                try:
                    stream = self._try_open(idx, rate)
                    if rate != SAMPLE_RATE:
                        SAMPLE_RATE = rate          # keep VAD/recognition in sync
                    self.dev_index, self.dev_name, self.dev_rate = idx, name, rate
                    print(f"  🎤  Using mic: [{idx}] {name}  @ {rate} Hz")
                    return stream
                except Exception:
                    continue

        # Nothing opened — give the user something they can ACT on.
        ins = []
        for i in range(self.pa.get_device_count()):
            try:
                d = self.pa.get_device_info_by_index(i)
                if d["maxInputChannels"] > 0:
                    ins.append(f"[{i}] {str(d.get('name','?'))[:38]}")
            except Exception:
                pass
        listing = "\n        ".join(ins) if ins else "(none detected)"
        raise RuntimeError(
            "no microphone Windows will let me open.\n"
            "      Fix: connect your earbuds/headset and pick HANDS-FREE (not\n"
            "      Stereo) mode — Stereo mode has NO mic. Then set it as the\n"
            "      DEFAULT recording device in Windows Sound settings.\n"
            f"      Input devices Windows currently lists:\n        {listing}"
        )

    # ── read one frame → (raw, average level, PEAK level) ──
    #    A clap is a ~5ms impulse; averaged over a 64ms chunk it shrinks toward
    #    the speech threshold. The PEAK preserves the impulse, so we use the
    #    average for speech VAD and the peak for clap detection.
    def _read(self):
        data = self.stream.read(CHUNK, exception_on_overflow=False)
        arr  = np.abs(np.frombuffer(data, dtype=np.int16))
        return data, float(arr.mean()), float(arr.max())

    # ── auto-tune thresholds from the room's noise floor ──
    def calibrate(self):
        print("  🎤  Calibrating mic to your room (stay quiet ~1.5s)...")
        vols, peaks = [], []
        try:
            for _ in range(int(1.5 * SAMPLE_RATE / CHUNK)):
                _, v, p = self._read()
                vols.append(v)
                peaks.append(p)
        except Exception as e:
            print(f"  ⚠️  Calibration read failed: {e}")
        peak_floor = max(peaks) if peaks else 0
        if vols:
            self.ambient    = max(40.0, float(np.median(vols)))
            self.speech_thr = max(300.0, self.ambient * 2.4)
            # Clap = peak impulse. Sit well above the loudest quiet-room peak,
            # but no lower than 8000 (claps peak ~20000–32000, speech ~5000–15000).
            self.clap_thr   = max(8000.0, peak_floor * 1.8)
        if self.ambient < 45:
            print("  ⚠️  Mic seems SILENT — check it's plugged in & not muted in Windows sound settings!")
        print(f"  ✅  Ambient≈{int(self.ambient)} | speak>{int(self.speech_thr)} | "
              f"clap-peak>{int(self.clap_thr)} | room-peak={int(peak_floor)}")
        print("      👏 Tip: clap twice now — watch the 'transient peak' numbers below to tune.")

    # ── double-clap detector (rising-edge transients) ──
    def _is_double_clap(self, level):
        now  = time.time()
        loud = level > self.clap_thr
        edge = loud and not self.prev_loud
        self.prev_loud = loud
        if edge and (now - self.last_edge) > 0.12:
            self.last_edge  = now
            self.clap_times = [t for t in self.clap_times if now - t < DOUBLE_CLAP_WINDOW]
            self.clap_times.append(now)
            if len(self.clap_times) >= 2:
                gap = self.clap_times[-1] - self.clap_times[-2]
                if CLAP_COOLDOWN < gap < DOUBLE_CLAP_WINDOW:
                    self.clap_times.clear()
                    return True
        return False

    # ── record one spoken phrase via voice-activity detection, return text ──
    def capture_phrase(self, start_timeout=6, max_seconds=8):
        set_ui("listening", message="Listening...")
        frames, started, silent, waited = [], False, 0, 0
        start_limit = int(start_timeout * SAMPLE_RATE / CHUNK)
        max_chunks  = int(max_seconds  * SAMPLE_RATE / CHUNK)
        while True:
            try:
                data, vol, _ = self._read()
            except Exception:
                return None
            if not started:
                waited += 1
                if vol > self.speech_thr:
                    started, silent = True, 0
                    frames.append(data)
                elif waited > start_limit:
                    return None                       # nothing said
            else:
                frames.append(data)
                if vol < self.speech_thr:
                    silent += 1
                    if silent >= self.silence_chunks:
                        break
                else:
                    silent = 0
                if len(frames) > max_chunks:
                    break
        audio = sr.AudioData(b"".join(frames), SAMPLE_RATE, 2)
        try:
            return sr.Recognizer().recognize_google(audio).lower()
        except sr.UnknownValueError:
            return None
        except sr.RequestError as e:
            print(f"  ⚠️  Speech API error (internet?): {e}")
            return None
        except Exception:
            return None

    def _flush(self, n=8):
        for _ in range(n):
            try: self.stream.read(CHUNK, exception_on_overflow=False)
            except Exception: break

    # ── wake → greet → take command ──
    def activate(self, source="voice"):
        self.busy = True
        try:
            print(f"\n  🟢  JARVIS ACTIVATED  [{source.upper()}]")
            set_ui("active", message="ACTIVATED", wake_source=source)
            time.sleep(0.2)
            speak(random.choice([
                f"Yes {YOUR_NAME}? I'm listening.",
                f"At your service, {YOUR_NAME}.",
                "Jarvis here. Go ahead.",
                "Online. What do you need?",
            ]))
            self._flush()                              # ignore the echo of my own voice
            command = self.capture_phrase(start_timeout=6, max_seconds=9)
            if command:
                print(f"  👤 You » {command}")
                set_ui("thinking", message="Processing...", command=command)
                handle_command(command)
            else:
                speak("I didn't catch that. Call me again when you're ready.")
        except Exception as e:
            print(f"  ⚠️  Activation error: {e}")
        finally:
            set_ui("idle", message="Standing by...")
            self._flush()
            self.busy = False

    # ── run a command directly, no wake/greeting (wake-word-free mode) ──
    def _run_command(self, text):
        self.busy = True
        try:
            print(f"\n  ⚡  Direct command » {text}")
            set_ui("thinking", message="Processing...", command=text)
            handle_command(text)
        except Exception as e:
            print(f"  ⚠️  Command error: {e}")
        finally:
            set_ui("idle", message="Standing by...")
            self._flush()                              # drop the echo of my reply
            self.busy = False

    # ── main loop: clap + wake word on the SAME stream ──
    def run(self):
        if ALWAYS_LISTEN:
            print("  🎙️   WAKE-WORD-FREE mode — just say your command, e.g. 'open youtube'.")
            print("       (Saying 'Jarvis' or double-clapping still works too.)")
        else:
            print(f"  🎙️   Listening for claps 👏👏 and wake words {WAKE_PHRASES[:4]}...")
        print("  ⌨️   Or press ENTER in this window to type a command (works without a mic).\n")
        frames, recording, silent = [], False, 0
        max_phrase = int(5 * SAMPLE_RATE / CHUNK)
        while True:
            try:
                if self.busy:
                    time.sleep(0.05)
                    continue
                data, vol, peak = self._read()

                # Live feedback: show any loud impulse so you can tune the
                # clap threshold from real numbers (clap and read the value).
                if peak > self.clap_thr * 0.45:
                    print(f"  🔊 transient peak={int(peak)}  (clap needs >{int(self.clap_thr)})")

                # 1) double clap?  (uses PEAK, not the diluted average)
                if self._is_double_clap(peak):
                    print("\n  👏👏  Double clap detected!")
                    frames, recording, silent = [], False, 0
                    self.activate("clap")
                    continue

                # 2) wake word via VAD-captured phrase
                if vol > self.speech_thr:
                    recording = True
                    frames.append(data)
                    silent = 0
                elif recording:
                    frames.append(data)
                    silent += 1
                    if silent >= self.silence_chunks or len(frames) > max_phrase:
                        audio = sr.AudioData(b"".join(frames), SAMPLE_RATE, 2)
                        frames, recording, silent = [], False, 0
                        try:
                            text = sr.Recognizer().recognize_google(audio).lower()
                            print(f"  heard: [{text}]")

                            # A) wake word present → strip it. If a command follows
                            #    ("jarvis open youtube"), run it; else greet & listen.
                            if any(p in text for p in WAKE_PHRASES):
                                cmd = text
                                for p in WAKE_PHRASES:
                                    cmd = cmd.replace(p, "")
                                cmd = cmd.strip(" ,.")
                                if cmd:
                                    print("  🟡  Wake word + command!")
                                    self._run_command(cmd)
                                else:
                                    print("  🟡  Wake word matched!")
                                    self.activate("voice")

                            # B) wake-word-free → just run the command directly
                            elif ALWAYS_LISTEN:
                                if (not REQUIRE_TRIGGER) or has_command_trigger(text):
                                    self._run_command(text)
                                else:
                                    print("  ·  (ignored — no command word)")
                        except (sr.UnknownValueError, sr.RequestError):
                            pass
                        except Exception:
                            pass
            except Exception as e:
                print(f"  ⚠️  Audio loop error: {e}")
                time.sleep(0.3)

# ── console fallback: type commands even if the mic misbehaves ──
def console_loop():
    while True:
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            return
        text = line.strip().lower()

        # No mic available → typed commands are the ONLY way in. Handle directly.
        if ENGINE is None:
            if not text:
                print("  ⌨️  No microphone — type a command, e.g. 'what time is it'.")
                continue
            print(f"  ⌨️  You typed » {text}")
            set_ui("thinking", message="Processing...", command=text)
            handle_command(text)
            set_ui("idle", message="Standing by...")
            continue

        if not text:
            # plain ENTER → trigger a voice activation
            ENGINE.activate("manual")
            continue
        # typed command → handle directly (no mic needed); pause the mic loop
        ENGINE.busy = True
        try:
            print(f"  ⌨️  You typed » {text}")
            set_ui("thinking", message="Processing...", command=text)
            handle_command(text)
        finally:
            set_ui("idle", message="Standing by...")
            ENGINE.busy = False

# ══════════════════════════════════════════════
# 🚀  BOOT
# ══════════════════════════════════════════════

if __name__ == "__main__":
    print("""
  ╔══════════════════════════════════════════════╗
  ║    J . A . R . V . I . S                     ║
  ║    Just A Rather Very Intelligent System     ║
  ╠══════════════════════════════════════════════╣
  ║  🗣️   Just speak     →  Runs the command      ║
  ║       (no "Jarvis" needed — wake-word-free)   ║
  ║  👏  Double clap    →  Wake Jarvis           ║
  ║  ⌨️   Press ENTER    →  Type a command        ║
  ║  🧠  Gemini AI brain + system control         ║
  ║  🌐  HUD launching automatically...          ║
  ╚══════════════════════════════════════════════╝
    """)

    # Start UI bridge server
    ui_thread = threading.Thread(target=start_ui_server, daemon=True)
    ui_thread.start()
    print("  🌐  UI server running on http://localhost:5050")

    def launch_hud():
        time.sleep(1.2)
        print("  🖥️   Launching HUD at http://localhost:5050")
        webbrowser.open("http://localhost:5050")
    threading.Thread(target=launch_hud, daemon=True).start()

    # Check the Gemini AI brain
    ok, msg = verify_gemini()
    print(f"  🧠  {msg}")

    # Build the single shared mic engine + calibrate to the room
    try:
        ENGINE = AudioEngine()
        ENGINE.calibrate()
    except Exception as e:
        print(f"  ⚠️  Could not open microphone: {e}")
        print("      You can still TYPE commands — press ENTER in this window.")
        ENGINE = None

    speak(f"Jarvis online. Good to see you, {YOUR_NAME}. All systems operational.")

    # Console typing always works
    threading.Thread(target=console_loop, daemon=True).start()

    # Run the mic engine (or idle if no mic)
    if ENGINE is not None:
        ENGINE.run()
    else:
        while True:
            time.sleep(1)