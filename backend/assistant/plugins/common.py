"""Shared helpers used by more than one command plugin."""

import os
import sys
import subprocess


def open_folder(path) -> bool:
    """Open a filesystem path in the OS file explorer. Returns True on success."""
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception as e:
        print(f"  ⚠️  Folder error: {e}")
        return False
