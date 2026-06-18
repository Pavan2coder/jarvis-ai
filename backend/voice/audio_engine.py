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
from backend.audio import CalibrationManager, AdaptiveClapDetector

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


class SpectralNoiseReducer:
    def __init__(self, chunk_size: int = 1024, sample_rate: int = 16000):
        self.chunk_size = chunk_size
        self.sample_rate = sample_rate
        self.num_bins = chunk_size // 2 + 1
        self.noise_power = np.zeros(self.num_bins, dtype=np.float32)
        self.noise_count = 0
        self.noise_alpha = 0.95
        self.subtraction_factor = config.AUDIO_SPECTRUM_SUBTRACTION_FACTOR
        self.spectral_floor = config.AUDIO_SPECTRAL_FLOOR

    def update_noise_profile(self, magnitude_spectrum: np.ndarray):
        """Update noise power profile using an exponential moving average."""
        if self.noise_count == 0:
            self.noise_power = magnitude_spectrum.copy()
        else:
            self.noise_power = (self.noise_alpha * self.noise_power + 
                                (1.0 - self.noise_alpha) * magnitude_spectrum)
        self.noise_count += 1

    def process(self, audio_data: bytes, is_silence: bool = False) -> bytes:
        """Apply real-time spectral subtraction to the audio chunk."""
        if not config.AUDIO_NOISE_REDUCTION_ENABLED:
            return audio_data

        try:
            samples = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
            if len(samples) != self.chunk_size:
                return audio_data

            # FFT
            spectrum = np.fft.rfft(samples)
            magnitude = np.abs(spectrum)
            phase = np.angle(spectrum)

            # Update noise profile during silence or initial frames
            if is_silence or self.noise_count < 10:
                self.update_noise_profile(magnitude)

            # Subtract estimated noise magnitude
            subtracted_magnitude = magnitude - self.subtraction_factor * self.noise_power
            
            # Floor to prevent negative values and reduce musical noise artifacts
            floor_value = self.spectral_floor * magnitude
            subtracted_magnitude = np.maximum(subtracted_magnitude, floor_value)

            # Reconstruct and IFFT
            cleaned_spectrum = subtracted_magnitude * np.exp(1j * phase)
            cleaned_samples = np.fft.irfft(cleaned_spectrum)

            cleaned_samples = np.clip(cleaned_samples, -32768, 32767).astype(np.int16)
            return cleaned_samples.tobytes()
        except Exception:
            return audio_data


class AudioEngine:
    def __init__(self):
        self.pa = pyaudio.PyAudio()
        # Probe every input-capable device, read a chunk from each, and keep the first that works.
        self.stream = self._open_working_input()
        
        # Audio package DSP modules
        self.calibration = CalibrationManager()
        self.clap_detector = AdaptiveClapDetector(sensitivity=config.CLAP_SENSITIVITY)
        self.clap_thr = self.clap_detector.ambient_peak * 3.0
        
        # Noise reducer
        self.noise_reducer = SpectralNoiseReducer(config.CHUNK, config.SAMPLE_RATE)
        
        self.busy = False           # True while handling a command
        self.flush_pending = False  # set by worker after TTS; cleared by run() loop
        self.clap_times = []
        self.last_edge = 0.0
        self.prev_loud = False
        
        # chunks of silence that mark the end of a phrase (~0.7s)
        self.silence_chunks = max(6, int(0.7 * config.SAMPLE_RATE / config.CHUNK))
        self.start_chunks = max(1, int(config.SAMPLE_RATE / config.CHUNK))   # ~1s to start

    @property
    def ambient(self):
        return self.calibration.ambient
    
    @ambient.setter
    def ambient(self, val):
        self.calibration.ambient = val
        
    @property
    def speech_thr(self):
        return self.calibration.activation_threshold
    
    @speech_thr.setter
    def speech_thr(self, val):
        self.calibration.activation_threshold = val

    @property
    def activation_threshold(self):
        return self.calibration.activation_threshold

    @activation_threshold.setter
    def activation_threshold(self, val):
        self.calibration.activation_threshold = val

    @property
    def deactivation_threshold(self):
        return self.calibration.deactivation_threshold

    @deactivation_threshold.setter
    def deactivation_threshold(self, val):
        self.calibration.deactivation_threshold = val

    @property
    def calibrated_ambient(self):
        return self.calibration.calibrated_ambient
    
    @calibrated_ambient.setter
    def calibrated_ambient(self, val):
        self.calibration.calibrated_ambient = val
        
    @property
    def short_term_noise(self):
        return self.calibration.short_term_noise
        
    @short_term_noise.setter
    def short_term_noise(self, val):
        self.calibration.short_term_noise = val
        
    @property
    def long_term_noise(self):
        return self.calibration.long_term_noise
        
    @long_term_noise.setter
    def long_term_noise(self, val):
        self.calibration.long_term_noise = val

    @property
    def stable_ambient_time(self):
        return self.calibration.stable_ambient_time

    @stable_ambient_time.setter
    def stable_ambient_time(self, val):
        self.calibration.stable_ambient_time = val

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
        raw_data = self.stream.read(config.CHUNK, exception_on_overflow=False)
        arr = np.abs(np.frombuffer(raw_data, dtype=np.int16))
        vol = float(arr.mean())
        peak = float(arr.max())
        
        # Silence gating flag for updating noise estimation spectrum
        is_silence = vol < self.deactivation_threshold
        
        # Apply spectral noise reduction
        cleaned_data = self.noise_reducer.process(raw_data, is_silence=is_silence)
        cleaned_arr = np.abs(np.frombuffer(cleaned_data, dtype=np.int16))
        cleaned_vol = float(cleaned_arr.mean())
        cleaned_peak = float(cleaned_arr.max())
        
        return raw_data, cleaned_data, vol, peak, cleaned_vol, cleaned_peak

    def _emit_calibration_diagnostics(self):
        try:
            from backend.websocket.events import dispatcher, JarvisEvent, JarvisEventType
            from backend.websocket.socket_manager import manager
            diag_data = {
                "ambient": float(self.ambient),
                "calibrated_ambient": float(self.calibrated_ambient),
                "speech_threshold": float(self.activation_threshold),
                "deactivation_threshold": float(self.deactivation_threshold),
                "clap_threshold": float(self.clap_detector.ambient_peak * (12.0 - (self.clap_detector.sensitivity * 9.0)))
            }
            event = JarvisEvent(JarvisEventType.DIAGNOSTICS_UPDATE, data={
                "type": "microphone_calibration",
                "metrics": diag_data
            })
            dispatcher.emit_sync(event, loop=manager.loop)
        except Exception:
            pass

    def calibrate(self):
        print("  🎤  Calibrating mic to your room (stay quiet ~1.5s)...")
        vols, peaks = [], []
        try:
            for _ in range(int(1.5 * config.SAMPLE_RATE / config.CHUNK)):
                _, _, v, p, _, _ = self._read()
                vols.append(v)
                peaks.append(p)
        except Exception as e:
            print(f"  ⚠️  Calibration read failed: {e}")
        peak_floor = max(peaks) if peaks else 0
        if vols:
            self.calibration.calibrate_baseline(vols, peaks, self.clap_detector)
            self.clap_thr = self.clap_detector.ambient_peak * (12.0 - (self.clap_detector.sensitivity * 9.0))
            
        if self.ambient < 45:
            print("  ⚠️  Mic seems SILENT — check it's plugged in & not muted in Windows sound settings!")
        print(f"  ✅  Ambient≈{int(self.ambient)} | speak-activation>{int(self.activation_threshold)} | "
              f"speak-deactivation>{int(self.deactivation_threshold)} | "
              f"clap-peak-ambient≈{int(self.clap_detector.ambient_peak)} | room-peak={int(peak_floor)}")
        print("      👏 Tip: clap twice now — watch the 'transient peak' numbers below to tune.")

    def capture_phrase(self, start_timeout=6, max_seconds=8):
        ui_server.set_ui("listening", message="Listening...")
        frames, started, silent, waited = [], False, 0, 0
        start_limit = int(start_timeout * config.SAMPLE_RATE / config.CHUNK)
        max_chunks  = int(max_seconds  * config.SAMPLE_RATE / config.CHUNK)
        while True:
            try:
                _, cleaned_data, _, _, cleaned_vol, _ = self._read()
            except Exception:
                return None
            if not started:
                waited += 1
                if cleaned_vol > self.activation_threshold:
                    started, silent = True, 0
                    frames.append(cleaned_data)
                elif waited > start_limit:
                    return None                       # nothing said
            else:
                frames.append(cleaned_data)
                if cleaned_vol < self.deactivation_threshold:
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
            try:
                self.stream.read(config.CHUNK, exception_on_overflow=False)
            except Exception:
                break

    def activate(self, source="voice"):
        # Hold busy for the full greeting + capture phase so the audio loop
        # doesn't re-enter while we own the mic stream.  The worker will
        # re-acquire busy via on_command_start before we release it here.
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
            self._flush()                              # drop echo of the greeting
            command = self.capture_phrase(start_timeout=6, max_seconds=9)
            if command:
                print(f"  👤 You » {command}")
                ui_server.set_ui("thinking", message="Processing...", command=command)
                from core.command_queue import COMMAND_QUEUE, CommandSource
                if not COMMAND_QUEUE.put(command, CommandSource.VOICE):
                    speak("I'm a bit overloaded right now. Please try again.")
            else:
                speak("I didn't catch that. Call me again when you're ready.")
        except Exception as e:
            print(f"  ⚠️  Activation error: {e}")
        finally:
            # Release busy so the audio loop can proceed.  The worker sets
            # busy=True in on_command_start within milliseconds of the put()
            # above, so the gap where busy=False is negligible.
            self.busy = False

    def _run_command(self, text):
        # Non-blocking: hand the command to the worker and return immediately.
        # The worker manages the busy flag and UI state via its lifecycle hooks.
        print(f"\n  ⚡  Direct command » {text}")
        from core.command_queue import COMMAND_QUEUE, CommandSource
        if not COMMAND_QUEUE.put(text, CommandSource.VOICE):
            print("  ⚠️  Command queue full — command dropped.")

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
                # Flush the mic buffer when the worker signals it (echo suppression
                # after TTS reply).  Checked here — outside the busy branch — so it
                # fires even if busy transitions to False in the same scheduler tick.
                if self.flush_pending:
                    self._flush()
                    self.flush_pending = False

                if self.busy:
                    time.sleep(0.05)
                    continue
                raw_data, cleaned_data, vol, peak, cleaned_vol, cleaned_peak = self._read()

                # Dynamic Ambient Noise Floor Tracking & Hysteresis VAD Adjustments
                # Only update background ambient estimates during quiet, non-triggering times
                is_quiet = (vol < self.deactivation_threshold) and (peak < self.clap_detector.ambient_peak * 1.5)
                if not recording and is_quiet:
                    self.calibration.update_noise_floor(vol)
                    
                    # Automatic Recalibration Check
                    self.calibration.check_auto_recalibration(self.clap_detector)
                else:
                    self.stable_ambient_time = 0.0

                # Show loud impulse to help tune threshold
                clap_needed = self.clap_detector.ambient_peak * (12.0 - (self.clap_detector.sensitivity * 9.0))
                if peak > clap_needed * 0.45:
                    print(f"  🔊 transient peak={int(peak)}  (clap needs >{int(clap_needed)})")

                # 1) double clap? (Uses original raw vol and peak for impulse/clap detection)
                if self.clap_detector.process_frame(vol, peak):
                    print("\n  👏👏  Double clap detected!")
                    frames, recording, silent = [], False, 0
                    self.activate("clap")
                    continue

                # 2) wake word via VAD-captured phrase (Uses noise-reduced cleaned data and volume)
                if cleaned_vol > self.activation_threshold:
                    recording = True
                    frames.append(cleaned_data)
                    silent = 0
                elif recording:
                    frames.append(cleaned_data)
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
