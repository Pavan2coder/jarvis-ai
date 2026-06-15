import unittest
import time
from backend.vision.gesture_debouncer import GestureDebouncer

class TestGestureDebouncer(unittest.TestCase):
    def setUp(self):
        # Set up a debouncer with custom test settings
        self.debouncer = GestureDebouncer(
            buffer_size=10,
            stability_threshold=7,
            default_cooldown=1.0,
            confidence_threshold=0.65
        )

    def test_stability_threshold(self):
        """Verifies that a gesture is only stabilized when it reaches the stability threshold."""
        # Add 6 matching frames
        for _ in range(6):
            g, a = self.debouncer.add_frame("Fist", "Mute", 0.8)
            self.assertEqual(g, "None")
            
        # 7th frame reaches threshold (7 out of 10)
        g, a = self.debouncer.add_frame("Fist", "Mute", 0.8)
        self.assertEqual(g, "Fist")
        self.assertEqual(a, "Mute")

    def test_confidence_threshold_filtering(self):
        """Verifies that frames with confidence below the threshold are ignored."""
        # Add 10 frames with low confidence
        for _ in range(10):
            g, a = self.debouncer.add_frame("Fist", "Mute", 0.6)
            self.assertEqual(g, "None")
            
        # Pushing a high-confidence frame still doesn't stabilize it immediately
        g, a = self.debouncer.add_frame("Fist", "Mute", 0.9)
        self.assertEqual(g, "None")

    def test_cooldown_and_duplicate_prevention(self):
        """Verifies that a discrete gesture triggers only once on transition and respects cooldown."""
        # Stabilize Fist (needs 7 frames)
        for _ in range(6):
            self.debouncer.add_frame("Fist", "Mute", 0.8)
            
        # Frame 7: becomes stable, should be eligible to trigger
        g, a = self.debouncer.add_frame("Fist", "Mute", 0.8)
        self.assertEqual(g, "Fist")
        self.assertTrue(self.debouncer.can_trigger(g, "toggle_mute"))
        
        # Frame 8: same stable gesture, should not trigger again (duplicate prevention)
        g, a = self.debouncer.add_frame("Fist", "Mute", 0.8)
        self.assertFalse(self.debouncer.can_trigger(g, "toggle_mute"))
        
        # Wait for cooldown (1.0 seconds) to expire
        time.sleep(1.05)
        
        # After cooldown, same gesture still shouldn't trigger if there was no transition
        # because of duplicate action prevention (must transition off Fist and back to it, or be a key)
        self.assertFalse(self.debouncer.can_trigger(g, "toggle_mute"))
        
        # Transition to None
        for _ in range(10):
            self.debouncer.add_frame("None", "None", 1.0)
            
        # Transition back to Fist
        for _ in range(6):
            self.debouncer.add_frame("Fist", "Mute", 0.8)
        g, a = self.debouncer.add_frame("Fist", "Mute", 0.8)
        
        # Now it is a new transition and past cooldown, so it should trigger
        self.assertTrue(self.debouncer.can_trigger(g, "toggle_mute"))

    def test_continuous_gestures_bypass_cooldown(self):
        """Verifies that continuous mouse gestures bypass cooldown and trigger checks."""
        # Index Point is in continuous_gestures
        for _ in range(6):
            self.debouncer.add_frame("Index Point", "Hover/Move Mouse", 0.8)
            
        # Becomes stable
        g, a = self.debouncer.add_frame("Index Point", "Hover/Move Mouse", 0.8)
        self.assertEqual(g, "Index Point")
        
        # Should be allowed to trigger continuously on every frame
        self.assertTrue(self.debouncer.can_trigger(g, "move_cursor"))
        self.assertTrue(self.debouncer.can_trigger(g, "move_cursor"))
        self.assertTrue(self.debouncer.can_trigger(g, "move_cursor"))

    def test_key_auto_repeat(self):
        """Verifies that key mappings auto-repeat after the 0.8 second interval."""
        # Fist mapped to key target (e.g., 'f5' in gaming)
        for _ in range(6):
            self.debouncer.add_frame("Fist", "Keypress", 0.8)
            
        g, a = self.debouncer.add_frame("Fist", "Keypress", 0.8)
        self.assertEqual(g, "Fist")
        
        # First trigger
        self.assertTrue(self.debouncer.can_trigger(g, "f5"))
        
        # Immediate next frame should not trigger
        self.assertFalse(self.debouncer.can_trigger(g, "f5"))
        
        # Wait for key repeat interval (0.8 seconds)
        time.sleep(0.85)
        
        # Should now allow repeat trigger even without transition
        self.assertTrue(self.debouncer.can_trigger(g, "f5"))

    def test_reset(self):
        """Verifies that resetting clears history and timers."""
        for _ in range(7):
            self.debouncer.add_frame("Fist", "Mute", 0.8)
        self.assertEqual(self.debouncer.add_frame("Fist", "Mute", 0.8)[0], "Fist")
        
        self.debouncer.reset()
        
        # After reset, Fist should not be stable
        g, a = self.debouncer.add_frame("Fist", "Mute", 0.8)
        self.assertEqual(g, "None")

if __name__ == "__main__":
    unittest.main()
