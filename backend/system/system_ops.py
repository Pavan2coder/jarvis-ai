import os
import time
import subprocess

from backend.core import config


def launch_app(name):
    """Open an app by friendly name, falling back to launching the raw name."""
    name = name.strip().lower()
    target = config.APPS.get(name)
    try:
        if target is None:
            # Unknown app — try launching whatever they said via the shell
            target = name
        if target.startswith("http://") or target.startswith("https://") or target.startswith("www."):
            import webbrowser
            url = target if not target.startswith("www.") else "https://" + target
            webbrowser.open(url)
            return True
        elif target.endswith(":"):                 # URI like ms-settings:
            os.startfile(target)
        else:
            # 'start' resolves apps on PATH and registered App Paths
            subprocess.Popen(["cmd", "/c", "start", "", target], shell=False)
        return True
    except Exception as e:
        print(f"  ⚠️  App launch error: {e}")
        return False

def kill_processes(image_names):
    """taskkill one or more process images. Returns True if anything was killed."""
    killed = False
    for img in image_names:
        try:
            r = subprocess.run(["taskkill", "/f", "/im", img],
                               capture_output=True, text=True)
            # returncode 0 = killed; 128 = not running
            if r.returncode == 0:
                killed = True
        except Exception as e:
            print(f"  ⚠️  Close error for {img}: {e}")
    return killed

def close_active_browser_tab():
    """Close whatever browser tab is currently focused (Ctrl+W)."""
    try:
        import pyautogui
        pyautogui.hotkey("ctrl", "w")
        return True
    except Exception:
        return False

def set_volume_percent(pct):
    """Set master volume 0-100 using pycaw if available."""
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        vol = cast(interface, POINTER(IAudioEndpointVolume))
        vol.SetMasterVolumeLevelScalar(max(0.0, min(1.0, pct / 100.0)), None)
        return True
    except Exception:
        return False

def set_brightness_percent(pct):
    try:
        import screen_brightness_control as sbc
        sbc.set_brightness(max(0, min(100, int(pct))))
        return True
    except Exception:
        return False

def battery_status():
    try:
        import psutil
        b = psutil.sensors_battery()
        if b is None:
            return "I couldn't read the battery — this might be a desktop."
        plugged = "charging" if b.power_plugged else "on battery"
        return f"Battery is at {int(b.percent)} percent, {plugged}."
    except ImportError:
        return "Install psutil for battery info. Run pip install psutil."
    except Exception:
        return "I couldn't read the battery status."

def gpu_status():
    """GPU load + memory. Tries GPUtil, then nvidia-smi (NVIDIA only)."""
    # 1) GPUtil — works for NVIDIA if installed
    try:
        import GPUtil
        gpus = GPUtil.getGPUs()
        if gpus:
            g = gpus[0]
            return (f"GPU {g.name} is at {int(g.load * 100)} percent load, "
                    f"using {int(g.memoryUsed)} of {int(g.memoryTotal)} megabytes of video memory, "
                    f"at {int(g.temperature)} degrees.")
    except Exception:
        pass
    # 2) nvidia-smi — present with any NVIDIA driver, no extra package
    try:
        out = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=8)
        if out.returncode == 0 and out.stdout.strip():
            load, used, total, temp = [x.strip() for x in out.stdout.strip().splitlines()[0].split(",")]
            return (f"GPU is at {load} percent load, using {used} of {total} "
                    f"megabytes of video memory, at {temp} degrees.")
    except Exception:
        pass
    return ("I couldn't read the GPU. For NVIDIA cards install GPUtil "
            "with pip install gputil, or make sure nvidia-smi is available.")

def system_stats_report(command):
    """Build a spoken report for whichever of CPU / memory / GPU was asked.
    If none is named specifically (e.g. 'system info'), report all of them."""
    try:
        import psutil
    except ImportError:
        return "Install psutil for system stats. Run pip install psutil."

    wants_cpu = any(w in command for w in ["cpu", "processor"])
    wants_mem = any(w in command for w in ["memory", "ram"])
    wants_gpu = any(w in command for w in ["gpu", "graphics", "video card"])
    # "system info", "how much is being used", etc. → everything
    if not (wants_cpu or wants_mem or wants_gpu):
        wants_cpu = wants_mem = wants_gpu = True

    parts = []
    if wants_cpu:
        parts.append(f"CPU is at {psutil.cpu_percent(interval=1)} percent")
    if wants_mem:
        m = psutil.virtual_memory()
        used_gb  = m.used  / (1024 ** 3)
        total_gb = m.total / (1024 ** 3)
        parts.append(f"memory is at {m.percent} percent, "
                     f"{used_gb:.1f} of {total_gb:.1f} gigabytes used")
    if wants_gpu:
        parts.append(gpu_status())

    return ". ".join(parts) + "."

# Live numeric stats for the HUD gauges (cached GPU so we don't spawn
# nvidia-smi on every poll).
_gpu_cache = {"t": 0.0, "data": {"gpu": None, "gpu_mem_used": None, "gpu_mem_total": None}}

def _gpu_numeric():
    now = time.time()
    if now - _gpu_cache["t"] < 3.0:
        return _gpu_cache["data"]
    data = {"gpu": None, "gpu_mem_used": None, "gpu_mem_total": None}
    try:
        import GPUtil
        gpus = GPUtil.getGPUs()
        if gpus:
            g = gpus[0]
            data = {"gpu": round(g.load * 100), "gpu_mem_used": round(g.memoryUsed),
                    "gpu_mem_total": round(g.memoryTotal)}
    except Exception:
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=6)
            if out.returncode == 0 and out.stdout.strip():
                load, used, total = [x.strip() for x in out.stdout.strip().splitlines()[0].split(",")]
                data = {"gpu": int(load), "gpu_mem_used": int(used), "gpu_mem_total": int(total)}
        except Exception:
            pass
    _gpu_cache["t"], _gpu_cache["data"] = now, data
    return data

def get_live_stats():
    """Real CPU / RAM / GPU / battery numbers for the HUD gauges."""
    stats = {"cpu": None, "ram": None, "ram_used": None, "ram_total": None,
             "battery": None, "gpu": None, "gpu_mem_used": None, "gpu_mem_total": None}
    try:
        import psutil
        stats["cpu"] = psutil.cpu_percent(interval=None)   # non-blocking
        m = psutil.virtual_memory()
        stats["ram"]       = m.percent
        stats["ram_used"]  = round(m.used  / (1024 ** 3), 1)
        stats["ram_total"] = round(m.total / (1024 ** 3), 1)
        b = psutil.sensors_battery()
        if b is not None:
            stats["battery"] = int(b.percent)
    except Exception:
        pass
    stats.update(_gpu_numeric())
    return stats
