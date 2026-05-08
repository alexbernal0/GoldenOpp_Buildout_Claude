"""
tv_health.py — TradingView CDP connection watchdog.

Polls localhost:9222 every N seconds. Logs reconnection attempts.
Can be imported as a module or run standalone as a daemon.

Usage:
    python tv_health.py            # One-shot check, print status
    python tv_health.py --daemon   # Run indefinitely, reconnect on drop
    python tv_health.py --status   # Print JSON status and exit
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    import urllib.request

# ── Config ────────────────────────────────────────────────────────────────────

CDP_PORT = 9222
CDP_URL = f"http://localhost:{CDP_PORT}"
POLL_INTERVAL = 10          # seconds between health checks
RECONNECT_WAIT = 5          # seconds to wait before attempting reconnect
LOG_PATH = Path(__file__).parent.parent / "logs" / "tv_health.log"

# ── Logging ───────────────────────────────────────────────────────────────────

LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [TV_HEALTH] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("tv_health")

# ── State ─────────────────────────────────────────────────────────────────────

_state = {
    "connected": False,
    "last_check": None,
    "last_connected": None,
    "reconnect_attempts": 0,
    "cdp_url": CDP_URL,
}


# ── Core Functions ────────────────────────────────────────────────────────────

def _get(url: str, timeout: float = 2.0) -> dict | None:
    """HTTP GET, returns parsed JSON or None."""
    try:
        if HAS_REQUESTS:
            r = requests.get(url, timeout=timeout)
            return r.json()
        else:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                return json.loads(resp.read())
    except Exception:
        return None


def is_connected() -> bool:
    """Return True if CDP is responding on port 9222."""
    result = _get(f"{CDP_URL}/json")
    connected = result is not None
    _state["connected"] = connected
    _state["last_check"] = datetime.utcnow().isoformat()
    if connected:
        _state["last_connected"] = _state["last_check"]
    return connected


def get_status() -> dict:
    """Return current health status as a dict."""
    connected = is_connected()
    version_data = _get(f"{CDP_URL}/json/version") or {}
    return {
        "connected": connected,
        "cdp_url": CDP_URL,
        "last_check": _state["last_check"],
        "last_connected": _state["last_connected"],
        "reconnect_attempts": _state["reconnect_attempts"],
        "browser": version_data.get("Browser", "unknown"),
        "user_agent": version_data.get("User-Agent", "unknown")[:80],
    }


def _attempt_reconnect():
    """Try to reconnect by re-launching TradingView."""
    _state["reconnect_attempts"] += 1
    log.warning(f"Connection lost. Reconnect attempt #{_state['reconnect_attempts']} in {RECONNECT_WAIT}s...")
    time.sleep(RECONNECT_WAIT)

    # Import the launcher
    try:
        launcher_path = Path(__file__).parent / "tv_launcher.py"
        if launcher_path.exists():
            import importlib.util
            spec = importlib.util.spec_from_file_location("tv_launcher", launcher_path)
            launcher = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(launcher)
            launcher.launch(wait=True)
        else:
            log.error("tv_launcher.py not found — cannot auto-reconnect.")
    except Exception as e:
        log.error(f"Reconnect failed: {e}")


def run_daemon(poll_interval: int = POLL_INTERVAL):
    """
    Run indefinitely. Poll every poll_interval seconds.
    On connection drop: wait, attempt reconnect, log all events.
    """
    log.info(f"Watchdog started — polling every {poll_interval}s")
    log.info(f"CDP target: {CDP_URL}")

    was_connected = False

    while True:
        connected = is_connected()

        if connected and not was_connected:
            log.info("✅ TradingView CDP connection ESTABLISHED")
            was_connected = True

        elif not connected and was_connected:
            log.warning("⚠  TradingView CDP connection LOST")
            was_connected = False
            _attempt_reconnect()

        elif not connected and not was_connected:
            log.info(f"Waiting for TradingView... (attempt {_state['reconnect_attempts']+1})")

        time.sleep(poll_interval)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TradingView CDP health watchdog")
    parser.add_argument("--daemon", action="store_true", help="Run continuously as watchdog")
    parser.add_argument("--status", action="store_true", help="Print JSON status and exit")
    args = parser.parse_args()

    if args.status:
        status = get_status()
        print(json.dumps(status, indent=2))
        sys.exit(0 if status["connected"] else 1)

    elif args.daemon:
        try:
            run_daemon()
        except KeyboardInterrupt:
            log.info("Watchdog stopped by user.")

    else:
        # One-shot check
        if is_connected():
            print(f"[TV_HEALTH] ✅ Connected to TradingView CDP on port {CDP_PORT}")
            sys.exit(0)
        else:
            print(f"[TV_HEALTH] ❌ TradingView CDP not responding on port {CDP_PORT}")
            print("[TV_HEALTH] Run: scripts\\launch_tv_windows.bat")
            sys.exit(1)
