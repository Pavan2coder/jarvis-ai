import gc
import time
import random
import threading
import numpy as np
import pyaudio
import speech_recognition as sr
import pyttsx3

from backend.core import config
from backend.api import ui_server

WAKE_PHRASES = ["jarvis", "hey jarvis", "ok jarvis", "okay jarvis",
                "yo jarvis", "hi jarvis", "jarvis wake up", "jervis", "service"]

ENGINE = None          # set in boot — the single shared mic owner
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
    ui_server.set_ui("speaking", message=text, response=text)
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
    ui_server.set_ui("idle", message="Standing by...")

def listen(timeout=6, phrase_limit=8):
    """Capture one spoken phrase. Uses the shared mic engine if it's running
    (so we never open the microphone twice), otherwise falls back to a
    one-shot recognizer (used when testing without the engine)."""
    # Preferred path — reuse the single shared stream
    if ENGINE is not None:
        text = ENGINE.capture_phrase(start_timeout=timeout, max_seconds=phrase_limit)
        if text:
            print(f"  👤 You » {text}")
            ui_server.set_ui("thinking", message="Processing...", command=text)
        return text or ""

    # Fallback path — no engine (e.g. typed-command session)
    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 300
    recognizer.dynamic_energy_threshold = True
    ui_server.set_ui("listening", message="Listening...")
    try:
        with sr.Microphone() as source:
            print("\n  🎤 Listening...")
            recognizer.adjust_for_ambient_noise(source, duration=0.4)
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
            text = recognizer.recognize_google(audio).lower()
            print(f"  👤 You » {text}")
            ui_server.set_ui("thinking", message="Processing...", command=text)
            return text
    except Exception:
        return ""

def _rms(data):
    return float(np.abs(np.frombuffer(data, dtype=np.int16)).mean())

def has_command_trigger(text):
    """True if the phrase contains a trigger word as a WHOLE word — so 'day'
    won't fire on 'yesterday', and 'play' won't fire on 'player'."""
    import re
    for k in config.COMMAND_TRIGGERS:
        if re.search(r"\b" + re.escape(k) + r"\b", text):
            return True
    return False

class AdaptiveClapDetector:
    def __init__(self, sensitivity: float = 0.5):
        self.sensitivity = sensitivity
        self.ambient_peak = 1000.0
        self.ambient_mean = 100.0
        self.clap_times = []
        self.last_clap_time = 0.0
        self.cooldown = config.CLAP_COOLDOWN
        self.window = config.DOUBLE_CLAP_WINDOW

    def calibrate(self, samples_peaks: list, samples_means: list):
        if samples_peaks:
            self.ambient_peak = max(400.0, float(np.median(samples_peaks)))
        if samples_means:
            self.ambient_mean = max(40.0, float(np.median(samples_means)))

    def process_frame(self, mean: float, peak: float) -> bool:
        now = time.time()
        
        # 1. Adapt running ambient levels
        is_impulsive = peak > (self.ambient_peak * 2.5)
        if not is_impulsive:
            self.ambient_peak = 0.98 * self.ambient_peak + 0.02 * peak
            self.ambient_mean = 0.98 * self.ambient_mean + 0.02 * mean
        else:
            self.ambient_peak = 0.999 * self.ambient_peak + 0.001 * peak
            self.ambient_mean = 0.999 * self.ambient_mean + 0.001 * mean
            
        self.ambient_peak = max(400.0, self.ambient_peak)
        self.ambient_mean = max(40.0, self.ambient_mean)

        # 2. Dynamic Threshold calculation
        multiplier = 12.0 - (self.sensitivity * 9.0)
        clap_threshold = max(3500.0, self.ambient_peak * multiplier)
        
        # 3. Clap Signature Validation (impulse detection & false positive prevention)
        is_loud_enough = peak > clap_threshold
        crest_factor = peak / max(1.0, mean)
        is_impulsive_crest = crest_factor > 8.5
        is_not_sustained = mean < (self.ambient_mean * 4.5)
        
        is_clap = is_loud_enough and is_impulsive_crest and is_not_sustained
        
        if is_clap:
            if (now - self.last_clap_time) > 0.15:
                self.last_clap_time = now
                self.clap_times = [t for t in self.clap_times if now - t < self.window]
                self.clap_times.append(now)
                
                # Check for double clap pattern
                if len(self.clap_times) >= 2:
                    gap = self.clap_times[-1] - self.clap_times[-2]
                    if self.cooldown < gap < self.window:
                        self.clap_times.clear()
                        return True
                        
        return False

class AudioEngine:
    def __init__(self):
        self.pa = pyaudio.PyAudio()
        # Probe every input-capable device, read a chunk from each, and keep the first that works.
        self.stream = self._open_working_input()
        self.ambient    = 80.0
        self.speech_thr = config.SPEECH_THRESHOLD
        
        # Initialize Adaptive Clap Detector
        self.clap_detector = AdaptiveClapDetector(sensitivity=config.CLAP_SENSITIVITY)
        self.clap_thr   = self.clap_detector.ambient_peak * 3.0
        
        self.busy       = False           # True while handling a command
        self.clap_times = []
        self.last_edge  = 0.0
        self.prev_loud  = False
        # chunks of silence that mark the end of a phrase (~0.7s)
        self.silence_chunks = max(6, int(0.7 * config.SAMPLE_RATE / config.CHUNK))
        self.start_chunks   = max(1, int(config.SAMPLE_RATE / config.CHUNK))   # ~1s to start

    def _try_open(self, index, rate):
        s = self.pa.open(format=pyaudio.paInt16, channels=1, rate=rate,
                         input=True, input_device_index=index,
                         frames_per_buffer=config.CHUNK)
        s.read(config.CHUNK, exception_on_overflow=False)   # prove it really reads
        return s

    def _open_working_input(self):
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
            for rate in (config.SAMPLE_RATE, int(info.get("defaultSampleRate", config.SAMPLE_RATE))):
                try:
                    stream = self._try_open(idx, rate)
                    if rate != config.SAMPLE_RATE:
                        config.SAMPLE_RATE = rate          # keep VAD/recognition in sync
                    self.dev_index, self.dev_name, self.dev_rate = idx, name, rate
                    print(f"  🎤  Using mic: [{idx}] {name}  @ {rate} Hz")
                    return stream
                except Exception:
                    continue

        # Nothing opened — list available input devices
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

    def _read(self):
        data = self.stream.read(config.CHUNK, exception_on_overflow=False)
        arr  = np.abs(np.frombuffer(data, dtype=np.int16))
        return data, float(arr.mean()), float(arr.max())

    def calibrate(self):
        print("  🎤  Calibrating mic to your room (stay quiet ~1.5s)...")
        vols, peaks = [], []
        try:
            for _ in range(int(1.5 * config.SAMPLE_RATE / config.CHUNK)):
                _, v, p = self._read()
                vols.append(v)
                peaks.append(p)
        except Exception as e:
            print(f"  ⚠️  Calibration read failed: {e}")
        peak_floor = max(peaks) if peaks else 0
        if vols:
            self.ambient    = max(40.0, float(np.median(vols)))
            self.speech_thr = max(300.0, self.ambient * 2.4)
            
            # Calibrate adaptive baseline
            self.clap_detector.calibrate(peaks, vols)
            self.clap_thr = self.clap_detector.ambient_peak * (12.0 - (self.clap_detector.sensitivity * 9.0))
            
        if self.ambient < 45:
            print("  ⚠️  Mic seems SILENT — check it's plugged in & not muted in Windows sound settings!")
        print(f"  ✅  Ambient≈{int(self.ambient)} | speak>{int(self.speech_thr)} | "
              f"clap-peak-ambient≈{int(self.clap_detector.ambient_peak)} | room-peak={int(peak_floor)}")
        print("      👏 Tip: clap twice now — watch the 'transient peak' numbers below to tune.")

    # Replaced by AdaptiveClapDetector.process_frame

    def capture_phrase(self, start_timeout=6, max_seconds=8):
        ui_server.set_ui("listening", message="Listening...")
        frames, started, silent, waited = [], False, 0, 0
        start_limit = int(start_timeout * config.SAMPLE_RATE / config.CHUNK)
        max_chunks  = int(max_seconds  * config.SAMPLE_RATE / config.CHUNK)
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
        audio = sr.AudioData(b"".join(frames), config.SAMPLE_RATE, 2)
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
            try: self.stream.read(config.CHUNK, exception_on_overflow=False)
            except Exception: break

    def activate(self, source="voice"):
        self.busy = True
        try:
            print(f"\n  🟢  JARVIS ACTIVATED  [{source.upper()}]")
            ui_server.set_ui("active", message="ACTIVATED", wake_source=source)
            time.sleep(0.2)
            speak(random.choice([
                f"Yes {config.YOUR_NAME}? I'm listening.",
                f"At your service, {config.YOUR_NAME}.",
                "Jarvis here. Go ahead.",
                "Online. What do you need?",
            ]))
            self._flush()                              # ignore the echo of my own voice
            command = self.capture_phrase(start_timeout=6, max_seconds=9)
            if command:
                print(f"  👤 You » {command}")
                ui_server.set_ui("thinking", message="Processing...", command=command)
                # Local import to avoid circular dependencies
                from backend.assistant import commands
                commands.handle_command(command)
            else:
                speak("I didn't catch that. Call me again when you're ready.")
        except Exception as e:
            print(f"  ⚠️  Activation error: {e}")
        finally:
            ui_server.set_ui("idle", message="Standing by...")
            self._flush()
            self.busy = False

    def _run_command(self, text):
        self.busy = True
        try:
            print(f"\n  ⚡  Direct command » {text}")
            ui_server.set_ui("thinking", message="Processing...", command=text)
            from backend.assistant import commands
            commands.handle_command(text)
        except Exception as e:
            print(f"  ⚠️  Command error: {e}")
        finally:
            ui_server.set_ui("idle", message="Standing by...")
            self._flush()                              # drop the echo of my reply
            self.busy = False

    def run(self):
        if config.ALWAYS_LISTEN:
            print("  🎙️   WAKE-WORD-FREE mode — just say your command, e.g. 'open youtube'.")
            print("       (Saying 'Jarvis' or double-clapping still works too.)")
        else:
            print(f"  🎙️   Listening for claps 👏👏 and wake words {WAKE_PHRASES[:4]}...")
        print("  ⌨️   Or press ENTER in this window to type a command (works without a mic).\n")
        frames, recording, silent = [], False, 0
        max_phrase = int(5 * config.SAMPLE_RATE / config.CHUNK)
        while True:
            try:
                if self.busy:
                    time.sleep(0.05)
                    continue
                data, vol, peak = self._read()

                # Show loud impulse to help tune threshold
                clap_needed = self.clap_detector.ambient_peak * (12.0 - (self.clap_detector.sensitivity * 9.0))
                if peak > clap_needed * 0.45:
                    print(f"  🔊 transient peak={int(peak)}  (clap needs >{int(clap_needed)})")

                # 1) double clap?
                if self.clap_detector.process_frame(vol, peak):
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
                        audio = sr.AudioData(b"".join(frames), config.SAMPLE_RATE, 2)
                        frames, recording, silent = [], False, 0
                        try:
                            text = sr.Recognizer().recognize_google(audio).lower()
                            print(f"  heard: [{text}]")

                            # A) wake word present
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

                            # B) wake-word-free
                            elif config.ALWAYS_LISTEN:
                                if (not config.REQUIRE_TRIGGER) or has_command_trigger(text):
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
