"""
Thread-safe progress reporter.

The FastAPI background thread sets a callback before calling run_pipeline_with_params().
Pipeline nodes call report() to push message + percentage updates through that callback.
Only one pipeline runs at a time in the current single-server deployment so a single
module-level callback is safe.
"""
import threading

_lock = threading.Lock()
_cb = None


def set_callback(cb) -> None:
    global _cb
    with _lock:
        _cb = cb


def clear_callback() -> None:
    global _cb
    with _lock:
        _cb = None


def report(message: str, progress: int) -> None:
    with _lock:
        cb = _cb
    if cb:
        try:
            cb(message, max(0, min(100, progress)))
        except Exception:
            pass
