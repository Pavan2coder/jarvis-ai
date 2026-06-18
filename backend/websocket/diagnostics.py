import asyncio
import time
from typing import Dict, Any
from backend.websocket.events import dispatcher, JarvisEvent, JarvisEventType
from backend.system.system_ops import get_live_stats
from backend.utils import logger
from core.shutdown_manager import shutdown_manager

# Store previous network stats to calculate throughput (KB/s)
_net_io_cache = {"t": time.time(), "sent": 0, "recv": 0}

def get_network_speeds() -> Dict[str, float]:
    """Calculates network send/receive speed in KB/s using psutil."""
    import psutil
    try:
        counters = psutil.net_io_counters()
        now = time.time()
        dt = now - _net_io_cache["t"]
        
        # Guard against division by zero or negative time deltas
        if dt <= 0:
            return {"sent_speed": 0.0, "recv_speed": 0.0}
            
        sent_speed = (counters.bytes_sent - _net_io_cache["sent"]) / dt
        recv_speed = (counters.bytes_recv - _net_io_cache["recv"]) / dt
        
        # Update cache
        _net_io_cache["t"] = now
        _net_io_cache["sent"] = counters.bytes_sent
        _net_io_cache["recv"] = counters.bytes_recv
        
        return {
            "sent_speed": round(sent_speed / 1024, 1),  # KB/s
            "recv_speed": round(recv_speed / 1024, 1)   # KB/s
        }
    except Exception as e:
        logger.error(f"Error gathering network statistics: {e}")
        return {"sent_speed": 0.0, "recv_speed": 0.0}

def gather_diagnostics() -> Dict[str, Any]:
    """Blocking OS calls consolidated to run safely in a background thread."""
    stats = get_live_stats()
    network = get_network_speeds()
    stats["network"] = network
    return stats

async def start_diagnostics_streamer():
    """Asynchronous loop streaming system diagnostics every second."""
    logger.info("Initializing Jarvis OS diagnostics streaming worker...")
    
    # Initialize network cache baseline
    try:
        import psutil
        counters = psutil.net_io_counters()
        _net_io_cache["sent"] = counters.bytes_sent
        _net_io_cache["recv"] = counters.bytes_recv
    except Exception:
        pass

    while not shutdown_manager.is_shutting_down():
        try:
            # PERFORMANCE OPTIMIZATION:
            # Run the blocking OS calls in a thread pool executor to prevent blocking
            # the main event loop thread and keep FastAPI responsive.
            data = await asyncio.to_thread(gather_diagnostics)
            
            # Emit the diagnostics event
            event = JarvisEvent(JarvisEventType.DIAGNOSTICS_UPDATE, data=data)
            await dispatcher.emit(event)
        except Exception as e:
            logger.error(f"Error in diagnostics streamer loop: {e}")
        
        await asyncio.sleep(1.0)
