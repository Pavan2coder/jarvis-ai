import unittest
from backend.assistant.intent_classifier import classify_intent

class TestIntentClassifierGestures(unittest.TestCase):
    def test_enable_gestures_intents(self):
        """Verifies that various enable gestures commands classify correctly."""
        enable_cases = [
            "start gesture control",
            "enable gestures",
            "turn on camera",
            "activate gestures",
            "start gestures",
            "enable gesture mode",
            "turn on gesture control"
        ]
        for command in enable_cases:
            result = classify_intent(command)
            self.assertEqual(result["intent"], "enable_gestures", f"Failed for: {command}")
            self.assertTrue(result["confidence"] >= 0.90)

    def test_disable_gestures_intents(self):
        """Verifies that various disable gestures commands classify correctly."""
        disable_cases = [
            "stop gesture control",
            "disable gestures",
            "turn off gesture mode",
            "turn off camera",
            "deactivate gestures",
            "stop gestures",
            "disable gesture control",
            "top gesture control"
        ]
        for command in disable_cases:
            result = classify_intent(command)
            self.assertEqual(result["intent"], "disable_gestures", f"Failed for: {command}")
            self.assertTrue(result["confidence"] >= 0.80)

    def test_substring_conflict_prevention(self):
        """Verifies that substring matches like 'on' in 'control' do not misclassify."""
        # This was the core bug: 'stop gesture control' contained 'on' (inside 'control')
        # and got misclassified as 'enable_gestures'
        result = classify_intent("stop gesture control")
        self.assertEqual(result["intent"], "disable_gestures")
        
        # 'volume on' should not trigger gesture intents (no gesture keyword)
        result = classify_intent("volume on")
        self.assertEqual(result["intent"], "system_control")

    def test_contradictory_commands_prevention(self):
        """Verifies that conflicting intents in a single command are rejected."""
        contradictory_cases = [
            "start and stop gesture control",
            "enable and disable gestures",
            "turn on and turn off camera",
            "activate and deactivate gestures"
        ]
        for command in contradictory_cases:
            result = classify_intent(command)
            self.assertNotEqual(result["intent"], "enable_gestures", f"Failed conflict check for: {command}")
            self.assertNotEqual(result["intent"], "disable_gestures", f"Failed conflict check for: {command}")

if __name__ == "__main__":
    unittest.main()
