from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = REPO_ROOT / "frontend"


def stream_output(prefix: str, pipe: object) -> None:
    assert pipe is not None
    for line in iter(pipe.readline, ""):
        print(f"[{prefix}] {line.rstrip()}", flush=True)


def terminate_process(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def start_process(
    prefix: str,
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> tuple[subprocess.Popen[str], threading.Thread]:
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    thread = threading.Thread(target=stream_output, args=(prefix, process.stdout), daemon=True)
    thread.start()
    return process, thread


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the TripBreeze API and Next.js frontend together.")
    parser.add_argument("--backend-host", default="127.0.0.1")
    parser.add_argument("--backend-port", type=int, default=8100)
    parser.add_argument("--frontend-host", default="127.0.0.1")
    parser.add_argument("--frontend-port", type=int, default=3000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if shutil.which("npm") is None:
        print("`npm` is required to run the frontend. Install Node.js first.", file=sys.stderr)
        return 1

    if not FRONTEND_DIR.exists():
        print("Frontend directory not found.", file=sys.stderr)
        return 1

    backend_command = [
        sys.executable,
        "-m",
        "uvicorn",
        "presentation.api:app",
        "--host",
        args.backend_host,
        "--port",
        str(args.backend_port),
    ]

    frontend_env = os.environ.copy()
    frontend_env.setdefault("HOST", args.frontend_host)
    frontend_env.setdefault("PORT", str(args.frontend_port))
    frontend_env.setdefault("NEXT_PUBLIC_API_BASE_URL", f"http://{args.backend_host}:{args.backend_port}")

    backend_process: subprocess.Popen[str] | None = None
    frontend_process: subprocess.Popen[str] | None = None

    def shutdown(*_: object) -> None:
        terminate_process(frontend_process)
        terminate_process(backend_process)

    original_sigint = signal.getsignal(signal.SIGINT)
    original_sigterm = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        print("Starting TripBreeze dev stack...", flush=True)
        print(
            f"Frontend: http://{args.frontend_host}:{args.frontend_port}  "
            f"API: http://{args.backend_host}:{args.backend_port}",
            flush=True,
        )
        backend_process, _ = start_process("api", backend_command, cwd=REPO_ROOT)
        frontend_process, _ = start_process("web", ["npm", "run", "dev"], cwd=FRONTEND_DIR, env=frontend_env)

        while True:
            if backend_process.poll() is not None:
                print("Backend process exited.", file=sys.stderr)
                return backend_process.returncode or 1
            if frontend_process.poll() is not None:
                print("Frontend process exited.", file=sys.stderr)
                return frontend_process.returncode or 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        shutdown()
        signal.signal(signal.SIGINT, original_sigint)
        signal.signal(signal.SIGTERM, original_sigterm)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
