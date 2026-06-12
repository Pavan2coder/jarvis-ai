import os

WAKE_WORD          = "jarvis"
CLAP_COOLDOWN      = 0.20   # min seconds between the two claps
DOUBLE_CLAP_WINDOW = 1.20   # max seconds between the two claps
YOUR_NAME          = "Boss"
YOUR_CITY          = "Hyderabad"

# 🗣️  WAKE-WORD-FREE MODE
ALWAYS_LISTEN  = True
REQUIRE_TRIGGER = True
COMMAND_TRIGGERS = [
    # actions
    "open", "close", "launch", "start", "stop", "disable", "turn", "kill", "shut", "shutdown", "restart",
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

# 🎧 AUDIO
SAMPLE_RATE        = 16000
CHUNK              = 1024
SPEECH_THRESHOLD   = 350     # auto-tuned at boot
CLAP_THRESHOLD     = 3000    # auto-tuned at boot

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

WEB_TAB_WORDS = ["youtube", "google", "gmail", "tab", "website", "web page", "webpage"]

# 📁 FOLDER SHORTCUTS
FOLDERS = {
    "desktop":   os.path.join(os.path.expanduser("~"), "Desktop"),
    "downloads": os.path.join(os.path.expanduser("~"), "Downloads"),
    "documents": os.path.join(os.path.expanduser("~"), "Documents"),
    "pictures":  os.path.join(os.path.expanduser("~"), "Pictures"),
    "music":     os.path.join(os.path.expanduser("~"), "Music"),
    "videos":    os.path.join(os.path.expanduser("~"), "Videos"),
    "projects":  os.path.join(os.path.expanduser("~"), "Projects"),
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

SYSTEM_PROMPT = (
    f"You are JARVIS, a witty, concise personal AI assistant for {YOUR_NAME}. "
    "Answer in 1-3 short spoken sentences. No markdown, no bullet points, no emojis "
    "— your reply is read aloud by a text-to-speech voice. Be helpful and direct."
)

jokes = [
    "Why don't scientists trust atoms? Because they make up everything!",
    "Why do programmers prefer dark mode? Because light attracts bugs!",
    "How many programmers does it take to change a light bulb? None. That's a hardware problem.",
    "I told my computer I needed a break. Now it won't stop sending me Kit-Kat ads.",
]

# 🎥 GESTURE CONTROL
GESTURES_ENABLED_ON_BOOT = False
CAMERA_INDEX = 0
