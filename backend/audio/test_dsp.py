import unittest
import time
import numpy as np
from backend.core import config
from backend.audio import CalibrationManager, AdaptiveClapDetector

class TestCalibrationManager(unittest.TestCase):
    def setUp(self):
        config.AUDIO_AUTO_RECALIBRATE_SEC = 0.1
        config.AUDIO_VAD_ACTIVATION_RATIO = 2.4
        config.AUDIO_VAD_DEACTIVATION_RATIO = 1.6
        self.calibrator = CalibrationManager()

    def test_initial_state(self):
        self.assertEqual(self.calibrator.calibrated_ambient, 80.0)
        self.assertEqual(self.calibrator.ambient, 80.0)
        self.assertGreater(self.calibrator.activation_threshold, 0)
        self.assertGreater(self.calibrator.deactivation_threshold, 0)

    def test_calibrate_baseline(self):
        vols = [100.0, 120.0, 110.0, 90.0, 80.0]
        peaks = [500.0, 600.0, 550.0, 480.0, 450.0]
        clap_detector = AdaptiveClapDetector()
        
        self.calibrator.calibrate_baseline(vols, peaks, clap_detector)
        
        expected_ambient = max(40.0, float(np.median(vols)))
        self.assertEqual(self.calibrator.calibrated_ambient, expected_ambient)
        self.assertEqual(self.calibrator.ambient, expected_ambient)
        self.assertEqual(clap_detector.ambient_peak, float(np.median(peaks)))
        self.assertEqual(clap_detector.ambient_mean, float(np.median(vols)))

    def test_update_noise_floor(self):
        initial_ambient = self.calibrator.ambient
        # Update with a higher noise level
        self.calibrator.update_noise_floor(150.0)
        
        # Noise levels should increase
        self.assertGreater(self.calibrator.short_term_noise, initial_ambient)
        self.assertGreater(self.calibrator.long_term_noise, initial_ambient)
        self.assertEqual(self.calibrator.ambient, self.calibrator.long_term_noise)
        
        # Check that thresholds adapt
        expected_activation = max(300.0, self.calibrator.long_term_noise * config.AUDIO_VAD_ACTIVATION_RATIO)
        self.assertEqual(self.calibrator.activation_threshold, expected_activation)

    def test_auto_recalibration_trigger(self):
        clap_detector = AdaptiveClapDetector()
        self.calibrator.calibrated_ambient = 80.0
        self.calibrator.short_term_noise = 200.0
        self.calibrator.long_term_noise = 200.0
        
        # Stability: abs(short_term_noise - long_term_noise) / long_term_noise < 0.10 => 0.0 < 0.10
        # Deviation: abs(200 - 80) / 80 = 1.5 > 0.30
        
        # First check sets stable_ambient_time
        recal_triggered_1 = self.calibrator.check_auto_recalibration(clap_detector)
        self.assertFalse(recal_triggered_1)
        self.assertGreater(self.calibrator.stable_ambient_time, 0.0)
        
        # Fast-forward time to exceed config.AUDIO_AUTO_RECALIBRATE_SEC
        original_stable_time = self.calibrator.stable_ambient_time
        self.calibrator.stable_ambient_time = original_stable_time - (config.AUDIO_AUTO_RECALIBRATE_SEC + 1.0)
        
        # Second check should trigger auto-recalibration
        recal_triggered_2 = self.calibrator.check_auto_recalibration(clap_detector)
        self.assertTrue(recal_triggered_2)
        self.assertEqual(self.calibrator.calibrated_ambient, 200.0)
        self.assertEqual(self.calibrator.stable_ambient_time, 0.0)
        self.assertEqual(clap_detector.ambient_peak, max(400.0, 200.0 * 10.0))
        self.assertEqual(clap_detector.ambient_mean, max(40.0, 200.0))


class TestAdaptiveClapDetector(unittest.TestCase):
    def setUp(self):
        config.CLAP_COOLDOWN = 0.05
        config.DOUBLE_CLAP_WINDOW = 0.8
        config.CLAP_SENSITIVITY = 0.5
        self.detector = AdaptiveClapDetector(sensitivity=0.5)
        self.detector.ambient_peak = 1000.0
        self.detector.ambient_mean = 100.0

    def test_calibrate(self):
        self.detector.calibrate([2000.0, 3000.0], [200.0, 300.0])
        self.assertEqual(self.detector.ambient_peak, 2500.0)
        self.assertEqual(self.detector.ambient_mean, 250.0)

    def test_impulsive_decay_detection(self):
        # Frame 1: Loud impulsive transient peak (looks like a clap, stored as candidate)
        res1 = self.detector.process_frame(mean=120.0, peak=8000.0)
        self.assertFalse(res1)  # False on first frame (needs decay check)
        self.assertIsNotNone(self.detector.pending_candidate)
        self.assertEqual(self.detector.pending_candidate["peak"], 8000.0)
        
        # Frame 2: Rapid decay (peak < 4000.0), confirmed first clap!
        res2 = self.detector.process_frame(mean=80.0, peak=1500.0)
        self.assertFalse(res2)  # False because we need a double clap
        self.assertIsNone(self.detector.pending_candidate)
        self.assertEqual(len(self.detector.clap_times), 1)

    def test_double_clap(self):
        # First clap sequence
        self.detector.process_frame(mean=120.0, peak=8000.0)
        self.detector.process_frame(mean=80.0, peak=1500.0)
        self.assertEqual(len(self.detector.clap_times), 1)
        
        # Wait for cooldown gap (> 0.15s)
        time.sleep(0.20)
        
        # Second clap sequence
        self.detector.process_frame(mean=120.0, peak=8000.0)
        res = self.detector.process_frame(mean=80.0, peak=1500.0)
        
        # Should trigger double clap
        self.assertTrue(res)
        self.assertEqual(len(self.detector.clap_times), 0)

    def test_sustained_sound_rejection(self):
        # Loud but mean is too high relative to ambient_mean (not impulsive or crest too low)
        res1 = self.detector.process_frame(mean=3000.0, peak=8000.0)
        self.assertFalse(res1)
        self.assertIsNone(self.detector.pending_candidate)
        
        # Loud impulsive peak but decay check fails in next frame
        self.detector.process_frame(mean=120.0, peak=8000.0)
        self.assertIsNotNone(self.detector.pending_candidate)
        
        # Frame 2 is still high (does not drop by >= 50%)
        res2 = self.detector.process_frame(mean=3000.0, peak=7000.0)
        self.assertFalse(res2)
        self.assertIsNone(self.detector.pending_candidate)
        self.assertEqual(len(self.detector.clap_times), 0)

if __name__ == "__main__":
    unittest.main()
