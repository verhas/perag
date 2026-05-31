"""Embedding daemon — keeps the local model resident between CLI invocations."""

import hashlib
import json
import os
import signal
import socket
import sys
import time
from pathlib import Path


def config_fingerprint(model: str, batch_size: int) -> str:
    return hashlib.md5(f"{model}:{batch_size}".encode()).hexdigest()


def _cleanup(sock_path: Path, pid_path: Path, server: socket.socket | None = None) -> None:
    if server is not None:
        try:
            server.close()
        except Exception:
            pass
    for p in (sock_path, pid_path):
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass


def serve(perag_dir: Path, model: str, batch_size: int, idle_timeout: int = 300) -> None:
    """Run the embedding daemon. Blocks until shutdown."""
    if not hasattr(socket, "AF_UNIX"):
        print("Unix domain sockets not available on this platform.", file=sys.stderr)
        sys.exit(1)

    sock_path = perag_dir / "embed.sock"
    pid_path = perag_dir / "embed.pid"
    fingerprint = config_fingerprint(model, batch_size)

    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    os.environ.setdefault("HF_HUB_VERBOSITY", "error")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    from sentence_transformers import SentenceTransformer
    embedder = SentenceTransformer(model)

    pid_path.write_text(str(os.getpid()))

    if sock_path.exists():
        sock_path.unlink()

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(sock_path))
    server.listen(5)
    server.settimeout(1.0)

    last_activity = time.monotonic()

    def handle_exit(signum, frame):
        _cleanup(sock_path, pid_path, server)
        sys.exit(0)

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, handle_exit)
        except (OSError, ValueError):
            pass

    try:
        while True:
            if idle_timeout > 0 and time.monotonic() - last_activity > idle_timeout:
                _cleanup(sock_path, pid_path, server)
                sys.exit(0)

            try:
                conn, _ = server.accept()
            except socket.timeout:
                continue

            try:
                data = b""
                while b"\n" not in data:
                    chunk = conn.recv(1 << 20)
                    if not chunk:
                        break
                    data += chunk

                if not data:
                    continue

                request = json.loads(data.rstrip(b"\n"))
                req_fp = request.get("config_fingerprint", "")

                if req_fp != fingerprint:
                    conn.sendall(json.dumps({
                        "status": "error",
                        "message": "config changed — restart daemon",
                    }).encode() + b"\n")
                    conn.close()
                    _cleanup(sock_path, pid_path, server)
                    sys.exit(0)

                conn.sendall(json.dumps({"status": "ack"}).encode() + b"\n")

                texts = request["texts"]
                vectors = embedder.encode(texts, batch_size=batch_size, convert_to_numpy=True)
                conn.sendall(json.dumps({
                    "status": "ok",
                    "vectors": [v.tolist() for v in vectors],
                }).encode() + b"\n")

                last_activity = time.monotonic()

            except Exception as e:
                try:
                    conn.sendall(json.dumps({
                        "status": "error", "message": str(e),
                    }).encode() + b"\n")
                except Exception:
                    pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    except Exception:
        _cleanup(sock_path, pid_path, server)
        raise


if __name__ == "__main__":
    perag_dir = Path(sys.argv[1])
    model = sys.argv[2]
    batch_size = int(sys.argv[3])
    idle_timeout = int(sys.argv[4])
    serve(perag_dir, model, batch_size, idle_timeout)
