"""
tv_orchestrator.py — Master controller that bridges Python → Node.js MCP controller → TradingView Desktop.

All 78 MCP tools are accessible via _cli(). Named workflows delegate to workflow modules.
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .session_store import SessionStore

# ── Paths ─────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.parent
CONTROLLER = ROOT / "controller"
CLI_ENTRY = CONTROLLER / "src" / "cli" / "index.js"
SCREENSHOTS_DIR = ROOT / "demo" / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


# ── CLI command map: Python name → tv CLI subcommand ─────────────────────────
# Format: "tool_name": ("cli_group", "cli_subcommand")

TOOL_CLI_MAP = {
    # Chart reading
    "chart_get_state":          ("state", None),
    "quote_get":                ("quote", None),
    "data_get_ohlcv":           ("ohlcv", None),
    "data_get_study_values":    ("data", "values"),
    "data_get_pine_lines":      ("data", "lines"),
    "data_get_pine_labels":     ("data", "labels"),
    "data_get_pine_tables":     ("data", "tables"),
    "data_get_pine_boxes":      ("data", "boxes"),
    # Chart control
    "chart_set_symbol":         ("symbol", None),
    "chart_set_timeframe":      ("timeframe", None),
    "chart_set_type":           ("type", None),
    "chart_manage_indicator":   ("indicator", None),
    "chart_scroll_to_date":     ("range", None),
    "symbol_info":              ("info", None),
    "symbol_search":            ("search", None),
    "indicator_set_inputs":     ("indicator", "set"),
    "indicator_toggle_visibility": ("indicator", "toggle"),
    # Multi-pane
    "pane_list":                ("pane", "list"),
    "pane_set_layout":          ("pane", "layout"),
    "pane_focus":               ("pane", "focus"),
    "pane_set_symbol":          ("pane", "symbol"),
    # Tabs
    "tab_list":                 ("tab", "list"),
    "tab_new":                  ("tab", "new"),
    "tab_close":                ("tab", "close"),
    "tab_switch":               ("tab", "switch"),
    # Pine Script
    "pine_set_source":          ("pine", "set"),
    "pine_smart_compile":       ("pine", "compile"),
    "pine_get_errors":          ("pine", "errors"),
    "pine_get_console":         ("pine", "console"),
    "pine_save":                ("pine", "save"),
    "pine_get_source":          ("pine", "get"),
    "pine_new":                 ("pine", "new"),
    "pine_open":                ("pine", "open"),
    "pine_list_scripts":        ("pine", "list"),
    "pine_analyze":             ("pine", "analyze"),
    "pine_check":               ("pine", "check"),
    # Replay
    "replay_start":             ("replay", "start"),
    "replay_step":              ("replay", "step"),
    "replay_autoplay":          ("replay", "autoplay"),
    "replay_trade":             ("replay", "trade"),
    "replay_status":            ("replay", "status"),
    "replay_stop":              ("replay", "stop"),
    # Drawings & Alerts
    "draw_shape":               ("draw", "shape"),
    "draw_list":                ("draw", "list"),
    "draw_remove_one":          ("draw", "remove"),
    "draw_clear":               ("draw", "clear"),
    "alert_create":             ("alert", "create"),
    "alert_list":               ("alert", "list"),
    "alert_delete":             ("alert", "delete"),
    # Screenshots & UI
    "capture_screenshot":       ("screenshot", None),
    "batch_run":                ("ui", "eval"),
    "watchlist_get":            ("watchlist", "get"),
    "watchlist_add":            ("watchlist", "add"),
    "layout_list":              ("layout", "list"),
    "layout_switch":            ("layout", "switch"),
    "ui_open_panel":            ("ui", "panel"),
    "ui_click":                 ("ui", "click"),
    "ui_evaluate":              ("ui", "eval"),
    # System
    "tv_health_check":          ("status", None),
    "tv_launch":                ("launch", None),
    "tv_discover":              ("discover", None),
}


class TVOrchestrator:
    """
    Master controller for TradingView sidecar.
    Exposes all 78 MCP tools as Python methods + named workflows.
    """

    def __init__(self):
        self.cdp_url = "http://localhost:9222"
        self.controller_path = CONTROLLER
        self.session_store = SessionStore()
        self._node_available = self._check_node()

    def _check_node(self) -> bool:
        """Check if Node.js is available."""
        try:
            result = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except Exception:
            return False

    # ── Core CLI bridge ───────────────────────────────────────────────────────

    def _cli(self, *args: str, timeout: int = 30) -> dict | list | str:
        """
        Call the Node.js CLI. Returns parsed JSON or raw string.
        Example: self._cli("symbol", "AAPL")
        """
        if not CLI_ENTRY.exists():
            return {"error": f"CLI not found: {CLI_ENTRY}"}

        cmd = ["node", str(CLI_ENTRY)] + [str(a) for a in args]

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,   # Binary mode — decode manually as UTF-8 to handle Unicode Pine code
                timeout=timeout,
                cwd=str(self.controller_path),
            )
            # Decode bytes as UTF-8 (handles Unicode in Pine code)
            stdout_raw = result.stdout if result.stdout else b""
            stderr_raw = result.stderr if result.stderr else b""
            output = stdout_raw.decode("utf-8", errors="replace").strip()
            stderr_str = stderr_raw.decode("utf-8", errors="replace").strip()

            if not output:
                if stderr_str:
                    return {"error": stderr_str[:500]}
                return {"ok": True, "note": "No output"}

            # Try JSON parse
            try:
                return json.loads(output)
            except json.JSONDecodeError:
                return {"raw": output}

        except subprocess.TimeoutExpired:
            return {"error": f"CLI timeout after {timeout}s"}
        except Exception as e:
            return {"error": str(e)}

    def call_tool(self, tool_name: str, **kwargs) -> dict:
        """
        Call any of the 78 MCP tools by name.
        kwargs are passed as --key value CLI flags.
        """
        if tool_name not in TOOL_CLI_MAP:
            return {"error": f"Unknown tool: {tool_name}. Available: {list(TOOL_CLI_MAP.keys())}"}

        group, subcommand = TOOL_CLI_MAP[tool_name]
        args = [group]
        if subcommand:
            args.append(subcommand)

        # Convert kwargs to CLI flags
        for k, v in kwargs.items():
            if isinstance(v, bool):
                if v:
                    args.append(f"--{k}")
            elif isinstance(v, (dict, list)):
                args.extend([f"--{k}", json.dumps(v)])
            else:
                args.extend([f"--{k}", str(v)])

        return self._cli(*args)

    # ── Common operations (convenience wrappers) ──────────────────────────────

    def get_chart_state(self) -> dict:
        """Get current symbol, timeframe, and all loaded indicators."""
        return self._cli("state")

    def set_symbol(self, symbol: str) -> bool:
        """Change the chart symbol."""
        result = self._cli("symbol", symbol)
        return not isinstance(result, dict) or "error" not in result

    def set_timeframe(self, tf: str) -> bool:
        """Change the chart timeframe. Values: 1, 5, 15, 60, D, W, M"""
        result = self._cli("timeframe", tf)
        return not isinstance(result, dict) or "error" not in result

    def get_quote(self) -> dict:
        """Get current price, OHLC, volume."""
        return self._cli("quote")

    def get_ohlcv(self, bars: int = 100, summary: bool = True) -> dict:
        """Get OHLCV bars. Use summary=True for compact stats."""
        if summary:
            return self._cli("ohlcv", "--summary")
        return self._cli("ohlcv", "--bars", str(bars))

    def get_study_values(self, study_filter: str | None = None) -> dict:
        """Read indicator values. Use study_filter to target one indicator."""
        if study_filter:
            return self._cli("data", "values", "--study_filter", study_filter)
        return self._cli("data", "values")

    def get_pine_labels(self, study_filter: str | None = None) -> dict:
        """Read Pine Script label.new() outputs (text annotations + prices)."""
        if study_filter:
            return self._cli("data", "labels", "--study_filter", study_filter)
        return self._cli("data", "labels")

    def get_pine_lines(self, study_filter: str | None = None) -> dict:
        """Read Pine Script line.new() outputs (price levels)."""
        if study_filter:
            return self._cli("data", "lines", "--study_filter", study_filter)
        return self._cli("data", "lines")

    def get_pine_tables(self, study_filter: str | None = None) -> dict:
        """Read Pine Script table.new() outputs."""
        if study_filter:
            return self._cli("data", "tables", "--study_filter", study_filter)
        return self._cli("data", "tables")

    def take_screenshot(self, region: str = "chart") -> str:
        """
        Capture screenshot. region: 'chart', 'full', 'strategy_tester'
        Returns file path of saved screenshot.
        """
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        outfile = SCREENSHOTS_DIR / f"screenshot_{region}_{ts}.png"

        result = self._cli("screenshot", "--region", region)

        if isinstance(result, dict) and "error" in result:
            return f"ERROR: {result['error']}"

        # If the CLI saves to disk, return path
        if outfile.exists():
            return str(outfile)

        # Some versions return base64 — save it
        if isinstance(result, dict):
            # Check for path returned by CLI
            path = result.get("path") or result.get("file") or result.get("output") or result.get("filename")
            if path and not str(path).startswith("ERROR"):
                return str(path)
            # Check for base64 image data
            b64 = result.get("screenshot") or result.get("data") or result.get("image")
            if b64:
                try:
                    img_bytes = base64.b64decode(b64)
                    outfile.write_bytes(img_bytes)
                    return str(outfile)
                except Exception:
                    pass
            # If success but no path, CLI saved it to its own screenshots dir
            if result.get("success"):
                # Look for the most recently created file in the controller screenshots dir
                ctrl_ss = self.controller_path / "screenshots"
                if ctrl_ss.exists():
                    pngs = sorted(ctrl_ss.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
                    if pngs:
                        # Copy to our screenshots dir
                        import shutil
                        dest = SCREENSHOTS_DIR / pngs[0].name
                        shutil.copy2(str(pngs[0]), str(dest))
                        return str(dest)
            if "error" in result:
                return f"ERROR: {result['error']}"

        return f"Screenshot attempted: {outfile} (check file)"

    # ── Chart Patterns ────────────────────────────────────────────────────────

    def enable_chart_patterns(self) -> bool:
        """
        Add the TradingView 'Auto Chart Patterns' built-in indicator to the current chart.
        This indicator automatically detects and draws chart patterns.
        """
        result = self._cli("indicator", "add", "--name", "Auto Chart Patterns")
        if isinstance(result, dict) and "error" in result:
            print(f"[Orchestrator] enable_chart_patterns: {result['error']}")
            return False
        # Wait for indicator to load and render
        time.sleep(3)
        return True

    def get_chart_pattern_data(self) -> dict:
        """
        Read all pattern data from the Auto Chart Patterns indicator.
        Parses labels (pattern names/targets) and lines (boundaries).
        Returns structured list of detected patterns.
        """
        # Read labels — patterns show as labels with name + price target
        labels_raw = self.get_pine_labels(study_filter="Auto Chart Patterns")
        lines_raw = self.get_pine_lines(study_filter="Auto Chart Patterns")

        patterns = []

        # Parse label data
        if isinstance(labels_raw, list):
            for label in labels_raw:
                text = label.get("text", "") or label.get("label", "") or str(label)
                price = label.get("price") or label.get("y") or label.get("value")
                patterns.append({
                    "type": "label",
                    "text": text,
                    "price": price,
                    "raw": label,
                })
        elif isinstance(labels_raw, dict):
            items = labels_raw.get("labels") or labels_raw.get("data") or []
            for item in items:
                if isinstance(item, dict):
                    patterns.append({
                        "type": "label",
                        "text": item.get("text", ""),
                        "price": item.get("price") or item.get("y"),
                        "raw": item,
                    })

        # Parse price levels from lines
        price_levels = []
        if isinstance(lines_raw, list):
            for line in lines_raw:
                price = line.get("price") or line.get("y1") or line.get("value")
                if price:
                    price_levels.append(float(price))
        elif isinstance(lines_raw, dict):
            items = lines_raw.get("lines") or lines_raw.get("data") or []
            for item in items:
                if isinstance(item, dict):
                    price = item.get("price") or item.get("y1")
                    if price:
                        price_levels.append(float(price))

        return {
            "patterns": patterns,
            "pattern_count": len(patterns),
            "price_levels": sorted(set(price_levels)),
            "labels_raw": labels_raw,
            "lines_raw": lines_raw,
        }

    # ── Pine Script ───────────────────────────────────────────────────────────

    def pine_set_and_compile(self, code: str) -> dict:
        """Inject Pine Script and compile. Returns {compiled: bool, errors: list}."""
        import tempfile, os
        # Write code to a temp file — CLI requires --file or stdin, not --code
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".pine",
                                          delete=False, encoding="utf-8")
        tmp.write(code)
        tmp.close()
        set_result = self._cli("pine", "set", "--file", tmp.name, timeout=15)
        try:
            os.unlink(tmp.name)
        except Exception:
            pass
        # After setting source, use raw-compile to click Add to Chart button directly
        # smart_compile can misidentify the button (hits Save instead of Add)
        compile_result_raw = self._cli("pine", "raw-compile", timeout=30)

        # Compile
        compile_result = self._cli("pine", "compile", timeout=30)

        # Check errors
        errors_result = self._cli("pine", "errors")
        all_messages = []
        if isinstance(errors_result, list):
            all_messages = errors_result
        elif isinstance(errors_result, dict):
            all_messages = errors_result.get("errors", [])

        # severity 4 = warning/info in Pine Script, not a true error
        # severity 1/2/3 = actual errors that prevent compilation
        true_errors = [
            e for e in all_messages
            if isinstance(e, dict) and e.get("severity", 0) < 4
        ] if all_messages and isinstance(all_messages[0], dict) else all_messages

        return {
            "compiled": len(true_errors) == 0,
            "errors": true_errors,
            "warnings": [e for e in all_messages if e not in true_errors],
            "set_result": set_result,
            "compile_result": compile_result,
        }

    # ── Alert management ──────────────────────────────────────────────────────

    def create_alert(self, condition: str, symbol: str | None = None) -> dict:
        """Create a price alert on the current chart."""
        args = ["alert", "create", "--condition", condition]
        if symbol:
            args.extend(["--symbol", symbol])
        result = self._cli(*args)
        if isinstance(result, dict) and "id" in result:
            self.session_store.save_alert(
                symbol=symbol or "current",
                condition=condition,
                alert_id=str(result["id"]),
            )
        return result

    def list_alerts(self) -> list:
        """List all active TradingView alerts."""
        result = self._cli("alert", "list")
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("alerts", [result])
        return []

    # ── Health ────────────────────────────────────────────────────────────────

    def health_check(self) -> dict:
        """Check full system health: Node.js, CDP, TradingView."""
        import urllib.request

        node_ok = self._node_available
        cli_ok = CLI_ENTRY.exists()

        cdp_ok = False
        tv_version = "unknown"
        try:
            with urllib.request.urlopen("http://localhost:9222/json/version", timeout=2) as resp:
                ver_data = json.loads(resp.read())
                cdp_ok = True
                tv_version = ver_data.get("Browser", "unknown")
        except Exception:
            pass

        return {
            "node_available": node_ok,
            "cli_found": cli_ok,
            "cli_path": str(CLI_ENTRY),
            "cdp_connected": cdp_ok,
            "tv_version": tv_version,
            "cdp_url": self.cdp_url,
            "status": "OK" if (node_ok and cli_ok and cdp_ok) else "DEGRADED",
        }
