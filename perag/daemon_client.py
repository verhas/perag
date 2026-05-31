"""Client-side utilities for the embedding daemon."""

import json
import os
import socket
import sys
from pathlib import Path
from typing import Callable, Optional


def _cleanup_stale(perag_dir: Path) -> None:
    for name in ("embed.pid", "embed.sock"):
        try:
            (perag_dir / name).unlink(missing_ok=True)
        except Exception:
            pass


def _is_alive(perag_dir: Path) -> Optional[int]:
    """Return PID if daemon process is running, None otherwise."""
    pid_path = perag_dir / "embed.pid"
    if not pid_path.exists():
        return None
    try:
        pid = int(pid_path.read_text().strip())
        os.kill(pid, 0)
        return pid
    except (ProcessLookupError, PermissionError, ValueError, OSError):
        return None


def _kill(pid: int) -> None:
    try:
        import signal as _signal
        os.kill(pid, _signal.SIGTERM)
    except Exception:
        try:
            os.kill(pid, 9)
        except Exception:
            pass


def _start_background(perag_dir: Path, model: str, batch_size: int, idle_timeout: int) -> None:
    import subprocess
    cmd = [
        sys.executable, "-m", "perag.embed_daemon",
        str(perag_dir), model, str(batch_size), str(idle_timeout),
    ]
    kwargs: dict = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, **kwargs)


def _try_start(perag_dir: Path, model: str, batch_size: int, idle_timeout: int) -> None:
    """Start daemon with a lock file to prevent race conditions."""
    lock_path = perag_dir / "embed.lock"
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except FileExistsError:
        return
    try:
        _start_background(perag_dir, model, batch_size, idle_timeout)
    finally:
        try:
            lock_path.unlink(missing_ok=True)
        except Exception:
            pass


def _recv_line(sock: socket.socket) -> bytes:
    data = b""
    while b"\n" not in data:
        chunk = sock.recv(1 << 20)
        if not chunk:
            raise ConnectionError("daemon closed connection")
        data += chunk
    return data.rstrip(b"\n")


def try_embed(
    perag_dir: Path,
    model: str,
    batch_size: int,
    ack_timeout: int,
    idle_timeout: int,
    texts: list[str],
    warn: Callable[[str], None],
) -> Optional[list[list[float]]]:
    """Try to embed via the daemon. Returns vectors or None — caller falls back to in-process."""
    if not hasattr(socket, "AF_UNIX"):
        return None

    from perag.embed_daemon import config_fingerprint
    fingerprint = config_fingerprint(model, batch_size)
    sock_path = perag_dir / "embed.sock"

    pid = _is_alive(perag_dir)
    if pid is None:
        _cleanup_stale(perag_dir)
        _try_start(perag_dir, model, batch_size, idle_timeout)
        return None

    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(str(sock_path))
    except (ConnectionRefusedError, FileNotFoundError, OSError):
        _cleanup_stale(perag_dir)
        _try_start(perag_dir, model, batch_size, idle_timeout)
        return None

    try:
        request = json.dumps({"texts": texts, "config_fingerprint": fingerprint}) + "\n"
        sock.sendall(request.encode())

        if ack_timeout > 0:
            sock.settimeout(ack_timeout)
        try:
            ack_raw = _recv_line(sock)
        except socket.timeout:
            warn("[yellow]Warning:[/yellow] embedding daemon timed out — killing and restarting")
            live_pid = _is_alive(perag_dir)
            if live_pid:
                _kill(live_pid)
            _cleanup_stale(perag_dir)
            _try_start(perag_dir, model, batch_size, idle_timeout)
            return None

        ack = json.loads(ack_raw)
        if ack.get("status") != "ack":
            return None

        sock.settimeout(None)
        resp_raw = _recv_line(sock)
        resp = json.loads(resp_raw)

        if resp.get("status") == "ok":
            return resp["vectors"]
        return None

    except Exception:
        return None
    finally:
        try:
            sock.close()
        except Exception:
            pass
