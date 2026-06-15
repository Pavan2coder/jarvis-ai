import unittest
import time
from backend.vision.gesture_state import GestureStateManager, GestureState

class TestGestureStateManager(unittest.TestCase):
    def setUp(self):
        self.manager = GestureStateManager()
        self.manager.reset()

    def test_singleton(self):
        """Verifies that the state manager is a singleton."""
        another_manager = GestureStateManager()
        self.assertIs(self.manager, another_manager)

    def test_valid_transitions(self):
        """Verifies correct execution of valid transition paths."""
        self.assertEqual(self.manager.get_state(), GestureState.STOPPED)
        
        # STOPPED -> STARTING
        self.assertTrue(self.manager.transition_to(GestureState.STARTING))
        self.assertEqual(self.manager.get_state(), GestureState.STARTING)
        
        # STARTING -> RUNNING
        self.assertTrue(self.manager.transition_to(GestureState.RUNNING))
        self.assertEqual(self.manager.get_state(), GestureState.RUNNING)
        
        # RUNNING -> PAUSED
        self.assertTrue(self.manager.transition_to(GestureState.PAUSED))
        self.assertEqual(self.manager.get_state(), GestureState.PAUSED)
        
        # PAUSED -> RUNNING
        self.assertTrue(self.manager.transition_to(GestureState.RUNNING))
        self.assertEqual(self.manager.get_state(), GestureState.RUNNING)
        
        # RUNNING -> STOPPED
        self.assertTrue(self.manager.transition_to(GestureState.STOPPED))
        self.assertEqual(self.manager.get_state(), GestureState.STOPPED)

    def test_invalid_transitions(self):
        """Verifies invalid transitions are rejected."""
        self.assertEqual(self.manager.get_state(), GestureState.STOPPED)
        
        # Cannot go STOPPED -> RUNNING directly
        self.assertFalse(self.manager.transition_to(GestureState.RUNNING))
        self.assertEqual(self.manager.get_state(), GestureState.STOPPED)
        
        # Cannot go STOPPED -> PAUSED directly
        self.assertFalse(self.manager.transition_to(GestureState.PAUSED))
        
        # Move to STARTING
        self.assertTrue(self.manager.transition_to(GestureState.STARTING))
        # Cannot go STARTING -> PAUSED directly
        self.assertFalse(self.manager.transition_to(GestureState.PAUSED))

    def test_duplicate_instance_prevention(self):
        """Verifies duplicate startup instances are correctly identified."""
        self.assertEqual(self.manager.get_state(), GestureState.STOPPED)
        self.assertFalse(self.manager.prevent_duplicate_instances())
        
        self.manager.transition_to(GestureState.STARTING)
        self.assertTrue(self.manager.prevent_duplicate_instances())
        
        self.manager.transition_to(GestureState.RUNNING)
        self.assertTrue(self.manager.prevent_duplicate_instances())
        
        self.manager.transition_to(GestureState.STOPPED)
        self.assertFalse(self.manager.prevent_duplicate_instances())

    def test_error_and_recovery(self):
        """Verifies transitioning to ERROR state and trigger automatic recovery loops."""
        # STOPPED -> STARTING -> RUNNING
        self.manager.transition_to(GestureState.STARTING)
        self.manager.transition_to(GestureState.RUNNING)
        
        # RUNNING -> ERROR
        error_msg = "Camera lost connection"
        self.assertTrue(self.manager.transition_to(GestureState.ERROR, error_msg))
        self.assertEqual(self.manager.get_state(), GestureState.ERROR)
        
        report = self.manager.get_status_report()
        self.assertEqual(report["last_error"], error_msg)
        self.assertIsNotNone(report["error_timestamp"])
        
        # Verify recovery callback execution
        callback_called = False
        def mock_starter():
            nonlocal callback_called
            callback_called = True
            return True
            
        success = self.manager.recover(mock_starter)
        self.assertTrue(success)
        self.assertTrue(callback_called)
        # Should now be in STARTING state (as set by recovery loop before calling callback,
        # note: the callback itself would transition it to RUNNING in actual integration)
        self.assertEqual(self.manager.get_state(), GestureState.STARTING)

    def test_status_reporting(self):
        """Verifies the completeness of the status report structure."""
        self.manager.transition_to(GestureState.STARTING)
        self.manager.increment_frame_count()
        self.manager.increment_frame_count()
        
        report = self.manager.get_status_report()
        self.assertEqual(report["state"], GestureState.STARTING.value)
        self.assertEqual(report["frames_processed"], 2)
        self.assertTrue(report["uptime"] >= 0.0)
        self.assertIn("active_profile", report)

if __name__ == "__main__":
    unittest.main()
