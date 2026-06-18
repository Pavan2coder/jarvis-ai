import unittest
import threading
import time
from typing import List, Dict, Any
from ui.state_manager import UIStateManager

class TestUIStateManager(unittest.TestCase):

    def test_single_thread_updates_and_snapshots(self):
        manager = UIStateManager()
        
        # Test default states
        snapshot = manager.get_snapshot()
        self.assertEqual(snapshot["status"], "idle")
        self.assertEqual(snapshot["message"], "Standing by...")
        
        # Test update state
        new_snap = manager.update_state(status="listening", message="Listening closely...")
        self.assertEqual(new_snap["status"], "listening")
        self.assertEqual(new_snap["message"], "Listening closely...")
        
        # Test snapshot persistence
        snapshot2 = manager.get_snapshot()
        self.assertEqual(snapshot2["status"], "listening")
        
        # Test blank message keeps old message
        manager.update_state(status="thinking", message="")
        self.assertEqual(manager.get_snapshot()["message"], "Listening closely...")
        self.assertEqual(manager.get_snapshot()["status"], "thinking")

    def test_custom_fields_via_kwargs(self):
        manager = UIStateManager()
        manager.update_state(status="speaking", gesture_active=True, cpu_load=45.2)
        snapshot = manager.get_snapshot()
        self.assertEqual(snapshot["status"], "speaking")
        self.assertEqual(snapshot["gesture_active"], True)
        self.assertEqual(snapshot["cpu_load"], 45.2)

    def test_subscription_and_unsubscription(self):
        manager = UIStateManager()
        received_snapshots: List[Dict[str, Any]] = []

        def listener(snapshot: Dict[str, Any]):
            received_snapshots.append(snapshot)

        # Register listener
        unsubscribe = manager.subscribe(listener)
        
        manager.update_state(status="listening")
        self.assertEqual(len(received_snapshots), 1)
        self.assertEqual(received_snapshots[0]["status"], "listening")
        
        # Unsubscribe
        unsubscribe()
        manager.update_state(status="thinking")
        
        # Callback should NOT be invoked after unsubscribe
        self.assertEqual(len(received_snapshots), 1)

    def test_diagnostics_telemetry(self):
        manager = UIStateManager()
        
        # Reset counters (just to test clean counts)
        manager._reads = 0
        manager._writes = 0
        
        manager.get_snapshot()
        manager.get_snapshot()
        manager.update_state(status="speaking")
        
        diag = manager.get_diagnostics()
        self.assertEqual(diag["reads"], 2)
        self.assertEqual(diag["writes"], 1)
        self.assertGreaterEqual(diag["total_lock_wait_time_ms"], 0.0)
        self.assertGreaterEqual(diag["avg_lock_wait_time_ms"], 0.0)

    def test_multithreading_safety(self):
        manager = UIStateManager()
        num_threads = 20
        iterations = 100
        
        errors = []

        def worker_task(thread_id: int):
            try:
                for i in range(iterations):
                    # Write
                    manager.update_state(
                        status="active",
                        message=f"Msg from thread {thread_id}",
                        cmd_val=i,
                        thread_owner=thread_id
                    )
                    # Read
                    snap = manager.get_snapshot()
                    self.assertEqual(snap["status"], "active")
                    # Quick sleep to yield thread
                    time.sleep(0.0001)
            except Exception as e:
                errors.append(e)

        threads = []
        for t_idx in range(num_threads):
            t = threading.Thread(target=worker_task, args=(t_idx,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Assert no errors occurred during concurrency stress test
        self.assertEqual(len(errors), 0, f"Concurrent execution errors: {errors}")
        
        # Verify final state is readable and diagnostics are correctly captured
        diag = manager.get_diagnostics()
        self.assertEqual(diag["writes"], num_threads * iterations)
        self.assertEqual(diag["reads"], num_threads * iterations)


if __name__ == '__main__':
    unittest.main()
