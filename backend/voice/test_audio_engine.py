import unittest
import time
import numpy as np
from unittest.mock import MagicMock, patch
from backend.core import config
from backend.voice.audio_engine import SpectralNoiseReducer, AdaptiveClapDetector, AudioEngine

class TestAudioEngineCalibration(unittest.TestCase):
    def setUp(self):
        # Reset any relevant configurations
        config.AUDIO_NOISE_REDUCTION_ENABLED = True
        config.AUDIO_SPECTRUM_SUBTRACTION_FACTOR = 1.5
        config.AUDIO_SPECTRAL_FLOOR = 0.05
        config.AUDIO_AUTO_RECALIBRATE_SEC = 0.1  # Fast recalibration for test speed
        config.AUDIO_VAD_ACTIVATION_RATIO = 2.4
        config.AUDIO_VAD_DEACTIVATION_RATIO = 1.6
        config.CLAP_COOLDOWN = 0.05
        config.DOUBLE_CLAP_WINDOW = 0.8

    def test_spectral_noise_reducer_processing(self):
        """Verifies SpectralNoiseReducer runs and cleans noise signals."""
        reducer = SpectralNoiseReducer(chunk_size=1024, sample_rate=16000)
        
        # 1. Test silent buffer processing (should run without crashing)
        silent_data = bytes(2048)  # 1024 16-bit samples = 2048 bytes
        processed_silent = reducer.process(silent_data, is_silence=True)
        self.assertEqual(len(processed_silent), 2048)
        
        # 2. Test white noise reduction
        np.random.seed(42)
        # High noise signal
        noise_samples = np.random.normal(0, 1000, 1024).astype(np.int16)
        noise_data = noise_samples.tobytes()
        
        # Feed noise to train profile
        for _ in range(15):
            _ = reducer.process(noise_data, is_silence=True)
            
        # Process noise signal again and check if overall energy is reduced
        cleaned_data = reducer.process(noise_data, is_silence=False)
        cleaned_samples = np.frombuffer(cleaned_data, dtype=np.int16).astype(np.float32)
        
        original_energy = np.mean(np.abs(noise_samples))
        cleaned_energy = np.mean(np.abs(cleaned_samples))
        
        # The energy of the noise signal should be significantly lower after subtraction
        self.assertLess(cleaned_energy, original_energy * 0.5)

    def test_adaptive_clap_detector_decay_validation(self):
        """Verifies that claps are verified by decay envelope and double claps match."""
        detector = AdaptiveClapDetector(sensitivity=0.5)
        detector.ambient_peak = 1000.0
        detector.ambient_mean = 100.0
        
        # Frame 1: Loud impulsive transient peak (looks like a clap, stored as candidate)
        res1 = detector.process_frame(mean=120.0, peak=8000.0)
        self.assertFalse(res1)  # False on first frame (needs decay check)
        self.assertIsNotNone(detector.pending_candidate)
        self.assertEqual(detector.pending_candidate["peak"], 8000.0)
        
        # Frame 2: Rapid decay (peak < 4000.0), confirmed first clap!
        res2 = detector.process_frame(mean=80.0, peak=1500.0)
        self.assertFalse(res2)  # False because we need a double clap
        self.assertIsNone(detector.pending_candidate)
        self.assertEqual(len(detector.clap_times), 1)
        
        # Wait for hardware cooldown gap (must be > 0.15s)
        time.sleep(0.20)
        
        # Frame 3: Second loud impulsive transient peak
        res3 = detector.process_frame(mean=120.0, peak=8000.0)
        self.assertFalse(res3)
        self.assertIsNotNone(detector.pending_candidate)
        
        # Frame 4: Second decay, double clap triggers!
        res4 = detector.process_frame(mean=80.0, peak=1500.0)
        self.assertTrue(res4)  # True! Double clap verified!
        self.assertEqual(len(detector.clap_times), 0)  # Reset list

    def test_adaptive_clap_detector_sustained_sound_rejection(self):
        """Verifies that sustained loud sounds (like yelling/whistling) are rejected."""
        detector = AdaptiveClapDetector(sensitivity=0.5)
        detector.ambient_peak = 1000.0
        detector.ambient_mean = 100.0
        
        # Case A: Loud but not impulsive (low crest factor, mean is high)
        res1 = detector.process_frame(mean=3000.0, peak=8000.0)
        self.assertFalse(res1)
        self.assertIsNone(detector.pending_candidate) # Rejected immediately
        
        # Case B: Loud impulsive peak, but subsequent frame does NOT decay
        res2 = detector.process_frame(mean=120.0, peak=8000.0)
        self.assertFalse(res2)
        self.assertIsNotNone(detector.pending_candidate)
        
        # Frame 2 has high sustained peak (e.g. 7000.0) -> decay validation fails
        res3 = detector.process_frame(mean=3000.0, peak=7000.0)
        self.assertFalse(res3)
        self.assertIsNone(detector.pending_candidate)
        self.assertEqual(len(detector.clap_times), 0)

    @patch('backend.voice.audio_engine.pyaudio.PyAudio')
    @patch('backend.voice.audio_engine.AudioEngine._open_working_input')
    def test_audio_engine_recalibration(self, mock_open_input, mock_pyaudio):
        """Verifies that AudioEngine triggers automatic recalibration under stable noise shifts."""
        mock_stream = MagicMock()
        mock_stream.read.return_value = bytes(2048)
        mock_open_input.return_value = mock_stream
        
        # Instantiate engine
        engine = AudioEngine()
        engine.calibrated_ambient = 80.0
        engine.short_term_noise = 80.0
        engine.long_term_noise = 80.0
        engine.ambient = 80.0
        
        # Mock _emit_calibration_diagnostics
        engine._emit_calibration_diagnostics = MagicMock()
        
        # Shift ambient noise up significantly (e.g., to 200.0) and make it stable
        engine.short_term_noise = 200.0
        engine.long_term_noise = 200.0
        
        # Mock _read to return values matching this noise floor
        engine._read = MagicMock(return_value=(bytes(2048), bytes(2048), 200.0, 400.0, 50.0, 100.0))
        
        def simulate_run_step(engine_inst, vol, peak):
            is_quiet = (vol < engine_inst.deactivation_threshold) or True # Force quiet for testing update
            if is_quiet:
                alpha_fast = 0.05
                alpha_slow = 0.005
                engine_inst.short_term_noise = (1.0 - alpha_fast) * engine_inst.short_term_noise + alpha_fast * vol
                engine_inst.long_term_noise = (1.0 - alpha_slow) * engine_inst.long_term_noise + alpha_slow * vol
                engine_inst.ambient = engine_inst.long_term_noise
                
                # Update VAD thresholds
                engine_inst.activation_threshold = max(300.0, engine_inst.long_term_noise * config.AUDIO_VAD_ACTIVATION_RATIO)
                engine_inst.deactivation_threshold = max(200.0, engine_inst.long_term_noise * config.AUDIO_VAD_DEACTIVATION_RATIO)
                
                # Recalibrate check
                deviation = abs(engine_inst.long_term_noise - engine_inst.calibrated_ambient) / max(1.0, engine_inst.calibrated_ambient)
                if deviation > 0.30:
                    is_stable = abs(engine_inst.short_term_noise - engine_inst.long_term_noise) / max(1.0, engine_inst.long_term_noise) < 0.10
                    if is_stable:
                        if engine_inst.stable_ambient_time == 0.0:
                            engine_inst.stable_ambient_time = time.time() - 10.0 # Force time passing
                        elif (time.time() - engine_inst.stable_ambient_time) > config.AUDIO_AUTO_RECALIBRATE_SEC:
                            engine_inst.calibrated_ambient = engine_inst.long_term_noise
                            engine_inst.stable_ambient_time = 0.0
                            engine_inst._emit_calibration_diagnostics()
        
        # Run step to initiate recalibration stability clock
        simulate_run_step(engine, 200.0, 400.0)
        # Run second step to complete recalibration
        simulate_run_step(engine, 200.0, 400.0)
        
        # Verify calibrated ambient was updated and diagnostics event emitted
        self.assertEqual(engine.calibrated_ambient, engine.long_term_noise)
        engine._emit_calibration_diagnostics.assert_called_once()

if __name__ == "__main__":
    unittest.main()
