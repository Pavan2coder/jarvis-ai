"""
Dynamic Island — an always-on-top pill at the top-center of the screen.

Collapsed: clock / now-playing (Spotify) / timer / live Jarvis status.
Hover to expand: Media controls, Timer, Quick Launch. Pin keeps it open.

Spawned by backend/main.py on boot (set JARVIS_NO_ISLAND=1 to disable).
Standalone:  .venv\\Scripts\\python.exe -m ui.dynamic_island
Self-check:  .venv\\Scripts\\python.exe -m ui.dynamic_island --selftest
"""
import ctypes
import json
import math
import os
import sys
import threading
import time
import urllib.request
import winsound
import tkinter as tk
from tkinter import font as tkfont, simpledialog

import psutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

STATE_URL = "http://localhost:5050/state"
APPS_FILE = os.path.join(ROOT, "backend", "config", "island_apps.json")
DEFAULT_APPS = ["spotify", "explorer", "chrome"]

KEY = "#010203"  # transparent (and click-through) colour key
BG, FG, DIM, GREEN, HILITE = "#000000", "#ffffff", "#8a8f98", "#22c55e", "#262a33"
STATUS_COLOR = {"listening": "#38bdf8", "active": "#38bdf8", "thinking": "#f59e0b", "speaking": GREEN}
APP_COLORS = ["#1db954", "#0ea5e9", "#f97316", "#a855f7", "#ef4444", "#14b8a6", "#eab308"]

WIN_W, WIN_H = 600, 190          # logical px; real window is scaled by DPI
EXP_W, EXP_H, COL_H = 560, 170, 38
HOVER_OPEN, HOVER_CLOSE = 0.3, 0.6  # seconds

# Segoe Fluent / MDL2 glyphs
G_MUSIC, G_TIMER, G_APPS = "", "", ""
G_PLAY, G_PAUSE, G_PREV, G_NEXT = "", "", "", ""
G_PIN, G_UNPIN, G_ADD, G_BOLT, G_CLOCK, G_RESET = "", "", "", "", "", ""

VK_NEXT, VK_PREV, VK_PLAY = 0xB0, 0xB1, 0xB3


# ── helpers ────────────────────────────────────────────────────────────────
def parse_spotify_title(title):
    """Spotify's window title is 'Artist - Song' while playing, 'Spotify ...' when paused."""
    if " - " not in title or title.startswith("Spotify"):
        return None
    artist, song = title.split(" - ", 1)
    return song.strip(), artist.strip()


def spotify_now_playing():
    """Returns ((song, artist) | None, spotify_running)."""
    pids = {p.pid for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() == "spotify.exe"}
    if not pids:
        return None, False
    user32, titles = ctypes.windll.user32, []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _):
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        n = user32.GetWindowTextLengthW(hwnd)
        if pid.value in pids and n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            titles.append(buf.value)
        return True

    user32.EnumWindows(cb, 0)
    return next((s for s in map(parse_spotify_title, titles) if s), None), True


def media_key(vk):
    u = ctypes.windll.user32
    u.keybd_event(vk, 0, 1, 0)      # KEYEVENTF_EXTENDEDKEY
    u.keybd_event(vk, 0, 3, 0)      # ... | KEYEVENTF_KEYUP


def fmt_secs(s):
    s = max(0, int(math.ceil(s)))
    h, m, sec = s // 3600, s // 60 % 60, s % 60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def round_rect(c, x0, y0, x1, y1, r, **kw):
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
           x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return c.create_polygon(pts, smooth=True, **kw)


def load_apps():
    try:
        with open(APPS_FILE, encoding="utf-8") as f:
            return list(json.load(f))
    except Exception:
        return list(DEFAULT_APPS)


def save_apps(apps):
    with open(APPS_FILE, "w", encoding="utf-8") as f:
        json.dump(apps, f, indent=2)


# ── island ─────────────────────────────────────────────────────────────────
class Island:
    def __init__(self, parent_pid=None):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        self.parent_pid = parent_pid
        self.root = r = tk.Tk()
        self.S = r.winfo_fpixels("1i") / 96.0
        r.overrideredirect(True)
        r.attributes("-topmost", True)
        r.attributes("-transparentcolor", KEY)
        r.configure(bg=KEY)
        sw = r.winfo_screenwidth()
        r.geometry(f"{int(WIN_W * self.S)}x{int(WIN_H * self.S)}+{int((sw - WIN_W * self.S) / 2)}+0")
        self.c = tk.Canvas(r, bg=KEY, highlightthickness=0)
        self.c.pack(fill="both", expand=True)
        self.c.bind("<Button-1>", lambda e: self.click(e, 0))
        self.c.bind("<Button-3>", lambda e: self.click(e, 1))

        fams = set(tkfont.families())
        icon = next((f for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if f in fams), "Segoe UI Symbol")
        self.f_text = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        self.f_small = tkfont.Font(family="Segoe UI", size=9)
        self.f_title = tkfont.Font(family="Segoe UI", size=12, weight="bold")
        self.f_big = tkfont.Font(family="Segoe UI", size=30, weight="bold")
        self.f_icon = tkfont.Font(family=icon, size=12)
        self.f_icon_s = tkfont.Font(family=icon, size=10)

        # live data (written by poll thread)
        self.jarvis, self.song, self.last_song, self.spotify_running = {}, None, None, False
        self.plugged, self.battery = False, None
        # ui state
        self.w, self.h = 240.0, float(COL_H)
        self.expanded = self.pinned = self.dialog = False
        self.tab, self.hits, self.pill = "media", [], (0, 0, 0, 0)
        self.hover_since, self.last_inside = None, 0.0
        # timer
        self.t_left, self.t_end, self.done_until = 0.0, None, 0.0
        self.apps = load_apps()
        self.next_parent_check = 0.0

        threading.Thread(target=self.poll, daemon=True).start()
        self.tick()

    # background data
    def poll(self):
        n = 0
        while True:
            try:
                with urllib.request.urlopen(STATE_URL, timeout=1) as resp:
                    self.jarvis = json.load(resp)
            except Exception:
                self.jarvis = {"status": "offline"}
            if n % 4 == 0:
                try:
                    self.song, self.spotify_running = spotify_now_playing()
                    if self.song:
                        self.last_song = self.song
                except Exception:
                    self.song = None
            if n % 20 == 0:
                b = psutil.sensors_battery()
                self.plugged, self.battery = (b.power_plugged, round(b.percent)) if b else (True, None)
            n += 1
            time.sleep(0.5)

    # timer
    def remaining(self, now):
        return max(0.0, self.t_end - now) if self.t_end else self.t_left

    def timer_add(self, secs):
        if self.t_end:
            self.t_end += secs
        else:
            self.t_left += secs

    def timer_toggle(self):
        now = time.time()
        if self.t_end:
            self.t_left, self.t_end = self.remaining(now), None
        elif self.t_left > 0:
            self.t_end = now + self.t_left

    def timer_reset(self):
        self.t_left, self.t_end = 0.0, None

    # quick launch
    def launch(self, name):
        from backend.system.system_ops import launch_app
        threading.Thread(target=launch_app, args=(name,), daemon=True).start()

    def add_app(self):
        self.dialog = True
        try:
            name = simpledialog.askstring("Quick Launch", "App name or URL (e.g. notepad, vs code, https://...):",
                                          parent=self.root)
        finally:
            self.dialog = False
        if name and name.strip():
            self.apps.append(name.strip().lower())
            save_apps(self.apps)

    def remove_app(self, name):
        self.apps.remove(name)
        save_apps(self.apps)

    # loop
    def tick(self):
        now = time.time()
        if self.parent_pid and now > self.next_parent_check:
            self.next_parent_check = now + 2
            if not psutil.pid_exists(self.parent_pid):
                self.root.destroy()
                return
        if self.t_end and now >= self.t_end:
            self.t_left, self.t_end, self.done_until = 0.0, None, now + 6
            winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)
        self.update_hover(now)
        tw, th = (EXP_W, EXP_H) if self.expanded else (self.collapsed_width(now), COL_H)
        self.w += (tw - self.w) * 0.3
        self.h += (th - self.h) * 0.3
        if abs(tw - self.w) < 0.5 and abs(th - self.h) < 0.5:
            self.w, self.h = tw, th
        self.draw(now)
        self.root.after(33, self.tick)

    def update_hover(self, now):
        px = (self.root.winfo_pointerx() - self.root.winfo_rootx()) / self.S
        py = (self.root.winfo_pointery() - self.root.winfo_rooty()) / self.S
        x0, y0, x1, y1 = self.pill
        if x0 - 4 <= px <= x1 + 4 and y0 - 4 <= py <= y1 + 4:
            self.last_inside = now
            self.hover_since = self.hover_since or now
            if now - self.hover_since >= HOVER_OPEN:
                self.expanded = True
        else:
            self.hover_since = None
            if self.expanded and not (self.pinned or self.dialog) and now - self.last_inside > HOVER_CLOSE:
                self.expanded = False

    def click(self, e, button):
        x, y = e.x / self.S, e.y / self.S
        for x0, y0, x1, y1, btn, cb in reversed(self.hits):
            if btn == button and x0 <= x <= x1 and y0 <= y <= y1:
                cb()
                return

    def hit(self, x0, y0, x1, y1, cb, button=0):
        self.hits.append((x0, y0, x1, y1, button, cb))

    def fit(self, text, font, max_w):
        if font.measure(text) <= max_w * self.S:
            return text
        while text and font.measure(text + "…") > max_w * self.S:
            text = text[:-1]
        return text + "…"

    # collapsed content
    def collapsed_text(self, now):
        j = self.jarvis
        st = j.get("status", "idle")
        if st == "listening":
            return j.get("message") or "Listening…"
        if st == "thinking":
            return j.get("command") or j.get("message") or "Thinking…"
        if st == "speaking":
            return j.get("response") or j.get("message") or "Speaking…"
        if st == "active":
            return j.get("message") or "Jarvis"
        if now < self.done_until:
            return "Time's up!"
        if self.t_end:
            return fmt_secs(self.remaining(now))
        if self.song:
            return self.song[0]
        return time.strftime("%I:%M %p").lstrip("0")

    def collapsed_width(self, now):
        text = self.fit(self.collapsed_text(now), self.f_text, 320)
        return min(460, max(240, self.f_text.measure(text) / self.S + 120))

    # drawing
    def draw(self, now):
        c = self.c
        c.delete("all")
        self.hits = []
        x0, y0 = (WIN_W - self.w) / 2, 6
        self.pill = (x0, y0, x0 + self.w, y0 + self.h)
        round_rect(c, x0, y0, x0 + self.w, y0 + self.h, min(self.h / 2, 28), fill=BG, outline=BG)
        if self.h < COL_H + 6:
            self.draw_collapsed(x0, y0, now)
        elif self.h > EXP_H - 12:
            self.draw_expanded(x0, y0, now)
        c.scale("all", 0, 0, self.S, self.S)

    def draw_collapsed(self, x0, y0, now):
        c, x1, cy = self.c, x0 + self.w, y0 + self.h / 2
        if self.plugged or self.battery is None:
            c.create_text(x0 + 24, cy, text=G_BOLT, font=self.f_icon, fill=GREEN)
        else:
            low = self.battery <= 20
            c.create_text(x0 + 26, cy, text=f"{self.battery}%", font=self.f_small, fill="#ef4444" if low else DIM)
        text = self.fit(self.collapsed_text(now), self.f_text, self.w - 110)
        c.create_text(x0 + self.w / 2, cy, text=text, font=self.f_text, fill=FG)
        st = self.jarvis.get("status", "idle")
        if st in STATUS_COLOR:
            pulse = 4 + 1.5 * math.sin(now * 6)
            c.create_oval(x1 - 24 - pulse, cy - pulse, x1 - 24 + pulse, cy + pulse, fill=STATUS_COLOR[st], outline="")
        elif self.song:
            self.draw_bars(x1 - 30, cy, now)
        elif self.t_end or now < self.done_until:
            c.create_text(x1 - 24, cy, text=G_TIMER, font=self.f_icon_s, fill="#f59e0b")
        else:
            c.create_text(x1 - 24, cy, text=G_CLOCK, font=self.f_icon_s, fill=DIM)

    def draw_bars(self, x, cy, now):
        for i in range(3):
            h = 4 + 5 * abs(math.sin(now * 5 + i * 1.3))
            self.c.create_rectangle(x + i * 5, cy - h, x + i * 5 + 3, cy + h, fill="#5eead4", outline="")

    def draw_expanded(self, x0, y0, now):
        c, x1 = self.c, x0 + self.w
        tabs = [("media", G_MUSIC, "Now Playing"), ("timer", G_TIMER, "Timer"), ("launch", G_APPS, "Quick Launch")]
        for i, (key, glyph, _) in enumerate(tabs):
            cx, cy = x0 + 40 + i * 40, y0 + 28
            if key == self.tab:
                round_rect(c, cx - 16, cy - 15, cx + 16, cy + 15, 8, fill=HILITE, outline=HILITE)
            c.create_text(cx, cy, text=glyph, font=self.f_icon, fill=FG if key == self.tab else DIM)
            self.hit(cx - 16, cy - 15, cx + 16, cy + 15, lambda k=key: setattr(self, "tab", k))
        title = dict((k, t) for k, _, t in tabs)[self.tab]
        c.create_text(x0 + self.w / 2, y0 + 28, text=title, font=self.f_small, fill=DIM)

        # jarvis status dot + pin
        st = self.jarvis.get("status", "idle")
        col = STATUS_COLOR.get(st, "#ef4444" if st == "offline" else "#4b5563")
        c.create_oval(x1 - 80, y0 + 24, x1 - 72, y0 + 32, fill=col, outline="")
        px, py = x1 - 40, y0 + 28
        c.create_oval(px - 15, py - 15, px + 15, py + 15, fill=HILITE if self.pinned else "#16181d", outline="")
        c.create_text(px, py, text=G_UNPIN if self.pinned else G_PIN, font=self.f_icon_s, fill=FG)
        self.hit(px - 15, py - 15, px + 15, py + 15, lambda: setattr(self, "pinned", not self.pinned))

        top = y0 + 52
        {"media": self.draw_media, "timer": self.draw_timer, "launch": self.draw_launch}[self.tab](x0, x1, top, now)

    def button(self, cx, cy, r, glyph, cb, filled=False, font=None):
        self.c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=FG if filled else HILITE, outline="")
        self.c.create_text(cx, cy, text=glyph, font=font or self.f_icon, fill=BG if filled else FG)
        self.hit(cx - r, cy - r, cx + r, cy + r, cb)

    def draw_media(self, x0, x1, top, now):
        c = self.c
        song = self.song or self.last_song
        round_rect(c, x0 + 28, top + 8, x0 + 92, top + 72, 12, fill=HILITE, outline=HILITE)
        c.create_text(x0 + 60, top + 40, text=G_MUSIC, font=self.f_title, fill=GREEN if self.song else DIM)
        if song:
            c.create_text(x0 + 108, top + 28, anchor="w", text=self.fit(song[0], self.f_title, 230),
                          font=self.f_title, fill=FG)
            c.create_text(x0 + 108, top + 52, anchor="w", text=self.fit(song[1], self.f_small, 230),
                          font=self.f_small, fill=DIM)
        else:
            c.create_text(x0 + 108, top + 28, anchor="w", text="Nothing playing", font=self.f_title, fill=FG)
            c.create_text(x0 + 108, top + 52, anchor="w", font=self.f_small, fill=DIM,
                          text="Spotify is paused" if self.spotify_running else "Click play to open Spotify")
        cy = top + 40
        play = (lambda: media_key(VK_PLAY)) if self.spotify_running else (lambda: self.launch("spotify"))
        self.button(x1 - 150, cy, 18, G_PREV, lambda: media_key(VK_PREV))
        self.button(x1 - 100, cy, 22, G_PAUSE if self.song else G_PLAY, play, filled=True)
        self.button(x1 - 50, cy, 18, G_NEXT, lambda: media_key(VK_NEXT))

    def draw_timer(self, x0, x1, top, now):
        c, cy = self.c, top + 42
        done = now < self.done_until
        c.create_text(x0 + 32, cy, anchor="w", text="Time's up!" if done else fmt_secs(self.remaining(now)),
                      font=self.f_big, fill="#f59e0b" if done or self.t_end else FG)
        bx = x1 - 290
        for label, secs in (("+1 min", 60), ("+5 min", 300)):
            round_rect(c, bx, cy - 17, bx + 64, cy + 17, 17, fill=HILITE, outline=HILITE)
            c.create_text(bx + 32, cy, text=label, font=self.f_small, fill=FG)
            self.hit(bx, cy - 17, bx + 64, cy + 17, lambda s=secs: self.timer_add(s))
            bx += 74
        self.button(bx + 22, cy, 22, G_PAUSE if self.t_end else G_PLAY, self.timer_toggle, filled=True)
        self.button(bx + 74, cy, 18, G_RESET, self.timer_reset)

    def draw_launch(self, x0, x1, top, now):
        c, cy = self.c, top + 36
        max_apps = int((self.w - 100) // 60)
        for i, name in enumerate(self.apps[:max_apps]):
            cx = x0 + 52 + i * 60
            col = APP_COLORS[sum(map(ord, name)) % len(APP_COLORS)]
            c.create_oval(cx - 22, cy - 22, cx + 22, cy + 22, fill=col, outline="")
            c.create_text(cx, cy, text=name[:1].upper(), font=self.f_title, fill=FG)
            c.create_text(cx, cy + 36, text=self.fit(name, self.f_small, 56), font=self.f_small, fill=DIM)
            self.hit(cx - 22, cy - 22, cx + 22, cy + 22, lambda n=name: self.launch(n))
            self.hit(cx - 22, cy - 22, cx + 22, cy + 22, lambda n=name: self.remove_app(n), button=1)
        cx = x0 + 52 + min(len(self.apps), max_apps) * 60
        if len(self.apps) < max_apps:
            self.button(cx, cy, 22, G_ADD, lambda: self.root.after(1, self.add_app))
        c.create_text(x1 - 28, top + 80, anchor="e", text="right-click an app to remove",
                      font=self.f_small, fill="#4b5563")


def _selftest():
    assert parse_spotify_title("Arijit Singh - Channa Mereya") == ("Channa Mereya", "Arijit Singh")
    assert parse_spotify_title("A - B - C") == ("B - C", "A")
    assert parse_spotify_title("Spotify Premium") is None
    assert parse_spotify_title("GDI+ Window (Spotify.exe)") is None
    assert fmt_secs(65) == "01:05" and fmt_secs(3600) == "1:00:00" and fmt_secs(0.2) == "00:01"
    print("selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
        sys.exit(0)
    parent = int(sys.argv[sys.argv.index("--parent") + 1]) if "--parent" in sys.argv else None
    Island(parent).root.mainloop()
