# ╔══════════════════════════════════════════════╗
# ║         J.A.R.V.I.S  —  Just A Rather Very Intelligent System ║
# ║              Voice-Activated Personal AI Assistant           ║
# ╚══════════════════════════════════════════════╝

J.A.R.V.I.S is a futuristic, voice-controlled personal AI assistant for Windows, powered by the Google Gemini API. It features a cinematic, web-based 3D HUD interface, offline console keyboard fallback, automated room/microphone calibration, and native system integration to control apps, folders, volume, brightness, screenshots, and power states.

---

## 🚀 Key Features

*   🎤 **Voice & Clap Activation**: Wake-word-free voice triggering (always listening for commands), double-clap detection to activate, or classic voice activation ("Hey Jarvis").
*   🧠 **Gemini AI Brain**: Dynamic conversation powered by Google Gemini (`gemini-2.5-flash` with automatic fallback models). Remembers recent context for seamless follow-up interactions.
*   🌐 **Cinematic 3D HUD**: Web-based interface built with **React, Vite, Framer Motion, and Three.js / React Three Fiber** on `http://localhost:5050`. Displays real-time Jarvis states (idle, listening, thinking, speaking), command logging, and hardware usage metrics.
*   💻 **Windows System Operations**:
    *   **App Launcher & Terminate**: Start or close processes (Chrome, VS Code, Notepad, Calculator, Task Manager, etc.).
    *   **Folder Navigator**: Quick access to default folders (Desktop, Downloads, Documents, Projects) or custom file paths.
    *   **Volume & Brightness Controls**: Precise master volume adjustment (via `pycaw`) and screen brightness tuning (via `screen-brightness-control`).
    *   **Screenshots**: Captures your screen and saves it straight to the Desktop.
    *   **Live System Diagnostics**: Audio reports of current CPU, RAM, GPU utilization, and Battery status.
    *   **PC Power Management**: Locked screen, sleep mode, and confirmation-guarded system shutdowns or restarts (which can be cancelled mid-countdown).
*   🖐️ **AI Hand Gesture Control System**: webcam-based input module using OpenCV and MediaPipe for virtual mouse control, scrolling, muting, and Spotify controls.
*   🎵 **Spotify Controller**: Launch Spotify, search for songs/artists, or trigger themed playlists (chill, focus, workout, sleep).
*   ⌨️ **Console Fallback**: No mic? No problem. Simply press `ENTER` in the terminal and type commands directly.

---

## 🖥️ Screenshots

Below is an overview of the cinematic HUD dashboard:

```
+-------------------------------------------------------------+
| J.A.R.V.I.S               TIME: 19:45  DATE: FRI, 12 JUN    |
+-------------------------+-----------------------------------+
|  [Vitals Gauge]         |                                   |
|   CPU: 23%  [=======]   |            [Reactor 3D Core]      |
|   RAM: 56%  [====   ]   |                                   |
|   GPU: 41%  [=====  ]   |                 / \               |
|                         |                | * |              |
|  [Theme Selector]       |                 \ /               |
|   Cyan Stark Stealth    |                                   |
|                         |                                   |
|  [Console Output Logs]  |  [Terminal Commands Input]        |
|   CMD: open notepad     |   > Ask me anything...            |
|   RSP: Opening Notepad. |                                   |
+-------------------------+-----------------------------------+
| J.A.R.V.I.S v3.5 — POWERED BY REACT & THREE.JS              |
+-------------------------------------------------------------+
```

*(Place your screenshots and UI demonstration recordings here)*

---

## 🛠️ System Architecture

The project is structured around a decoupled local communication model. The React client polls the Python API server for state updates and triggers OS commands dynamically.

```mermaid
graph TD
    subgraph Frontend (React / WebGL)
        HUD[React UI / HTML HUD] --> Context[HudContext - State Store]
        Context --> APIClient[api.js - Service Client]
    end

    subgraph Backend (Python Package)
        Wrapper[jarvis.py - Startup Wrapper] --> Main[backend/main.py - Orchestrator]
        Main --> AudioEngine[backend/voice/audio_engine.py - VAD/TTS]
        Main --> UIServer[backend/api/ui_server.py - HTTPServer]
        
        AudioEngine --> Commands[backend/assistant/commands.py - Handler]
        UIServer --> Commands
        
        Commands --> SystemOps[backend/system/system_ops.py - OS Control]
        Commands --> Brain[backend/assistant/brain.py - Gemini Client]
        Main --> Gesture[backend/system/gesture_engine.py - MediaPipe]
    end

    %% Communication Connections
    APIClient -- Polling /state & /stats --> UIServer
    APIClient -- Submit /command?text= --> UIServer
    Brain --> Gemini[Google Gemini API]
    SystemOps --> OS[Windows Desktop / Shell]
    Gesture --> OS
```

For a detailed breakdown of modules, threading logic, and network flows, see [architecture.md](file:///c:/Users/Rupadevi/Desktop/jarvis%20ai/docs/architecture.md).

---

## 📁 Project Folder Structure

The project code is organized as follows:

```
jarvis-ai/
├── jarvis.py                  # Root entry point wrapper (runs backend/main.py)
├── jarvis_hud.html            # Standalone static HUD fallback
├── jarvis_ui.html             # Legacy HUD fallback
├── .env                       # API Configuration variables
│
├── backend/                   # Python Backend Package
│   ├── __init__.py            # Main backend export definition
│   ├── main.py                # Main orchestrator loop
│   ├── core/                  # Core constants & configuration
│   │   ├── __init__.py
│   │   └── config.py          # App paths, playlist URLs, parameters
│   ├── assistant/             # AI Brain & Command Routers
│   │   ├── __init__.py
│   │   ├── brain.py           # Gemini API interface and history
│   │   └── commands.py        # System trigger matching
│   ├── voice/                 # Sound and speech components
│   │   ├── __init__.py
│   │   └── audio_engine.py    # VAD listener and TTS voice engines
│   ├── system/                # OS APIs & CV triggers
│   │   ├── __init__.py
│   │   ├── system_ops.py      # Volume, brightness, battery metrics
│   │   └── gesture_engine.py  # OpenCV & MediaPipe camera tracking
│   ├── api/                   # HTTP Local Web Bridge
│   │   ├── __init__.py
│   │   └── ui_server.py       # API endpoints and static assets hosting
│   └── utils/                 # Utility scripts
│       ├── __init__.py
│       └── dotenv.py          # Environment key loader helper
│
├── frontend/                  # React Frontend Project
│   ├── index.html             # HTML shell
│   ├── vite.config.js         # Bundler settings
│   ├── package.json           # npm manifest
│   └── src/
│       ├── main.jsx           # Mount entry point
│       ├── App.jsx            # Application provider shell
│       ├── pages/             # Layout views (Dashboard.jsx)
│       ├── components/        # Presentational blocks (Reactor3D, GlowCard)
│       ├── widgets/           # Dashboard control cards (Console, Vitals)
│       ├── services/          # Fetch API clients (api.js)
│       ├── hooks/             # Shared hooks (useHud.js)
│       ├── store/             # Global state stores (HudContext.jsx)
│       ├── animations/        # framer-motion parameter configs
│       ├── shaders/           # WebGL GLSL shader configurations
│       └── styles/            # CSS theme variables (index.css)
│
└── docs/                      # Technical Documentation
    ├── architecture.md        # Deep architectural specifications
    ├── roadmap.md             # Development goals and features
    └── changelog.md           # Version histories and changes
```

---

## 📋 Prerequisites & Installation Guide

### 1. Python Environment Setup
Install the necessary system dependencies. For full functionality, the following packages are required:

```bash
pip install numpy PyAudio SpeechRecognition pyttsx3 requests psutil GPUtil pyautogui screen-brightness-control pycaw comtypes opencv-python mediapipe
```

> [!NOTE]  
> If you experience errors installing `PyAudio` on Windows, download the appropriate precompiled wheel for your Python version from official sources or run:
> ```bash
> pip install pipwin
> pipwin install pyaudio
> ```

### 2. Configure Gemini API Key
Jarvis needs a Gemini API key to power its conversational responses.
1. Get a free API Key from [Google AI Studio](https://aistudio.google.com/).
2. Create a file named `.env` in the root folder of this project:
   ```env
   GEMINI_API_KEY=your_actual_api_key_here
   ```

### 3. Build the Frontend HUD (Optional but Recommended)
The project comes with a gorgeous, high-fidelity Three.js HUD dashboard in the `frontend` folder.
To compile it:
1. Make sure you have [Node.js](https://nodejs.org/) installed.
2. Open a terminal in the `frontend` folder and run:
   ```bash
   npm install
   npm run build
   ```
*If not compiled, the server will automatically serve a fallback static HUD page (`jarvis_hud.html`) so the system remains operational.*

---

## 🚀 Running Jarvis

1. Open a terminal in the root directory of the project and execute:
   ```bash
   python jarvis.py
   ```
2. The UI server will boot on `http://localhost:5050` and automatically launch the HUD in your default web browser.
3. Jarvis will calibrate your room's ambient noise levels for 1.5 seconds. Once finished, you will hear a confirmation message: *"Jarvis online. Good to see you, Boss."*

### Ways to Interact
*   **Speak Directly**: If `ALWAYS_LISTEN` is active, say commands like *"open YouTube"* or *"what is the time"*.
*   **Double-Clap**: Clap twice within 1.2 seconds to manually wake Jarvis up.
*   **Press Enter**: Press `ENTER` in the command window to pause recording and type commands directly.

---

## ⚙️ Customization (`backend/core/config.py`)

You can edit `backend/core/config.py` to adapt Jarvis to your personal preference:

*   `YOUR_NAME`: Changes how Jarvis addresses you (default: `"Boss"`).
*   `YOUR_CITY`: City location used for weather queries (default: `"Hyderabad"`).
*   `APPS`: Dictionary mapping spoken app names to executable commands.
*   `FOLDERS`: Paths pointing to your localized system directories.
*   `SPOTIFY_PLAYLISTS`: Connect your favorite Spotify playlist links for direct access.

---

## 🗺️ Project Roadmap

Our short-term and medium-term plans include:
- Integrating dynamic React subrouting to support detail panels.
- Incorporating local offline LLMs (via Ollama) as fallbacks when disconnected.
- Transitioning to offline wake-word engines (like Porcupine) to reduce background CPU cycles.
- Enhancing integration with Spotify APIs for in-client track queuing.

Check out the full [roadmap.md](file:///c:/Users/Rupadevi/Desktop/jarvis%20ai/docs/roadmap.md) and [changelog.md](file:///c:/Users/Rupadevi/Desktop/jarvis%20ai/docs/changelog.md) for more details.
