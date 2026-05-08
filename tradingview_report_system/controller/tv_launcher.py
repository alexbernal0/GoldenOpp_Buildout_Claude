"""
tv_launcher.py — Launch TradingView Desktop with Chrome DevTools Protocol enabled.

Usage:
    python tv_launcher.py            # Launch and return
    python tv_launcher.py --wait     # Launch and wait until CDP is ready
    python tv_launcher.py --check    # Only check if already connected (no launch)
"""

import argparse
import subprocess
import sys
import time
import os
import json
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

# ── Config ────────────────────────────────────────────────────────────────────

CDP_PORT = 9222
CDP_BASE = f"http://localhost:{CDP_PORT}"
PINNED_VERSION = "3.0.0"

TV_PATHS = [
    os.path.expandvars(r"%LOCALAPPDATA%\TradingView\TradingView.exe"),
    os.path.expandvars(r"%PROGRAMFILES%\TradingView\TradingView.exe"),
    r"C:\Users\admin\AppData\Local\TradingView\TradingView.exe",
]

MAX_RETRIES = 15
RETRY_INTERVAL = 2  # seconds


# ── Functions ─────────────────────────────────────────────────────────────────

def find_tv_executable() -> str | None:
    """Return the first TradingView executable path that exists."""
    for path in TV_PATHS:
        if Path(path).exists():
            return path
    return None


def is_cdp_ready() -> bool:
    """Check if CDP port 9222 is responding."""
    if requests is None:
        import urllib.request
        try:
            urllib.request.urlopen(f"{CDP_BASE}/json", timeout=2)
            return True
        except Exception:
            return False
    try:
        r = requests.get(f"{CDP_BASE}/json", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def get_cdp_version() -> dict | None:
    """Return the CDP /json/version payload."""
    try:
        if requests:
            r = requests.get(f"{CDP_BASE}/json/version", timeout=2)
            return r.json()
        else:
            import urllib.request
            with urllib.request.urlopen(f"{CDP_BASE}/json/version", timeout=2) as resp:
                return json.loads(resp.read())
    except Exception:
        return None


def check_version():
    """Warn if TradingView version differs from pinned version."""
    ver_data = get_cdp_version()
    if ver_data is None:
        print("[TV_LAUNCHER] ⚠  Could not read version from CDP.")
        return
    browser = ver_data.get("Browser", "")
    print(f"[TV_LAUNCHER] CDP Browser: {browser}")
    # TradingView Electron embeds its own Chrome; the app version is in the UserAgent
    ua = ver_data.get("User-Agent", "")
    print(f"[TV_LAUNCHER] UserAgent: {ua[:80]}...")
    if PINNED_VERSION not in ua and PINNED_VERSION not in browser:
        print(f"[TV_LAUNCHER] ⚠  Pinned version {PINNED_VERSION} not confirmed in UserAgent.")
        print(f"[TV_LAUNCHER] ⚠  If TradingView updated, CDP may break. Pin updates in TV settings.")
    else:
        print(f"[TV_LAUNCHER] ✅ Version check OK (pinned={PINNED_VERSION})")


def wait_for_cdp(max_retries: int = MAX_RETRIES, interval: float = RETRY_INTERVAL) -> bool:
    """Poll CDP until ready or give up. Returns True if connected."""
    print(f"[TV_LAUNCHER] Waiting for CDP on port {CDP_PORT}...", end="", flush=True)
    for i in range(max_retries):
        if is_cdp_ready():
            print(f" connected! ({i * interval:.0f}s)")
            return True
        print(".", end="", flush=True)
        time.sleep(interval)
    print(f" TIMEOUT after {max_retries * interval:.0f}s")
    return False


def launch(wait: bool = True) -> bool:
    """
    Launch TradingView Desktop with --remote-debugging-port=9222.
    If wait=True, blocks until CDP is ready.
    Returns True if CDP is reachable.
    """
    # Already running?
    if is_cdp_ready():
        print("[TV_LAUNCHER] ✅ TradingView already running with CDP on port 9222.")
        check_version()
        return True

    tv_path = find_tv_executable()
    if tv_path is None:
        print("[TV_LAUNCHER] ❌ TradingView Desktop not found. Checked paths:")
        for p in TV_PATHS:
            print(f"  {p}")
        print("[TV_LAUNCHER] Please install TradingView Desktop or set the correct path.")
        return False

    print(f"[TV_LAUNCHER] Launching: {tv_path}")
    print(f"[TV_LAUNCHER] Flag: --remote-debugging-port={CDP_PORT}")

    try:
        subprocess.Popen(
            [tv_path, f"--remote-debugging-port={CDP_PORT}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.DETACHED_PROCESS if sys.platform == "win32" else 0,
        )
    except Exception as e:
        print(f"[TV_LAUNCHER] ❌ Failed to launch TradingView: {e}")
        return False

    if not wait:
        print("[TV_LAUNCHER] TradingView launching (--wait not set, not polling).")
        return True

    connected = wait_for_cdp()
    if connected:
        check_version()
        print(f"[TV_LAUNCHER] ✅ TradingView Desktop connected on CDP port {CDP_PORT}")
    else:
        print("[TV_LAUNCHER] ❌ TradingView did not respond within timeout.")
        print("[TV_LAUNCHER] Try launching manually:")
        print(f'  "{tv_path}" --remote-debugging-port={CDP_PORT}')
    return connected


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Launch TradingView Desktop with CDP")
    parser.add_argument("--wait", action="store_true", help="Block until CDP is ready")
    parser.add_argument("--check", action="store_true", help="Check connection only, no launch")
    args = parser.parse_args()

    if args.check:
        if is_cdp_ready():
            print(f"[TV_LAUNCHER] ✅ CDP ready on port {CDP_PORT}")
            check_version()
            sys.exit(0)
        else:
            print(f"[TV_LAUNCHER] ❌ CDP not responding on port {CDP_PORT}")
            sys.exit(1)
    else:
        ok = launch(wait=args.wait or True)
        sys.exit(0 if ok else 1)
