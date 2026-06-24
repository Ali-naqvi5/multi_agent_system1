
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
