import itertools
import sys
import threading
import time
from contextlib import contextmanager

_CHARS = "|/-\\"


@contextmanager
def spinner(message: str):
    """Display a rotating spinner on stderr while the body executes.
    Falls back to a plain start/done line when stderr is not a TTY."""
    if not sys.stderr.isatty():
        yield
        return

    stop = threading.Event()

    def _spin():
        for char in itertools.cycle(_CHARS):
            if stop.is_set():
                break
            sys.stderr.write(f"\r{message} {char} ")
            sys.stderr.flush()
            time.sleep(0.1)
        sys.stderr.write(f"\r{' ' * (len(message) + 3)}\r")
        sys.stderr.flush()

    t = threading.Thread(target=_spin, daemon=True)
    t.start()
    try:
        yield
    finally:
        stop.set()
        t.join()
