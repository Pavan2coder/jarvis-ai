import time
import numpy as np
from backend.core import config

class CalibrationManager:
    def __init__(self):
        # Noise profile states
        self.calibrated_ambient = 80.0
        self.short_term_noise = 80.0
        self.long_term_noise = 80.0
        self.ambient = 80.0
        
        # Configurable thresholds
        self.activation_threshold = config.SPEECH_THRESHOLD
        self.deactivation_threshold = config.SPEECH_THRESHOLD * 0.7
        
        # Recalibration tracker
        self.stable_ambient_time = 0.0

    def update_noise_floor(self, vol: float):
        """Update slow and fast moving averages of the ambient noise floor during quiet periods."""
        alpha_fast = 0.05
        alpha_slow = 0.005
        self.short_term_noise = (1.0 - alpha_fast) * self.short_term_noise + alpha_fast * vol
        self.long_term_noise = (1.0 - alpha_slow) * self.long_term_noise + alpha_slow * vol
        self.ambient = self.long_term_noise
        
        # Dynamically adapt thresholds
        self.activation_threshold = max(300.0, self.long_term_noise * config.AUDIO_VAD_ACTIVATION_RATIO)
        self.deactivation_threshold = max(200.0, self.long_term_noise * config.AUDIO_VAD_DEACTIVATION_RATIO)

    def check_auto_recalibration(self, clap_detector) -> bool:
        """
        Check if the ambient noise has shifted significantly and stabilized.
        If so, trigger non-blocking auto-recalibration.
        """
        deviation = abs(self.long_term_noise - self.calibrated_ambient) / max(1.0, self.calibrated_ambient)
        if deviation > 0.30:
            is_stable = abs(self.short_term_noise - self.long_term_noise) / max(1.0, self.long_term_noise) < 0.10
            if is_stable:
                if self.stable_ambient_time == 0.0:
                    self.stable_ambient_time = time.time()
                elif (time.time() - self.stable_ambient_time) > config.AUDIO_AUTO_RECALIBRATE_SEC:
                    print(f"\n  [*] Auto-recalibrating microphone baseline (noise level shifted from {int(self.calibrated_ambient)} to {int(self.long_term_noise)})...")
                    self.calibrated_ambient = self.long_term_noise
                    self.stable_ambient_time = 0.0
                    
                    # Adapt clap detector ambient parameters
                    clap_detector.ambient_peak = max(400.0, self.long_term_noise * 10.0)
                    clap_detector.ambient_mean = max(40.0, self.long_term_noise)
                    
                    self._emit_calibration_diagnostics(clap_detector)
                    return True
            else:
                self.stable_ambient_time = 0.0
        else:
            self.stable_ambient_time = 0.0
        return False

    def calibrate_baseline(self, vols: list, peaks: list, clap_detector):
        """Establish initial room calibration baseline and set VAD/clap thresholds."""
        if vols:
            self.calibrated_ambient = max(40.0, float(np.median(vols)))
            self.short_term_noise = self.calibrated_ambient
            self.long_term_noise = self.calibrated_ambient
            self.ambient = self.calibrated_ambient
            
            # Recalculate VAD activation and deactivation thresholds
            self.activation_threshold = max(300.0, self.calibrated_ambient * config.AUDIO_VAD_ACTIVATION_RATIO)
            self.deactivation_threshold = max(200.0, self.calibrated_ambient * config.AUDIO_VAD_DEACTIVATION_RATIO)
            
            # Calibrate adaptive baseline for claps
            clap_detector.calibrate(peaks, vols)

    def _emit_calibration_diagnostics(self, clap_detector):
        """Broadcast updated thresholds to the React UI."""
        try:
            from backend.websocket.events import dispatcher, JarvisEvent, JarvisEventType
            from backend.websocket.socket_manager import manager
            diag_data = {
                "ambient": float(self.ambient),
                "calibrated_ambient": float(self.calibrated_ambient),
                "speech_threshold": float(self.activation_threshold),
                "deactivation_threshold": float(self.deactivation_threshold),
                "clap_threshold": float(clap_detector.ambient_peak * (12.0 - (clap_detector.sensitivity * 9.0)))
            }
            event = JarvisEvent(JarvisEventType.DIAGNOSTICS_UPDATE, data={
                "type": "microphone_calibration",
                "metrics": diag_data
            })
            dispatcher.emit_sync(event, loop=manager.loop)
        except Exception:
            pass
