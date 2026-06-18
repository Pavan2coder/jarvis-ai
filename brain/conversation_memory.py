"""
Conversation Memory Module for Jarvis OS.
Provides thread-safe storage for chat history to prevent race conditions
when accessed by multiple background threads (e.g., UI, gestures, web sockets).

Architecture & Locking Strategy:
--------------------------------
1. Reentrant Lock (RLock):
   We use threading.RLock() to serialize read/write access to the conversation memory.
   Unlike threading.Lock(), an RLock can be acquired multiple times by the same thread 
   without causing a deadlock. This is critical for internal methods that call other locked 
   methods (e.g., extend() calling append()).

2. Pluggable Storage Backends:
   The storage layer is abstracted behind BaseStorageBackend. Concrete implementations include:
   - InMemoryStorageBackend: Default backend; high-speed in-memory list.
   - JSONFileStorageBackend: Persists the conversation history to a local JSON file.

3. Thread-Safe List Compatibility:
   To ensure minimal changes to existing codebase, ThreadSafeConversationMemory implements
   __getitem__, __len__, __iter__, and append.
   - Reads (e.g. slicing, iteration) make copies of the elements so that subsequent usage/iteration
     by a thread is isolated and does not raise "dictionary changed size during iteration" or other 
     race condition errors.

Integration Example:
--------------------
from brain.conversation_memory import ThreadSafeConversationMemory, JSONFileStorageBackend

# In-memory storage (default):
chat_history = ThreadSafeConversationMemory()

# Persistent JSON storage:
backend = JSONFileStorageBackend("data/chat_history.json")
chat_history = ThreadSafeConversationMemory(backend=backend)

# Thread-safe operations:
chat_history.append({"role": "user", "text": "Hello Jarvis"})
print(len(chat_history))
recent_turns = chat_history[-8:]  # Returns a copy of the last 8 items
"""

import os
import json
import threading
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Union

class BaseStorageBackend(ABC):
    """Abstract base class for conversation memory storage backends."""
    
    @abstractmethod
    def load(self) -> List[Dict[str, Any]]:
        """Loads and returns the conversation history."""
        pass
        
    @abstractmethod
    def save(self, history: List[Dict[str, Any]]) -> None:
        """Saves the conversation history."""
        pass


class InMemoryStorageBackend(BaseStorageBackend):
    """Default high-performance in-memory storage backend."""
    
    def __init__(self) -> None:
        self._store: List[Dict[str, Any]] = []
        
    def load(self) -> List[Dict[str, Any]]:
        return self._store.copy()
        
    def save(self, history: List[Dict[str, Any]]) -> None:
        self._store = [dict(msg) for msg in history]


class JSONFileStorageBackend(BaseStorageBackend):
    """File-based persistent storage backend using JSON."""
    
    def __init__(self, filepath: str) -> None:
        self.filepath = filepath
        self._lock = threading.Lock()  # Additional lock specifically for file I/O safety
        
    def load(self) -> List[Dict[str, Any]]:
        with self._lock:
            if not os.path.exists(self.filepath):
                return []
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
                    return []
            except (json.JSONDecodeError, IOError) as e:
                # Log or handle corruption gracefully. Return empty list for safety.
                print(f"⚠️ Warning: Failed to load conversation history from {self.filepath}: {e}")
                return []
                
    def save(self, history: List[Dict[str, Any]]) -> None:
        with self._lock:
            temp_filepath = self.filepath + ".tmp"
            try:
                # Ensure the parent directory exists
                parent_dir = os.path.dirname(self.filepath)
                if parent_dir and not os.path.exists(parent_dir):
                    os.makedirs(parent_dir, exist_ok=True)
                
                # Write to temp file first to prevent corruption on crash
                with open(temp_filepath, "w", encoding="utf-8") as f:
                    json.dump(history, f, indent=2, ensure_ascii=False)
                
                # Atomic rename / replace
                if os.path.exists(self.filepath):
                    os.replace(temp_filepath, self.filepath)
                else:
                    os.rename(temp_filepath, self.filepath)
            except IOError as e:
                print(f"⚠️ Error: Failed to save conversation history to {self.filepath}: {e}")
                if os.path.exists(temp_filepath):
                    try:
                        os.remove(temp_filepath)
                    except OSError:
                        pass


class ThreadSafeConversationMemory:
    """Thread-safe, lock-synchronized wrapper around conversation storage.
    
    Supports list-like operations for drop-in compatibility with existing code.
    """
    
    def __init__(self, max_history: int = None, backend: BaseStorageBackend = None) -> None:
        self._lock = threading.RLock()
        self.max_history = max_history
        self._backend = backend if backend is not None else InMemoryStorageBackend()
        
        # Load initial state from backend
        self._history = self._backend.load()
        
    def append(self, message: Dict[str, Any]) -> None:
        """Thread-safe append of a chat message to history."""
        if not isinstance(message, dict) or "role" not in message or "text" not in message:
            raise ValueError("Message must be a dictionary with 'role' and 'text' keys")
            
        with self._lock:
            # Append a clean copy to prevent reference leakage
            self._history.append({
                "role": str(message["role"]),
                "text": str(message["text"])
            })
            
            # Prune if max_history is specified
            if self.max_history is not None and len(self._history) > self.max_history:
                self._history = self._history[-self.max_history:]
                
            self._backend.save(self._history)
            
    def extend(self, messages: List[Dict[str, Any]]) -> None:
        """Thread-safe append of multiple messages."""
        with self._lock:
            for message in messages:
                self.append(message)
                
    def clear(self) -> None:
        """Thread-safe clear of all history."""
        with self._lock:
            self._history.clear()
            self._backend.save(self._history)
            
    def get_history(self, limit: int = None) -> List[Dict[str, Any]]:
        """Returns a thread-safe copy of the history, optionally limited to the last N turns."""
        with self._lock:
            items = self._history if limit is None else self._history[-limit:]
            return [dict(item) for item in items]
            
    def __len__(self) -> int:
        with self._lock:
            return len(self._history)
            
    def __getitem__(self, index: Union[int, slice]) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        with self._lock:
            if isinstance(index, slice):
                # Return a list of copies for safety
                return [dict(item) for item in self._history[index]]
            return dict(self._history[index])
            
    def __iter__(self):
        """Returns an iterator over a copy of the current list to prevent concurrent modification errors."""
        with self._lock:
            copied_list = [dict(item) for item in self._history]
        return iter(copied_list)
        
    def __repr__(self) -> str:
        with self._lock:
            return f"ThreadSafeConversationMemory(length={len(self._history)}, backend={self._backend.__class__.__name__})"
