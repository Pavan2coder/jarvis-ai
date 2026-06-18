import os
import time
import shutil
import unittest
import threading
from typing import List

from brain.conversation_memory import (
    ThreadSafeConversationMemory,
    JSONFileStorageBackend,
    InMemoryStorageBackend
)

class TestConversationMemory(unittest.TestCase):
    
    def setUp(self) -> None:
        self.test_dir = "test_brain_output"
        os.makedirs(self.test_dir, exist_ok=True)
        self.json_path = os.path.join(self.test_dir, "test_chat_history.json")
        
    def tearDown(self) -> None:
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
            
    def test_basic_in_memory_operations(self) -> None:
        """Verifies append, length, clear, iteration, indexing, and slicing."""
        mem = ThreadSafeConversationMemory()
        
        # Initial empty check
        self.assertEqual(len(mem), 0)
        
        # Append
        mem.append({"role": "user", "text": "Hello"})
        mem.append({"role": "model", "text": "Hi there"})
        
        self.assertEqual(len(mem), 2)
        self.assertEqual(mem[0]["role"], "user")
        self.assertEqual(mem[1]["text"], "Hi there")
        
        # Slice compatibility
        sliced = mem[-1:]
        self.assertEqual(len(sliced), 1)
        self.assertEqual(sliced[0]["role"], "model")
        
        # Iterable compatibility
        items = list(mem)
        self.assertEqual(len(items), 2)
        
        # Clear
        mem.clear()
        self.assertEqual(len(mem), 0)
        
    def test_max_history_capping(self) -> None:
        """Verifies that setting max_history prunes older entries correctly."""
        mem = ThreadSafeConversationMemory(max_history=3)
        for i in range(5):
            mem.append({"role": "user", "text": f"Msg {i}"})
            
        self.assertEqual(len(mem), 3)
        self.assertEqual(mem[0]["text"], "Msg 2")
        self.assertEqual(mem[2]["text"], "Msg 4")
        
    def test_json_persistence(self) -> None:
        """Verifies JSON backend writes to disk and can reload the state on init."""
        backend = JSONFileStorageBackend(self.json_path)
        mem = ThreadSafeConversationMemory(backend=backend)
        
        mem.append({"role": "user", "text": "Persist this please"})
        mem.append({"role": "model", "text": "Saved!"})
        
        # Confirm file exists and is populated
        self.assertTrue(os.path.exists(self.json_path))
        with open(self.json_path, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("Persist this please", content)
            
        # Re-initialize new memory with same backend
        new_backend = JSONFileStorageBackend(self.json_path)
        new_mem = ThreadSafeConversationMemory(backend=new_backend)
        
        self.assertEqual(len(new_mem), 2)
        self.assertEqual(new_mem[0]["text"], "Persist this please")
        
    def test_concurrency_stress(self) -> None:
        """Spawns concurrent writers and readers to stress-test synchronization."""
        mem = ThreadSafeConversationMemory(max_history=50)
        
        num_writers = 10
        num_readers = 10
        ops_per_thread = 100
        
        errors: List[Exception] = []
        
        def writer_job(thread_id: int):
            try:
                for i in range(ops_per_thread):
                    mem.append({"role": "user", "text": f"Thread {thread_id} - msg {i}"})
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)
                
        def reader_job():
            try:
                for _ in range(ops_per_thread * 2):
                    # Concurrent read operations (len, slice, list-copy, iteration)
                    _ = len(mem)
                    _ = mem[-5:]
                    _ = list(mem)
                    for turn in mem:
                        _ = turn["role"]
                    time.sleep(0.0005)
            except Exception as e:
                errors.append(e)
                
        # Start threads
        threads = []
        for i in range(num_writers):
            t = threading.Thread(target=writer_job, args=(i,))
            threads.append(t)
            t.start()
            
        for _ in range(num_readers):
            t = threading.Thread(target=reader_job)
            threads.append(t)
            t.start()
            
        # Join threads
        for t in threads:
            t.join()
            
        # Check if any exception was raised in threads
        self.assertEqual(len(errors), 0, f"Exceptions occurred during concurrent stress: {errors}")
        self.assertGreater(len(mem), 0)

if __name__ == "__main__":
    unittest.main()
