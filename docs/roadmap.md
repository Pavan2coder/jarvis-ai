# Project Roadmap — J.A.R.V.I.S

This document outlines the milestones, current developments, and future roadmap phases for the J.A.R.V.I.S assistant project.

---

## Phase 1: Core System & Cinematic UI (Completed)
- [x] Create core orchestrator (`jarvis.py`) and audio/voice capabilities.
- [x] Implement double-clap wake system and ambient microphone calibration.
- [x] Build local HTTP state server bridge (`ui_server.py`).
- [x] Construct a cinematic Three.js WebGL HUD dashboard (React + Vite + React Three Fiber).
- [x] Integrate Google Gemini API (`gemini-2.5-flash`) for dynamic voice conversations.
- [x] Support Windows system controls (executables, volume, brightness, screenshots).
- [x] Integrate MediaPipe hand-tracking gesture inputs (webcam mouse controls, scrolling).

---

## Phase 2: Refactoring & Architecture Solidification (Completed)
- [x] Restructure backend scripts into a structured Python package layout (`backend/`).
- [x] Implement dynamic path resolutions relative to project root.
- [x] Create centralized `.env` configuration loaders and package-level API exports.
- [x] Introduce console input threads to provide a fallback interface during hardware constraints.

---

## Phase 3: Frontend Scalability & Core Settings (Short-Term)
- [ ] **Frontend Routing**: Integrate `react-router-dom` to support sub-pages (e.g. system statistics logs, custom configurations, camera diagnostic overlays).
- [ ] **Config Path Aliases**: Implement Vite path aliasing (`@/components/*`) to simplify relative imports.
- [ ] **Settings Panel Widget**: Create an interactive HUD component that updates `backend/core/config.py` options directly through API requests (e.g. modifying wake-words, toggling wake-word-free modes, camera indexing).
- [ ] **Offline LLM Fallback**: Add local LLM integration (e.g., Ollama / Llama 3) to execute offline conversation parsing when internet connectivity is lost.

---

## Phase 4: Custom Speech & Agent Capabilities (Medium-Term)
- [ ] **Offline Wake-Word Engine**: Integrate local wake-word modules (like Porcupine or Sherpa-onnx) to replace the continuous STT VAD loop, reducing background CPU load and energy usage.
- [ ] **Direct Web Search Tools**: Enable Jarvis to perform live Google searches for current events and summarize them when Gemini prompt parameters request real-time data.
- [ ] **Spotify API Integration**: Integrate the Spotify Web SDK to enable play, pause, skip, and playlist queue controls directly through Web API calls instead of opening browser tabs.
- [ ] **Visual HUD Overlays**: Overlay floating widgets on the Windows desktop for visual confirmations of volume/brightness changes, similar to native OS feedback bars.

---

## Phase 5: Smart Home & Ambient Intelligence (Long-Term)
- [ ] **Home Assistant Integration**: Control IoT appliances (lights, plugs, thermostats) directly via voice directives through Home Assistant API connections.
- [ ] **Camera Face Recognition**: Use localized face tracking to authenticate user presence and greet users personalized to their configuration profile.
- [ ] **Local Speech Cloning**: Replace system pyttsx3 voices with customized local neural TTS engines (like Coqui TTS) to sound like the cinematic JARVIS system.
- [ ] **Task Automation Agent**: Enable multi-step desktop executions (e.g. "Create a slide deck, find sales data, and draft an email") using autonomous browser/OS agent loops.
