import unittest
from core.shutdown_manager import ShutdownManager

class TestShutdownManager(unittest.TestCase):
    
    def test_handler_registration_and_sorting(self) -> None:
        """Verifies handlers are registered and sorted by priority."""
        mgr = ShutdownManager()
        
        # Register in unsorted order
        calls = []
        mgr.register_handler("persistence", lambda: calls.append("persist"), priority=40)
        mgr.register_handler("sockets", lambda: calls.append("sockets"), priority=20)
        mgr.register_handler("worker", lambda: calls.append("worker"), priority=10)
        mgr.register_handler("audio", lambda: calls.append("audio"), priority=30)
        
        # Verify internal sorting
        self.assertEqual(len(mgr._handlers), 4)
        self.assertEqual(mgr._handlers[0][1], "worker")
        self.assertEqual(mgr._handlers[1][1], "sockets")
        self.assertEqual(mgr._handlers[2][1], "audio")
        self.assertEqual(mgr._handlers[3][1], "persistence")
        
    def test_shutdown_execution_order_and_idempotency(self) -> None:
        """Verifies callbacks execute in ascending priority order and run exactly once."""
        mgr = ShutdownManager()
        mgr._bypass_exit = True
        
        execution_order = []
        
        def step_1():
            execution_order.append("step_1")
            
        def step_2():
            execution_order.append("step_2")
            
        def step_3():
            execution_order.append("step_3")
            
        mgr.register_handler("third", step_3, priority=30)
        mgr.register_handler("first", step_1, priority=10)
        mgr.register_handler("second", step_2, priority=20)
        
        # Initiate first time
        self.assertFalse(mgr.is_shutting_down())
        mgr.initiate_shutdown(0)
        self.assertTrue(mgr.is_shutting_down())
        
        # Check order
        self.assertEqual(execution_order, ["step_1", "step_2", "step_3"])
        
        # Attempt to run a second time (should do nothing due to idempotency)
        mgr.initiate_shutdown(0)
        self.assertEqual(execution_order, ["step_1", "step_2", "step_3"])
        
    def test_exception_isolation(self) -> None:
        """Verifies that an exception in one handler does not halt subsequent handlers."""
        mgr = ShutdownManager()
        mgr._bypass_exit = True
        
        executed = []
        
        def crashing_step():
            raise RuntimeError("Boom!")
            
        def safe_step():
            executed.append("safe")
            
        mgr.register_handler("crasher", crashing_step, priority=10)
        mgr.register_handler("safe", safe_step, priority=20)
        
        mgr.initiate_shutdown(0)
        
        # Confirm that the second handler still ran successfully
        self.assertEqual(executed, ["safe"])

if __name__ == "__main__":
    unittest.main()
