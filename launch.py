#!/usr/bin/env python3
"""One-click launcher for AI Overlord.

Goal: the user double-clicks ``Start AI Overlord.bat`` (Windows),
``Start AI Overlord.command`` (macOS) or ``start-ai-overlord.sh`` (Linux), and
the entire stack — Python venv, backend deps, frontend deps, renderer build,
Electron — comes up automatically. Re-runs are fast because every step is
idempotent.

Stdlib only — runs on any Python 3.11+ without installation.

Flags
-----
--no-electron     Run only the backend (useful for `vite dev` or headless boxes).
--rebuild         Force ``npm run build`` even if ``frontend/dist`` exists.
--reset           Wipe ``.venv`` and ``frontend/node_modules`` and re-install.
--port PORT       Override the backend port (default 8765).
--check           Print prerequisites status and exit (no install / no launch).
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
IS_WIN = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"

VENV = ROOT / ".venv"
PY_BIN = (
    VENV / ("Scripts" if IS_WIN else "bin") / ("python.exe" if IS_WIN else "python")
)
PIP_BIN = (
    VENV / ("Scripts" if IS_WIN else "bin") / ("pip.exe" if IS_WIN else "pip")
)

FRONTEND = ROOT / "frontend"
NODE_MODULES = FRONTEND / "node_modules"
DIST = FRONTEND / "dist"
ELECTRON_BIN = NODE_MODULES / ".bin" / ("electron.cmd" if IS_WIN else "electron")
SETUP_MARKER = ROOT / ".venv" / ".overlord-setup-complete"


# ANSI palette (auto-disabled on Windows legacy consoles).
class _C:
    if IS_WIN and not os.environ.get("WT_SESSION"):
        BOLD = CYAN = MAG = GREEN = YELLOW = RED = DIM = END = ""
    else:
        BOLD = "\033[1m"
        CYAN = "\033[36m"
        MAG = "\033[35m"
        GREEN = "\033[32m"
        YELLOW = "\033[33m"
        RED = "\033[31m"
        DIM = "\033[2m"
        END = "\033[0m"


def banner() -> None:
    print(f"{_C.BOLD}{_C.MAG}╭───────────────────────────────────────────────╮{_C.END}")
    print(f"{_C.BOLD}{_C.MAG}│              A I   O V E R L O R D            │{_C.END}")
    print(f"{_C.BOLD}{_C.MAG}╰───────────────────────────────────────────────╯{_C.END}")
    print(f"{_C.DIM}  one-click launcher — {platform.system()} / Python {sys.version.split()[0]}{_C.END}")
    print()


def info(msg: str) -> None:
    print(f"{_C.CYAN}»{_C.END} {msg}")


def good(msg: str) -> None:
    print(f"{_C.GREEN}✓{_C.END} {msg}")


def warn(msg: str) -> None:
    print(f"{_C.YELLOW}!{_C.END} {msg}")


def fail(msg: str) -> None:
    print(f"{_C.RED}✗{_C.END} {msg}")


# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------


def which(cmd: str) -> str | None:
    return shutil.which(cmd)


def node_version() -> tuple[int, int, int] | None:
    node = which("node")
    if not node:
        return None
    try:
        out = subprocess.run(
            [node, "--version"], capture_output=True, text=True, check=True
        ).stdout.strip().lstrip("v")
        a, b, c = (int(x) for x in out.split(".")[:3])
        return a, b, c
    except Exception:
        return None


def python_ok() -> bool:
    return sys.version_info >= (3, 11)


def npm_bin() -> str | None:
    return which("npm")


def show_install_help() -> None:
    print()
    print(f"{_C.BOLD}AI Overlord needs Node.js (≥ 18) and Python (≥ 3.11).{_C.END}")
    print()
    if IS_WIN:
        print("Easy install on Windows 11 (open PowerShell as your normal user):")
        print(f"  {_C.CYAN}winget install OpenJS.NodeJS.LTS{_C.END}")
        print(f"  {_C.CYAN}winget install Python.Python.3.12{_C.END}")
        print()
        print("Then re-run this launcher.")
    elif IS_MAC:
        print("Easy install on macOS (with Homebrew):")
        print(f"  {_C.CYAN}brew install node python@3.12{_C.END}")
        print()
        print("Then re-run this launcher.")
    else:
        print("Easy install on Linux (Debian/Ubuntu):")
        print(
            f"  {_C.CYAN}sudo apt update && sudo apt install -y python3-venv "
            f"python3-pip nodejs npm{_C.END}"
        )
        print("Or via nvm + pyenv. Then re-run this launcher.")
    print()


def check_prereqs() -> bool:
    ok = True
    if not python_ok():
        fail(f"Python {sys.version_info.major}.{sys.version_info.minor} too old; need 3.11+")
        ok = False
    else:
        good(f"Python {sys.version.split()[0]}")
    nv = node_version()
    if nv is None:
        fail("Node.js not found on PATH")
        ok = False
    elif nv[0] < 18:
        fail(f"Node {'.'.join(map(str, nv))} too old; need 18+")
        ok = False
    else:
        good(f"Node v{'.'.join(map(str, nv))}")
    if not npm_bin():
        fail("npm not found on PATH")
        ok = False
    else:
        good(f"npm at {npm_bin()}")
    return ok


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


def run(cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> int:
    info(" ".join(str(c) for c in cmd))
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env)
    return proc.returncode


def ensure_venv() -> None:
    if PY_BIN.exists():
        return
    info("creating Python virtual environment…")
    rc = run([sys.executable, "-m", "venv", str(VENV)])
    if rc != 0 or not PY_BIN.exists():
        fail("venv creation failed; aborting.")
        sys.exit(rc or 1)
    good("venv created")


def install_backend() -> None:
    info("installing backend (pip install -e ./backend) …")
    rc = run([str(PY_BIN), "-m", "pip", "install", "--upgrade", "pip", "wheel", "--quiet"])
    if rc != 0:
        warn("pip upgrade failed; continuing")
    rc = run([str(PY_BIN), "-m", "pip", "install", "-e", "./backend", "--quiet"])
    if rc != 0:
        fail("backend install failed")
        sys.exit(rc)
    good("backend installed")


def install_frontend() -> None:
    if NODE_MODULES.exists():
        good("frontend deps already installed")
        return
    info("installing frontend deps (npm install) — first run takes ~1 min …")
    rc = run([npm_bin() or "npm", "install", "--no-audit", "--no-fund"], cwd=FRONTEND)
    if rc != 0:
        fail("npm install failed")
        sys.exit(rc)
    good("frontend installed")


def build_renderer(force: bool = False) -> None:
    if DIST.exists() and (DIST / "index.html").exists() and not force:
        good("renderer already built")
        return
    info("building renderer (npm run build) …")
    rc = run([npm_bin() or "npm", "run", "build"], cwd=FRONTEND)
    if rc != 0:
        fail("renderer build failed")
        sys.exit(rc)
    good("renderer built")


def mark_setup_done() -> None:
    SETUP_MARKER.parent.mkdir(parents=True, exist_ok=True)
    SETUP_MARKER.write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")


# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------


def wait_for_backend(port: int, timeout_s: float = 25.0) -> bool:
    url = f"http://127.0.0.1:{port}/health"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(0.4)
    return False


def start_backend(port: int) -> subprocess.Popen:
    info(f"starting backend on http://127.0.0.1:{port} …")
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    cmd = [
        str(PY_BIN),
        "-m",
        "uvicorn",
        "backend.app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "info",
    ]
    creationflags = 0
    if IS_WIN:
        # CREATE_NEW_PROCESS_GROUP lets us send Ctrl-C without killing ourselves
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=env,
        creationflags=creationflags,
    )


def start_electron(port: int) -> subprocess.Popen:
    info("starting Electron …")
    env = os.environ.copy()
    env["OVERLORD_NO_BACKEND"] = "1"  # we already started it
    env["OVERLORD_PORT"] = str(port)
    bin_ = ELECTRON_BIN if ELECTRON_BIN.exists() else None
    if bin_:
        cmd = [str(bin_), "."]
    else:
        cmd = [npm_bin() or "npm", "run", "electron"]
    return subprocess.Popen(cmd, cwd=str(FRONTEND), env=env)


def supervise(procs: list[subprocess.Popen]) -> int:
    """Wait until any child exits, then tear the others down."""
    try:
        while True:
            for p in procs:
                rc = p.poll()
                if rc is not None:
                    return rc
            time.sleep(0.3)
    except KeyboardInterrupt:
        info("interrupt received; stopping…")
        return 0
    finally:
        for p in procs:
            if p.poll() is None:
                try:
                    if IS_WIN:
                        p.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[arg-type]
                    else:
                        p.terminate()
                except Exception:  # noqa: BLE001
                    pass
        deadline = time.time() + 4.0
        for p in procs:
            while p.poll() is None and time.time() < deadline:
                time.sleep(0.1)
            if p.poll() is None:
                try:
                    p.kill()
                except Exception:  # noqa: BLE001
                    pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="AI Overlord one-click launcher")
    ap.add_argument("--no-electron", action="store_true", help="backend only")
    ap.add_argument("--rebuild", action="store_true", help="force renderer rebuild")
    ap.add_argument("--reset", action="store_true", help="wipe and re-install")
    ap.add_argument("--port", type=int, default=int(os.environ.get("OVERLORD_PORT", 8765)))
    ap.add_argument("--check", action="store_true", help="report prereqs and exit")
    args = ap.parse_args()

    banner()

    if args.check:
        ok = check_prereqs()
        sys.exit(0 if ok else 1)

    if args.reset:
        if VENV.exists():
            info("removing .venv …")
            shutil.rmtree(VENV, ignore_errors=True)
        if NODE_MODULES.exists():
            info("removing frontend/node_modules …")
            shutil.rmtree(NODE_MODULES, ignore_errors=True)
        if DIST.exists():
            info("removing frontend/dist …")
            shutil.rmtree(DIST, ignore_errors=True)

    if not check_prereqs():
        show_install_help()
        return 2

    ensure_venv()
    install_backend()
    install_frontend()
    if not args.no_electron:
        build_renderer(force=args.rebuild)
    mark_setup_done()
    good("setup complete — launching")
    print()

    backend = start_backend(args.port)
    if not wait_for_backend(args.port):
        warn("backend didn't answer /health in time — continuing anyway")
    else:
        good(f"backend is healthy on :{args.port}")

    procs = [backend]
    if not args.no_electron:
        procs.append(start_electron(args.port))

    return supervise(procs)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
