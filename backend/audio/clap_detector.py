import time
import numpy as np
from backend.core import config

class AdaptiveClapDetector:
    def __init__(self, sensitivity: float = 0.5):
        self.sensitivity = sensitivity
        self.ambient_peak = 1000.0
        self.ambient_mean = 100.0
        self.clap_times = []
        self.last_clap_time = 0.0
        self.cooldown = config.CLAP_COOLDOWN
        self.window = config.DOUBLE_CLAP_WINDOW
        self.pending_candidate = None

    def calibrate(self, samples_peaks: list, samples_means: list):
        """Estimate initial room baseline levels for claps."""
        if samples_peaks:
            self.ambient_peak = max(400.0, float(np.median(samples_peaks)))
        if samples_means:
            self.ambient_mean = max(40.0, float(np.median(samples_means)))

    def process_frame(self, mean: float, peak: float) -> bool:
        """
        Processes a single audio frame's mean/peak levels to detect a double clap.
        Enforces dynamic noise-scaling, crest factor bounds, and decay checking.
        """
        now = time.time()
        
        # 1. Adapt running ambient noise statistics via EMA
        is_impulsive = peak > (self.ambient_peak * 2.5)
        if not is_impulsive:
            self.ambient_peak = 0.98 * self.ambient_peak + 0.02 * peak
            self.ambient_mean = 0.98 * self.ambient_mean + 0.02 * mean
        else:
            self.ambient_peak = 0.999 * self.ambient_peak + 0.001 * peak
            self.ambient_mean = 0.999 * self.ambient_mean + 0.001 * mean
            
        self.ambient_peak = max(400.0, self.ambient_peak)
        self.ambient_mean = max(40.0, self.ambient_mean)

        # 2. Dynamic threshold calculation adjusted for room noise
        noise_factor = min(2.0, max(1.0, self.ambient_mean / 100.0))
        multiplier = (12.0 - (self.sensitivity * 9.0)) * noise_factor
        clap_threshold = max(3500.0, self.ambient_peak * multiplier)
        
        # 3. Transient decay validation check (analyzing previous frame candidate)
        is_confirmed_clap = False
        if self.pending_candidate is not None:
            candidate_peak = self.pending_candidate["peak"]
            # Assert rapid decay: peak must drop by at least 50% in next 64ms chunk
            if peak < 0.5 * candidate_peak:
                is_confirmed_clap = True
            self.pending_candidate = None

        # 4. Clap signature checks
        is_loud_enough = peak > clap_threshold
        crest_factor = peak / max(1.0, mean)
        required_crest = 8.5 * noise_factor
        is_impulsive_crest = crest_factor > required_crest
        is_not_sustained = mean < (self.ambient_mean * 4.5 * noise_factor)
        
        # If impulse matches, store as candidate for next frame decay checking
        if is_loud_enough and is_impulsive_crest and is_not_sustained:
            self.pending_candidate = {"time": now, "peak": peak, "mean": mean}
        
        # 5. Double-clap validation
        if is_confirmed_clap:
            if (now - self.last_clap_time) > 0.15: # Cooldown gap
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
