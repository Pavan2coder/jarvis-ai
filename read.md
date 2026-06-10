# J.A.R.V.I.S — Quick Start Guide

Welcome to **J.A.R.V.I.S** (Just A Rather Very Intelligent System), a voice-activated personal assistant for Windows powered by Gemini AI and a 3D HUD interface.

> [!TIP]
> The full, detailed documentation is available in the main [README.md](file:///c:/Users/Rupadevi/Desktop/jarvis%20ai/README.md) file.

---

## ⚡ Quick Start

### 1. Install Dependencies
Run the following command to install the required Python libraries:
```bash
pip install numpy PyAudio SpeechRecognition pyttsx3 requests psutil GPUtil pyautogui screen-brightness-control pycaw comtypes
```

### 2. Configure Gemini Key
Create a `.env` file in the root folder and add your Google Gemini API key:
```env
GEMINI_API_KEY=your_gemini_api_key_here
```

### 3. Run the Assistant
Launch Jarvis by running:
```bash
python jarvis.py
```
This will automatically open the UI dashboard at `http://localhost:5050` in your web browser.

---

## 🗣️ Common Commands

*   **Apps**: *"open notepad"*, *"close browser"*, *"launch vs code"*
*   **System**: *"volume up"*, *"set volume to 50"*, *"set brightness to 80"*, *"screenshot"*
*   **Info**: *"what time is it"*, *"how is the weather"*, *"system stats"*
*   **Media**: *"play workout music on spotify"*, *"play focus"*
*   **PC Control**: *"lock computer"*, *"shutdown"*
*   **General**: Just talk to ask questions like *"who was Albert Einstein?"* or *"explain quantum computing in one sentence."*
