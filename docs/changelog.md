# Changelog — J.A.R.V.I.S

This document records the version release history and updates for J.A.R.V.I.S.

---

## [v3.5.0] — 2026-06-12
### Added
- Created a modular python package directory structure under `backend/`.
- Introduced `backend/utils/dotenv.py` environment variable parser.
- Exposed package interfaces via `__init__.py` files in all subfolders.
- Embedded a lightweight startup redirect wrapper in the root `jarvis.py` to route executions.

### Changed
- Migrated files:
  - `config.py` ➔ `backend/core/config.py`
  - `brain.py` ➔ `backend/assistant/brain.py`
  - `commands.py` ➔ `backend/assistant/commands.py`
  - `audio_engine.py` ➔ `backend/voice/audio_engine.py`
  - `system_ops.py` ➔ `backend/system/system_ops.py`
  - `gesture_engine.py` ➔ `backend/system/gesture_engine.py`
  - `ui_server.py` ➔ `backend/api/ui_server.py`
  - `jarvis.py` ➔ `backend/main.py`
- Refactored relative path resolutions (e.g. for `frontend/dist` and `.env`) to look relative to project root.
- Re-routed all backend imports to use absolute package namespaces.

### Removed
- Deleted redundant duplicate files at the root level to prevent Python namespace conflicts.

---

## [v3.0.0] — 2026-05-18
### Added
- Added Cinematic React/Three.js HUD client dashboard serving real-time logs, hardware gauges, and status flags.
- Created OpenCV and MediaPipe-based Hand Gesture Control Engine to navigate screen coordinates and pinch/scroll/mute.
- Introduced double-clap wakeup triggers.
- Added room calibration steps on startup to dynamically adjust VAD sensitivity.
- Configured automated Gemini model fallbacks to test key access states.

---

## [v2.0.0] — 2026-03-05
### Added
- Integrated Google Gemini API for natural dialog responses.
- Implemented Windows process controller actions (`taskkill` process mappings).
- Added system operations controls (master volume control and display brightness control).
- Integrated home shortcuts commands (Documents, Desktop, Downloads, Projects).
- Added system reports (PSUtil readings for RAM, CPU load, and battery capacity).
- Added Spotify theme playlist controllers.
- Integrated keyboard console fallback thread.

---

## [v1.0.0] — 2026-01-15
### Added
- Initial release featuring local Speech-to-Text transcription.
- Simple offline greeting rules and mock answer responses.
