"""PID file lock for FR monitors.

Prevents overlapping monitor instances caused by watchdog restart races.
Uses fcntl.flock (advisory, cross-Unix); stale lock files are detected via
pid-alive check.

Usage (add near top of each monitor's main()):
    from _monitor_lock import acquire_lock
    acquire_lock("fr_monitor")   # exits with code 0 if already running
"""
import atexit
import errno
import fcntl
import os
import sys
from pathlib import Path

LOCK_DIR = Path(__file__).parent / "data_cache" / ".locks"


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError as e:
        return e.errno != errno.ESRCH


def acquire_lock(name: str) -> None:
    """Acquire exclusive lock for monitor `name`. Exit silently if held."""
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = LOCK_DIR / f"{name}.pid"

    # Check stale lock
    if lock_path.exists():
        try:
            old_pid = int(lock_path.read_text().strip())
            if _pid_alive(old_pid) and old_pid != os.getpid():
                print(f"[lock] {name}: already running as pid={old_pid}; exiting")
                sys.exit(0)
        except (ValueError, OSError):
            pass  # stale, will overwrite

    f = open(lock_path, "w")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(f"[lock] {name}: another instance holds the lock; exiting")
        sys.exit(0)
    f.write(str(os.getpid()))
    f.flush()

    def _release():
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            f.close()
            if lock_path.exists():
                lock_path.unlink()
        except OSError:
            pass

    atexit.register(_release)
