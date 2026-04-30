"""
GoldenOpp Research — Weekly Technical Analysis Report Generator
==============================================================

ALL data sourced exclusively from TradingView Desktop via CDP.
No external APIs. No yfinance. No screener calls.

Data sources (all via CDP):
  - OHLCV bars        → orc._cli("ohlcv", "--bars", "500") 
  - S/R levels        → orc.get_pine_lines(study_filter="Support/Resistance")
  - Quote             → orc.get_quote()
  - Study metadata    → orc.get_chart_state()

Indicators calculated locally from the raw bars:
  SMA50, SMA200, EMA50, MACD(12,26,9), RSI(14), ATR(14), ADX(14), +DI/-DI

Layout: Landscape A4 — one page per stock
  Left  half → TradingView full-window screenshot
  Right half → CMT institutional analysis prose (6 sections + bias box)

Usage:
    python workflows/weekly_ta_report.py
    python workflows/weekly_ta_report.py --tickers NEM WPM AEM
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from orchestrator.tv_orchestrator import TVOrchestrator

# ── Config ─────────────────────────────────────────────────────────────────────

from datetime import date as _date
REPORT_DATE      = _date.today().strftime("%B %d, %Y")
REPORT_TITLE     = "GoldenOpp Research — Weekly Technical Analysis"
REPORT_SUBTITLE  = "Chartered Market Technician (CMT) Institutional Brief  |  OBQ Signal Suite v2"
DEFAULT_TICKERS  = ["GLD", "SLV", "GDX", "GDXJ", "XME"]

COMPANY_MAP = {
    # ETF Benchmarks
    "GLD":  "SPDR Gold Shares ETF",
    "SLV":  "iShares Silver Trust ETF",
    "GDX":  "VanEck Gold Miners ETF",
    "GDXJ": "VanEck Junior Gold Miners ETF",
    "XME":  "SPDR S&P Metals & Mining ETF",
    # Senior Producers
    "NEM":  "Newmont Corp",
    "WPM":  "Wheaton Precious Metals",
    "AEM":  "Agnico Eagle Mines",
    "GOLD": "Barrick Gold",
    "FNV":  "Franco-Nevada",
    "KGC":  "Kinross Gold",
    "AGI":  "Alamos Gold",
    "PAAS": "Pan American Silver",
    "AU":   "AngloGold Ashanti",
    "GFI":  "Gold Fields",
    "SSRM": "SSR Mining",
    "HL":   "Hecla Mining",
    "EXK":  "Endeavour Silver",
    "SA":   "Seabridge Gold",
    "RGLD": "Royal Gold",
    "OR":   "Osisko Royalties",
    "EQX":  "Equinox Gold",
    "BTG":  "B2Gold Corp",
    "EGO":  "Eldorado Gold",
    "IAG":  "IAMGOLD Corp",
    "HMY":  "Harmony Gold Mining",
    "BVN":  "Buenaventura Mining",
    "CDE":  "Coeur Mining",
    "AG":   "First Majestic Silver",
    "FSM":  "Fortuna Silver Mines",
    "ORLA": "Orla Mining",
    "CGAU": "Centerra Gold",
    "DRD":  "DRDGold",
    "SVM":  "Silvercorp Metals",
    "NG":   "NovaGold Resources",
    "MUX":  "McEwen Mining",
    "ARMN": "Aris Mining",
    # Base / Industrial Metals
    "FCX":  "Freeport-McMoRan",
    "AA":   "Alcoa Corp",
    "NUE":  "Nucor Corp",
    "STLD": "Steel Dynamics",
    "CLF":  "Cleveland-Cliffs",
    "CMC":  "Commercial Metals",
    "RS":   "Reliance Steel",
    "MP":   "MP Materials",
    "LEU":  "Centrus Energy",
    "UEC":  "Uranium Energy Corp",
}

EXCHANGE_MAP = {
    "NEM": "NYSE", "WPM": "NYSE", "AEM": "NYSE", "GOLD": "NYSE",
    "FNV": "NYSE", "KGC": "NYSE", "AGI": "NYSE", "AU":  "NYSE",
    "GFI": "NYSE", "SSRM":"NASDAQ","HL":  "NYSE", "EXK": "NYSE",
    "PAAS":"NASDAQ","SA":  "NYSE",
}

SCREENSHOTS_DIR = ROOT / "reports" / "screenshots"
REPORTS_DIR     = ROOT / "reports"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# ── Step 1: Fetch raw OHLCV bars from TradingView via CDP ─────────────────────

def fetch_ohlcv_bars(orc: TVOrchestrator, bars: int = 500) -> list[dict]:
    """
    Pull raw OHLCV bars from the live TradingView chart.
    CLI flag: --count N  (default 100, max ~500 depending on chart history loaded)
    Returns list of {time, open, high, low, close, volume}.
    """
    result = orc._cli("ohlcv", "--count", str(min(bars, 500)))

    if isinstance(result, dict):
        raw = (result.get("bars") or result.get("data") or
               result.get("ohlcv") or result.get("candles") or [])
    elif isinstance(result, list):
        raw = result
    else:
        raw = []

    return raw


def fetch_bars_via_js(orc: TVOrchestrator, bars: int = 500) -> list[dict]:
    """
    Fallback: extract OHLCV directly from TradingView's chart model via JS.
    This reads from the main series data store.
    """
    js = f"""(function() {{
        try {{
            var chart = window.TradingViewApi.activeChart();
            var panes = chart.getPanes();
            if (!panes || panes.length === 0) return JSON.stringify({{error: 'no panes'}});

            var mainSeries = null;
            try {{
                mainSeries = chart.mainSeries ? chart.mainSeries() : null;
                if (!mainSeries) {{
                    var pane = panes[0];
                    var sources = pane.dataSources ? pane.dataSources() : [];
                    mainSeries = sources[0] || null;
                }}
            }} catch(e) {{}}

            if (!mainSeries) return JSON.stringify({{error: 'no main series'}});

            // Get the data via the series bars method
            var barsData = [];
            try {{
                var data = mainSeries.data ? mainSeries.data() : null;
                if (data && data.bars) {{
                    var allBars = data.bars();
                    var start = Math.max(0, allBars.size() - {bars});
                    for (var i = start; i < allBars.size(); i++) {{
                        var b = allBars.get(i);
                        if (b) barsData.push({{
                            time:   b.time,
                            open:   b.open,
                            high:   b.high,
                            low:    b.low,
                            close:  b.close,
                            volume: b.volume || 0
                        }});
                    }}
                    return JSON.stringify({{bars: barsData, count: barsData.length}});
                }}
            }} catch(e) {{}}

            // Alternate: try _data
            try {{
                var d = mainSeries._data;
                if (d && typeof d.bars === 'function') {{
                    var bs = d.bars();
                    var n = Math.max(0, bs.size() - {bars});
                    for (var j = n; j < bs.size(); j++) {{
                        var bar = bs.get(j);
                        if (bar && bar.close) barsData.push({{
                            time: bar.time, open: bar.open, high: bar.high,
                            low: bar.low, close: bar.close, volume: bar.volume || 0
                        }});
                    }}
                    return JSON.stringify({{bars: barsData, count: barsData.length}});
                }}
            }} catch(e) {{}}

            return JSON.stringify({{error: 'could not access bar data', series_type: typeof mainSeries}});
        }} catch(e) {{
            return JSON.stringify({{error: e.message}});
        }}
    }})()"""

    result = orc._cli("ui", "eval", "--code", js)
    data = json.loads(result.get("result", "{}")) if result.get("result") else {}
    return data.get("bars", [])


def fetch_bars_stream(orc: TVOrchestrator, bars: int = 500) -> list[dict]:
    """
    Third approach: use the stream command to get a batch of bars.
    """
    result = orc._cli("ohlcv", "--summary")
    # Try non-summary mode
    result2 = orc._cli("ohlcv")
    if isinstance(result2, dict):
        raw = result2.get("bars") or result2.get("data") or []
        if raw:
            return raw
    if isinstance(result2, list):
        return result2
    return []


# ── Step 2: Calculate all indicators from raw bars ────────────────────────────

def calc_indicators(bars: list[dict]) -> dict:
    """
    Calculate SMA50, SMA200, EMA50, MACD(12,26,9), RSI(14), ATR(14), ADX(14)
    from a list of OHLCV bar dicts.
    Returns a flat dict of the most recent values.
    """
    if len(bars) < 30:
        return {}

    closes  = [b.get("close", 0) or 0  for b in bars]
    highs   = [b.get("high",  0) or 0  for b in bars]
    lows    = [b.get("low",   0) or 0  for b in bars]
    volumes = [b.get("volume",0) or 0  for b in bars]
    n       = len(closes)

    def sma(data: list, period: int) -> list:
        result = [None] * len(data)
        for i in range(period - 1, len(data)):
            result[i] = sum(data[i - period + 1: i + 1]) / period
        return result

    def ema(data: list, period: int, prev: list = None) -> list:
        k = 2.0 / (period + 1)
        result = [None] * len(data)
        # Seed with SMA
        seed_idx = period - 1
        if seed_idx >= len(data):
            return result
        result[seed_idx] = sum(data[:period]) / period
        for i in range(seed_idx + 1, len(data)):
            result[i] = data[i] * k + result[i-1] * (1 - k)
        return result

    # ── Moving averages ───────────────────────────────────────────────────────
    sma50_s  = sma(closes, 50)
    sma200_s = sma(closes, 200) if n >= 200 else [None] * n
    ema50_s  = ema(closes, 50)

    # ── MACD (12, 26, 9) ─────────────────────────────────────────────────────
    ema12_s = ema(closes, 12)
    ema26_s = ema(closes, 26)
    macd_line_s = [
        (ema12_s[i] - ema26_s[i]) if (ema12_s[i] is not None and ema26_s[i] is not None) else None
        for i in range(n)
    ]
    # Signal = 9-period EMA of MACD line
    macd_vals = [v for v in macd_line_s if v is not None]
    signal_s  = [None] * n
    if len(macd_vals) >= 9:
        first_valid = next(i for i, v in enumerate(macd_line_s) if v is not None)
        k = 2.0 / (9 + 1)
        signal_s[first_valid + 8] = sum(
            v for v in macd_line_s[first_valid: first_valid + 9] if v is not None
        ) / 9
        for i in range(first_valid + 9, n):
            if macd_line_s[i] is not None and signal_s[i-1] is not None:
                signal_s[i] = macd_line_s[i] * k + signal_s[i-1] * (1 - k)

    # ── RSI (14) ─────────────────────────────────────────────────────────────
    rsi_s = [None] * n
    if n >= 15:
        gains = [max(closes[i] - closes[i-1], 0) for i in range(1, n)]
        losses= [max(closes[i-1] - closes[i], 0) for i in range(1, n)]
        # Initial average (simple)
        avg_gain = sum(gains[:14]) / 14
        avg_loss = sum(losses[:14]) / 14
        if avg_loss == 0:
            rsi_s[14] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi_s[14] = 100 - 100 / (1 + rs)
        for i in range(15, n):
            avg_gain = (avg_gain * 13 + gains[i-1]) / 14
            avg_loss = (avg_loss * 13 + losses[i-1]) / 14
            if avg_loss == 0:
                rsi_s[i] = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi_s[i] = 100 - 100 / (1 + rs)

    # ── ATR (14) ─────────────────────────────────────────────────────────────
    tr_s  = [None] * n
    atr_s = [None] * n
    for i in range(1, n):
        hl  = highs[i] - lows[i]
        hpc = abs(highs[i] - closes[i-1])
        lpc = abs(lows[i]  - closes[i-1])
        tr_s[i] = max(hl, hpc, lpc)
    if n >= 15:
        atr_s[14] = sum(t for t in tr_s[1:15] if t) / 14
        for i in range(15, n):
            if tr_s[i] is not None and atr_s[i-1] is not None:
                atr_s[i] = (atr_s[i-1] * 13 + tr_s[i]) / 14

    # ── ADX / +DI / -DI (14) ─────────────────────────────────────────────────
    plus_dm_s  = [None] * n
    minus_dm_s = [None] * n
    for i in range(1, n):
        up_move   = highs[i]  - highs[i-1]
        down_move = lows[i-1] - lows[i]
        plus_dm_s[i]  = up_move   if up_move  > down_move and up_move  > 0 else 0.0
        minus_dm_s[i] = down_move if down_move > up_move  and down_move > 0 else 0.0

    # Smooth +DM, -DM, TR over 14 periods (Wilder smoothing — RMA/SMMA)
    # Wilder's formula: first value = sum(first N), then: prev*(N-1)/N + current
    def wilder_smooth(data: list, period: int) -> list:
        result = [None] * len(data)
        # Find first index with a real value
        first_idx = next((i for i, v in enumerate(data) if v is not None), None)
        if first_idx is None:
            return result
        # Need period valid values to seed
        valid_from_first = [v for v in data[first_idx:first_idx + period] if v is not None]
        if len(valid_from_first) < period:
            return result
        seed_end = first_idx + period - 1
        # Seed = AVERAGE (not sum) of first `period` values — this is Wilder's initial RMA
        result[seed_end] = sum(valid_from_first) / period
        for i in range(seed_end + 1, len(data)):
            if data[i] is not None and result[i-1] is not None:
                # RMA: result = (prev * (period-1) + current) / period
                result[i] = (result[i-1] * (period - 1) + data[i]) / period
        return result

    sm_tr   = wilder_smooth(tr_s,       14)
    sm_pdm  = wilder_smooth(plus_dm_s,  14)
    sm_mdm  = wilder_smooth(minus_dm_s, 14)

    pdi_s = [None] * n
    mdi_s = [None] * n
    dx_s  = [None] * n
    for i in range(n):
        if sm_tr[i] and sm_tr[i] > 0 and sm_pdm[i] is not None and sm_mdm[i] is not None:
            pdi_s[i] = 100 * sm_pdm[i] / sm_tr[i]
            mdi_s[i] = 100 * sm_mdm[i] / sm_tr[i]
            di_sum = pdi_s[i] + mdi_s[i]
            if di_sum > 0:
                dx_s[i] = 100 * abs(pdi_s[i] - mdi_s[i]) / di_sum

    adx_s = wilder_smooth([v if v is not None else None for v in dx_s], 14)

    # ── Performance ───────────────────────────────────────────────────────────
    last_close = closes[-1]
    prev_close = closes[-2] if n >= 2 else last_close
    chg_pct    = (last_close - prev_close) / prev_close * 100 if prev_close else 0

    perf_1w = ((last_close - closes[-6])  / closes[-6]  * 100) if n >= 6  else None
    perf_1m = ((last_close - closes[-22]) / closes[-22] * 100) if n >= 22 else None
    perf_3m = ((last_close - closes[-66]) / closes[-66] * 100) if n >= 66 else None

    hi52 = max(highs[-252:])  if n >= 252 else max(highs)
    lo52 = min(lows[-252:])   if n >= 252 else min(lows)

    # ── Swing high / low (recent structure — last 60 bars) ───────────────────
    recent_hi = max(highs[-60:])
    recent_lo = min(lows[-60:])

    # ── Helper to get last non-None value ────────────────────────────────────
    def last(series):
        for v in reversed(series):
            if v is not None:
                return v
        return None

    def prev(series, lookback=5):
        valid = [(i, v) for i, v in enumerate(series) if v is not None]
        if len(valid) < 2:
            return None
        return valid[-min(lookback, len(valid))][1]

    return {
        "price":       round(last_close, 2),
        "prev_close":  round(prev_close, 2),
        "chg_pct":     round(chg_pct, 2),
        "open":        round(bars[-1].get("open", 0), 2),
        "high":        round(bars[-1].get("high", 0), 2),
        "low":         round(bars[-1].get("low", 0), 2),
        "volume":      int(bars[-1].get("volume", 0)),
        "sma50":       round(last(sma50_s),  2) if last(sma50_s)  else None,
        "sma200":      round(last(sma200_s), 2) if last(sma200_s) else None,
        "ema50":       round(last(ema50_s),  2) if last(ema50_s)  else None,
        "sma50_prev":  round(prev(sma50_s),  2) if prev(sma50_s)  else None,
        "sma200_prev": round(prev(sma200_s), 2) if prev(sma200_s) else None,
        "macd":        round(last(macd_line_s), 4) if last(macd_line_s) is not None else None,
        "signal":      round(last(signal_s),    4) if last(signal_s)    is not None else None,
        "histogram":   round((last(macd_line_s) - last(signal_s)), 4)
                       if (last(macd_line_s) is not None and last(signal_s) is not None) else None,
        "macd_prev":   round(prev(macd_line_s), 4) if prev(macd_line_s) is not None else None,
        "signal_prev": round(prev(signal_s),    4) if prev(signal_s)    is not None else None,
        "hist_prev":   round(prev(macd_line_s) - prev(signal_s), 4)
                       if (prev(macd_line_s) is not None and prev(signal_s) is not None) else None,
        "rsi":         round(last(rsi_s),  1) if last(rsi_s)  is not None else None,
        "rsi_5ago":    round(prev(rsi_s, 5), 1) if prev(rsi_s, 5) is not None else None,
        "rsi_10ago":   round(prev(rsi_s, 10),1) if prev(rsi_s,10) is not None else None,
        "atr":         round(last(atr_s),  3) if last(atr_s)  is not None else None,
        "adx":         round(last(adx_s),  1) if last(adx_s)  is not None else None,
        "adx_prev":    round(prev(adx_s, 5), 1) if prev(adx_s, 5) is not None else None,
        "pdi":         round(last(pdi_s),  1) if last(pdi_s)  is not None else None,
        "mdi":         round(last(mdi_s),  1) if last(mdi_s)  is not None else None,
        "hi52":        round(hi52, 2),
        "lo52":        round(lo52, 2),
        "recent_hi":   round(recent_hi, 2),
        "recent_lo":   round(recent_lo, 2),
        "perf_1w":     round(perf_1w, 1) if perf_1w is not None else None,
        "perf_1m":     round(perf_1m, 1) if perf_1m is not None else None,
        "perf_3m":     round(perf_3m, 1) if perf_3m is not None else None,
        "bar_count":   n,
    }


# ── Step 3: Read S/R levels from drawn indicator ──────────────────────────────

def read_sr_levels(orc: TVOrchestrator, current_price: float) -> dict:
    """Read Support/Resistance drawn levels from the chart and cluster near price."""
    lines_data = orc.get_pine_lines(study_filter="Support/Resistance")
    all_levels = []

    if isinstance(lines_data, dict):
        for study in lines_data.get("studies", []):
            all_levels.extend([float(l) for l in study.get("horizontal_levels", []) if l])

    if not all_levels:
        all_lines = orc.get_pine_lines()
        if isinstance(all_lines, dict):
            for study in all_lines.get("studies", []):
                all_levels.extend([float(l) for l in study.get("horizontal_levels", []) if l])

    if not current_price or not all_levels:
        return {"resistance": [], "support": [], "all": []}

    # Only keep levels within 40% of current price (relevant context)
    relevant = [l for l in sorted(set(all_levels))
                if abs(l - current_price) / current_price <= 0.40]

    # Split into resistance (above) and support (below)
    resistance = sorted([l for l in relevant if l > current_price * 1.002])
    support    = sorted([l for l in relevant if l < current_price * 0.998], reverse=True)

    return {
        "resistance": resistance[:5],   # nearest 5 above
        "support":    support[:5],       # nearest 5 below
        "all":        relevant,
    }


# ── Step 4: Collect everything for one ticker ─────────────────────────────────

def collect_stock_data(orc: TVOrchestrator, ticker: str) -> dict:
    """Switch chart to ticker, set 2Y view, screenshot, pull all data."""
    print(f"\n  [{ticker}] Setting chart...")
    orc.set_symbol(ticker)
    time.sleep(3.0)   # wait for symbol data to fully load
    orc.set_timeframe("D")
    time.sleep(2.0)

    # Set visible range: Dec 1 2025 → 35 calendar days forward (shows full Forward Cloud)
    js_range = """(function() {
        try {
            var chart = window.TradingViewApi.activeChart();
            var dec1_2025 = Math.floor(new Date('2025-12-01T00:00:00Z').getTime() / 1000);
            var to = Math.floor(Date.now() / 1000) + 35 * 86400;
            chart.setVisibleRange({ from: dec1_2025, to: to });
            return JSON.stringify({success: true});
        } catch(e) { return JSON.stringify({error: e.message}); }
    })()"""
    orc._cli("ui", "eval", "--code", js_range)

    # Wait for chart to FULLY render — all indicators, cloud, S/R lines need time
    print(f"  [{ticker}] Waiting for full chart render...")
    time.sleep(5.0)

    # Re-apply range to ensure cloud redraws at the correct position
    orc._cli("ui", "eval", "--code", js_range)
    time.sleep(3.0)

    # Screenshot (full window — all panes)
    print(f"  [{ticker}] Screenshotting...")
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    shot_dst = SCREENSHOTS_DIR / f"{ticker}_{ts}.png"
    raw_path = orc.take_screenshot(region="full")
    screenshot = None
    if raw_path and "ERROR" not in str(raw_path).upper():
        p = Path(str(raw_path))
        if p.exists():
            # Crop out the OS window chrome (title bar, borders) and TV's dark frame
            # so the chart fills the full white PDF column cleanly
            try:
                from PIL import Image
                import numpy as np

                img = Image.open(p).convert("RGB")
                arr = np.array(img)          # shape: (height, width, 3)
                img_h, img_w = arr.shape[:2]

                # ── Find all 4 crop edges by scanning inward from each side ──
                # A pixel row/column is "content" if its average brightness > threshold
                THRESHOLD = 50   # dark TV chrome is RGB ~15,15,15 → brightness ~15

                def find_left(a, h, w):
                    for col in range(w):
                        brightness = a[h//4:3*h//4:5, col, :3].mean()
                        if brightness > THRESHOLD:
                            return max(0, col - 1)
                    return 0

                def find_right(a, h, w):
                    for col in range(w-1, w//2, -1):
                        brightness = a[h//4:3*h//4:5, col, :3].mean()
                        if brightness > THRESHOLD:
                            return min(w, col + 2)
                    return w

                def find_top(a, h, w):
                    for row in range(h):
                        brightness = a[row, w//4:3*w//4:5, :3].mean()
                        if brightness > THRESHOLD:
                            return max(0, row - 1)
                    return 0

                def find_bottom(a, h, w):
                    for row in range(h-1, h//2, -1):
                        brightness = a[row, w//4:3*w//4:5, :3].mean()
                        if brightness > THRESHOLD:
                            return min(h, row + 2)
                    return h

                left   = find_left(arr,   img_h, img_w)
                right  = find_right(arr,  img_h, img_w)
                top    = find_top(arr,    img_h, img_w)
                bottom = find_bottom(arr, img_h, img_w)

                # Sanity check — crop must be meaningful
                crop_w = right - left
                crop_h = bottom - top
                if crop_w < img_w * 0.5 or crop_h < img_h * 0.5:
                    # Scanner failed — fall back to known TV Desktop v3.1.0 values
                    left, top, right, bottom = 56, 42, img_w - 1, img_h - 1
                    print(f"  [{ticker}] Crop scanner gave bad result, using defaults")

                cropped = img.crop((left, top, right, bottom))
                cropped.save(str(shot_dst), "PNG")
                screenshot = str(shot_dst)
                print(f"  [{ticker}] Crop: L={left} T={top} R={right} B={bottom} -> {cropped.size[0]}x{cropped.size[1]}")

            except Exception as crop_err:
                print(f"  [{ticker}] Crop error, using fixed values")
                try:
                    from PIL import Image
                    import numpy as np
                    img = Image.open(p).convert("RGB")
                    arr2 = np.array(img)
                    h2, w2 = arr2.shape[:2]
                    # Scan right edge
                    right2 = w2 - 1
                    for col in range(w2-1, w2//2, -1):
                        if arr2[h2//4:3*h2//4:5, col, :3].mean() > 50:
                            right2 = min(w2, col + 2); break
                    # Scan bottom edge
                    bottom2 = h2 - 1
                    for row in range(h2-1, h2//2, -1):
                        if arr2[row, w2//4:3*w2//4:5, :3].mean() > 50:
                            bottom2 = min(h2, row + 2); break
                    img.crop((56, 42, right2, bottom2)).save(str(shot_dst), "PNG")
                    print(f"  [{ticker}] Fixed crop: 56,42 -> {right2},{bottom2}")
                    screenshot = str(shot_dst)
                except Exception:
                    shutil.copy2(p, shot_dst)
                    screenshot = str(shot_dst)

    # Get live quote
    quote = orc.get_quote()
    price = float(quote.get("close") or quote.get("last") or quote.get("price") or 0)

    # Pull 500 OHLCV bars from TV via CLI
    print(f"  [{ticker}] Pulling OHLCV bars from TradingView...")
    bars = fetch_ohlcv_bars(orc, bars=500)

    # Fallback to JS extraction if CLI returned no bars
    if len(bars) < 50:
        print(f"  [{ticker}] CLI bars sparse ({len(bars)}), trying JS extraction...")
        bars = fetch_bars_via_js(orc, bars=500)

    if len(bars) < 50:
        print(f"  [{ticker}] JS extraction also sparse ({len(bars)}), trying stream...")
        bars = fetch_bars_stream(orc, bars=500)

    print(f"  [{ticker}] Got {len(bars)} bars")

    # Calculate indicators
    ind = {}
    if len(bars) >= 50:
        ind = calc_indicators(bars)
        # Override price with live quote if available
        if price:
            ind["price"] = price
    else:
        # Fallback: build partial ind from quote only
        ind = {"price": price, "bar_count": len(bars)}

    # S/R levels
    sr = read_sr_levels(orc, ind.get("price", price))

    return {
        "ticker":     ticker,
        "screenshot": screenshot,
        "ind":        ind,
        "sr":         sr,
        "bars":       len(bars),
    }


# ── Step 5: Generate CMT-level prose analysis ─────────────────────────────────

def generate_analysis(ticker: str, data: dict) -> dict:
    """
    Generate institutional-grade CMT technical analysis from CDP data.
    Every section is real analytical prose — not just label/value pairs.
    """
    ind  = data.get("ind", {})
    sr   = data.get("sr", {})
    comp = COMPANY_MAP.get(ticker, ticker)

    price    = ind.get("price")
    sma50    = ind.get("sma50")
    sma200   = ind.get("sma200")
    ema50    = ind.get("ema50")
    macd     = ind.get("macd")
    signal   = ind.get("signal")
    hist     = ind.get("histogram")
    hist_p   = ind.get("hist_prev")
    macd_p   = ind.get("macd_prev")
    sig_p    = ind.get("signal_prev")
    rsi      = ind.get("rsi")
    rsi_5    = ind.get("rsi_5ago")
    rsi_10   = ind.get("rsi_10ago")
    adx      = ind.get("adx")
    adx_p    = ind.get("adx_prev")
    pdi      = ind.get("pdi")
    mdi      = ind.get("mdi")
    atr      = ind.get("atr")
    hi52     = ind.get("hi52")
    lo52     = ind.get("lo52")
    rec_hi   = ind.get("recent_hi")
    rec_lo   = ind.get("recent_lo")
    p1w      = ind.get("perf_1w")
    p1m      = ind.get("perf_1m")
    p3m      = ind.get("perf_3m")
    chg_pct  = ind.get("chg_pct")
    bar_count= ind.get("bar_count", 0)

    resistance = sr.get("resistance", [])
    support    = sr.get("support", [])

    def f(v, d=2): return f"{v:.{d}f}" if v is not None else "N/A"
    def pct(v):    return f"{v:+.1f}%" if v is not None else "N/A"
    def pc(v):     return f"{v:.1f}%"  if v is not None else "N/A"

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 1: TREND STRUCTURE
    # ══════════════════════════════════════════════════════════════════════════
    if price and sma50 and sma200:
        above50  = price > sma50
        above200 = price > sma200
        gc       = sma50 > sma200
        dist50   = (price - sma50)  / sma50  * 100
        dist200  = (price - sma200) / sma200 * 100
        pct_off_hi52 = (price - hi52) / hi52 * 100 if hi52 else None

        # Cross status
        if gc:
            cross_desc = "Golden Cross configuration (SMA50 above SMA200)"
        else:
            cross_desc = "Death Cross configuration (SMA50 below SMA200)"

        # Price-MA relationship narrative
        if above50 and above200:
            ma_rel = (f"Price is trading above both moving averages, with SMA50 at ${f(sma50)} "
                      f"({dist50:+.1f}%) and SMA200 at ${f(sma200)} ({dist200:+.1f}%), "
                      f"confirming intact primary uptrend structure.")
        elif above200 and not above50:
            ma_rel = (f"Price has retreated below SMA50 (${f(sma50)}, {dist50:+.1f}%) but "
                      f"remains above the critical SMA200 at ${f(sma200)} ({dist200:+.1f}%). "
                      f"This is a short-term correction within a longer-term uptrend — the SMA200 "
                      f"now represents key structural support.")
        elif not above200 and above50:
            ma_rel = (f"Price is trading above SMA50 (${f(sma50)}) but below SMA200 (${f(sma200)}, "
                      f"{dist200:+.1f}%), indicating a counter-trend bounce within a broader downtrend. "
                      f"SMA200 overhead resistance is the critical level to reclaim.")
        else:
            ma_rel = (f"Price is trading below both SMA50 (${f(sma50)}, {dist50:+.1f}%) and "
                      f"SMA200 (${f(sma200)}, {dist200:+.1f}%). Bearish trend structure is intact. "
                      f"Any rally must reclaim the SMA50 to signal a change in character.")

        # 52-week context
        hi52_context = ""
        if hi52 and pct_off_hi52:
            if pct_off_hi52 > -5:
                hi52_context = f" Price is within striking distance of its 52-week high (${f(hi52)}), indicating a potential breakout setup."
            elif pct_off_hi52 < -30:
                hi52_context = f" At ${f(price)}, the stock is {abs(pct_off_hi52):.0f}% off its 52-week high of ${f(hi52)}, reflecting significant technical damage."
            else:
                hi52_context = f" The 52-week range is ${f(lo52)}–${f(hi52)}; current price is {abs(pct_off_hi52):.0f}% below the annual high."

        trend_text = f"{cross_desc}. {ma_rel}{hi52_context}"
        trend_dir  = ("Bullish" if gc and above50 and above200 else
                      "Cautiously Bullish" if above200 else
                      "Bearish" if not gc and not above200 else "Neutral")

    else:
        trend_text = (f"{comp} is trading at ${f(price)}. "
                      f"Insufficient bar history to fully assess MA configuration "
                      f"({bar_count} bars retrieved from TradingView).")
        trend_dir  = "Neutral"

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 2: MOMENTUM (MACD)
    # ══════════════════════════════════════════════════════════════════════════
    if macd is not None and signal is not None and hist is not None:
        above_sig      = macd > signal
        hist_expanding = (hist_p is not None and abs(hist) > abs(hist_p))
        hist_direction = "expanding" if hist_expanding else "contracting"
        hist_sign      = "positive" if hist > 0 else "negative"

        # MACD crossover detection
        cross_signal = ""
        if macd_p is not None and sig_p is not None:
            was_above = macd_p > sig_p
            if not was_above and above_sig:
                cross_signal = " A bullish MACD crossover has recently occurred — a positive momentum shift signal."
            elif was_above and not above_sig:
                cross_signal = " A bearish MACD crossover has recently occurred — momentum is rotating lower."

        # Histogram narrative
        if hist > 0 and hist_expanding:
            hist_narr = (f"The histogram is {hist_sign} at {f(hist,3)} and expanding, "
                         f"indicating accelerating bullish momentum.")
        elif hist > 0 and not hist_expanding:
            hist_narr = (f"The histogram is {hist_sign} at {f(hist,3)} but contracting from {f(hist_p,3)}, "
                         f"suggesting bullish momentum is beginning to fade — watch for potential deceleration.")
        elif hist < 0 and hist_expanding:
            hist_narr = (f"The histogram is {hist_sign} at {f(hist,3)} and expanding in magnitude, "
                         f"indicating increasing bearish pressure.")
        else:
            hist_narr = (f"The histogram is {hist_sign} at {f(hist,3)} and contracting from {f(hist_p,3)}, "
                         f"suggesting bearish pressure is losing conviction — a potential base is forming.")

        momentum_text = (
            f"MACD line ({f(macd,3)}) is {'above' if above_sig else 'below'} the signal line ({f(signal,3)}), "
            f"placing momentum in a {'bullish' if above_sig else 'bearish'} configuration.{cross_signal} "
            f"{hist_narr}"
        )
        mom_bull = above_sig and (hist > 0)
        mom_bear = not above_sig and (hist < 0)

    else:
        momentum_text = "MACD data unavailable from TradingView — insufficient bar history."
        mom_bull = mom_bear = False

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 3: OSCILLATOR (RSI + DIVERGENCE)
    # ══════════════════════════════════════════════════════════════════════════
    if rsi is not None:
        # Zone classification
        if rsi >= 70:
            zone = "overbought territory (≥70)"
            zone_implication = ("This is not an automatic sell signal in a strong trend, but "
                                "it indicates elevated risk of a near-term pullback or consolidation.")
        elif rsi >= 60:
            zone = "bullish momentum zone (60–70)"
            zone_implication = ("This level is consistent with a healthy trend that has room to run "
                                "before reaching overbought conditions.")
        elif rsi >= 50:
            zone = "the neutral-to-bullish zone (50–60)"
            zone_implication = ("Momentum is constructive but not yet firmly trending. "
                                "A sustained move above 60 would confirm strengthening momentum.")
        elif rsi >= 40:
            zone = "the neutral-to-bearish zone (40–50)"
            zone_implication = ("RSI is below the midline, consistent with weak or corrective price action. "
                                "A reclaim of 50 is needed to shift momentum back to neutral.")
        elif rsi >= 30:
            zone = "the bearish momentum zone (30–40)"
            zone_implication = ("Momentum remains under pressure. Watch for any constructive base "
                                "formation or RSI hook back above 40.")
        else:
            zone = "oversold territory (≤30)"
            zone_implication = ("While not an automatic buy signal, oversold RSI readings "
                                "warrant attention for potential mean-reversion setups, "
                                "particularly if price shows a constructive reversal candle.")

        # Trend of RSI
        rsi_trend = ""
        if rsi_5 is not None:
            rsi_chg = rsi - rsi_5
            if rsi_chg > 5:
                rsi_trend = f" RSI has risen {rsi_chg:.1f} points over the past 5 sessions, reflecting improving momentum."
            elif rsi_chg < -5:
                rsi_trend = f" RSI has declined {abs(rsi_chg):.1f} points over the past 5 sessions, reflecting deteriorating momentum."
            else:
                rsi_trend = f" RSI is relatively stable over the past 5 sessions ({f(rsi_5,1)} → {f(rsi,1)})."

        # Divergence detection
        divergence = ""
        if rsi_10 is not None and price and ind.get("prev_close"):
            # Bearish divergence: price higher but RSI lower
            if rsi < rsi_10 and price > ind.get("prev_close", price) and rsi > 55:
                divergence = (" ⚠ Potential bearish RSI divergence is forming — price making higher highs "
                              "while RSI is declining. This is a warning sign of weakening internal momentum "
                              "and warrants close monitoring for a potential trend reversal.")
            # Bullish divergence: price lower but RSI higher
            elif rsi > rsi_10 and price < ind.get("prev_close", price) and rsi < 45:
                divergence = (" ✦ Potential bullish RSI divergence is developing — price making lower lows "
                              "while RSI is rising. This is a constructive sign that selling pressure "
                              "may be exhausting and a reversal could be developing.")

        oscillator_text = (
            f"RSI(14) is reading {f(rsi,1)}, placing the oscillator in {zone}. "
            f"{zone_implication}{rsi_trend}{divergence}"
        )

    else:
        oscillator_text = "RSI data unavailable from TradingView."

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 4: TREND STRENGTH (ADX)
    # ══════════════════════════════════════════════════════════════════════════
    if adx is not None and pdi is not None and mdi is not None:
        # ADX classification
        if adx >= 40:
            adx_class = "a very strong, well-defined trend"
            adx_action = "Trend-following strategies are favored; mean-reversion approaches carry elevated risk."
        elif adx >= 25:
            adx_class = "a trending environment"
            adx_action = "Directional trade positioning is supported by trend confirmation."
        elif adx >= 20:
            adx_class = "an emerging or weakening trend"
            adx_action = "Trend conviction is borderline — confirmation from price action and other indicators is required before committing to directional positions."
        else:
            adx_class = "a non-trending, range-bound environment"
            adx_action = "Trend-following approaches are discouraged. Range-trading and mean-reversion strategies are better suited to current conditions."

        # DI spread
        di_spread  = pdi - mdi
        di_bull    = pdi > mdi
        di_narr    = (f"+DI ({f(pdi,1)}) is {'above' if di_bull else 'below'} -DI ({f(mdi,1)}), "
                      f"with a spread of {abs(di_spread):.1f} points confirming "
                      f"{'bullish' if di_bull else 'bearish'} directional bias.")

        # ADX trend (is it rising or falling?)
        adx_trend = ""
        if adx_p is not None:
            adx_chg = adx - adx_p
            if adx_chg > 2:
                adx_trend = f" ADX is rising (+{adx_chg:.1f} from {f(adx_p,1)}), indicating the trend is gaining strength."
            elif adx_chg < -2:
                adx_trend = f" ADX is declining ({adx_chg:.1f} from {f(adx_p,1)}), suggesting trend momentum is fading — potential consolidation or reversal ahead."
            else:
                adx_trend = f" ADX is relatively flat, suggesting trend strength is stable."

        strength_text = (
            f"ADX(14) at {f(adx,1)} reflects {adx_class}. {di_narr}{adx_trend} "
            f"{adx_action}"
        )

    else:
        strength_text = "ADX data unavailable from TradingView."

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 5: KEY LEVELS
    # ══════════════════════════════════════════════════════════════════════════
    if price and (resistance or support):
        level_lines = []

        # Resistance levels
        if resistance:
            r1 = resistance[0]
            r1_pct = (r1 - price) / price * 100
            r_desc = f"Immediate resistance is at ${f(r1)} ({r1_pct:+.1f}%)"
            if len(resistance) >= 2:
                r2 = resistance[1]
                r2_pct = (r2 - price) / price * 100
                r_desc += f", with secondary resistance at ${f(r2)} ({r2_pct:+.1f}%)"
            level_lines.append(r_desc + ".")

        # Support levels
        if support:
            s1 = support[0]
            s1_pct = (s1 - price) / price * 100
            s_desc = f"Nearest support sits at ${f(s1)} ({s1_pct:.1f}%)"
            if len(support) >= 2:
                s2 = support[1]
                s2_pct = (s2 - price) / price * 100
                s_desc += f", with secondary support at ${f(s2)} ({s2_pct:.1f}%)"
            level_lines.append(s_desc + ".")

        # ATR context (risk sizing)
        atr_context = ""
        if atr:
            atr_pct = atr / price * 100
            atr_context = (f" ATR(14) is ${f(atr,2)} ({atr_pct:.1f}% of price), "
                           f"providing a daily volatility benchmark for position sizing and stop placement.")

        # 52-week range anchor
        range_context = (f" The 52-week range (${f(lo52)}–${f(hi52)}) "
                         f"provides the primary structural framework.")

        levels_text = " ".join(level_lines) + atr_context + range_context

    else:
        atr_context = f" ATR(14): ${f(atr,2)}." if atr else ""
        levels_text = (f"52-week range: ${f(lo52)}–${f(hi52)}.{atr_context} "
                       f"S/R levels are drawn directly on the chart via the Support/Resistance indicator.")

    # ══════════════════════════════════════════════════════════════════════════
    # ANALYST BIAS + CONVICTION
    # ══════════════════════════════════════════════════════════════════════════
    score = 0
    factors = []

    if sma50 and sma200:
        if sma50 > sma200: score += 2; factors.append("Golden Cross")
        else:              score -= 2; factors.append("Death Cross")
    if price and sma200:
        if price > sma200: score += 1; factors.append("Above SMA200")
        else:              score -= 1; factors.append("Below SMA200")
    if price and sma50:
        if price > sma50:  score += 1; factors.append("Above SMA50")
        else:              score -= 1; factors.append("Below SMA50")
    if macd is not None and signal is not None:
        if macd > signal:  score += 1; factors.append("MACD Bullish")
        else:              score -= 1; factors.append("MACD Bearish")
    if hist is not None and hist_p is not None:
        if hist > 0 and abs(hist) > abs(hist_p): score += 1; factors.append("Momentum Building")
        elif hist < 0 and abs(hist) > abs(hist_p): score -= 1; factors.append("Momentum Weakening")
    if rsi is not None:
        if rsi > 55:   score += 1; factors.append(f"RSI Bullish ({f(rsi,1)})")
        elif rsi < 45: score -= 1; factors.append(f"RSI Bearish ({f(rsi,1)})")
    if pdi is not None and mdi is not None:
        if pdi > mdi:  score += 1; factors.append("+DI > -DI")
        else:          score -= 1; factors.append("-DI > +DI")
    if adx is not None and adx >= 25:
        if score > 0: score += 1; factors.append("ADX Trend Confirmed")
        else:         score -= 1

    max_score = 9
    if score >= 5:
        bias = "BULLISH"; conviction = "HIGH"
    elif score >= 3:
        bias = "BULLISH"; conviction = "MEDIUM"
    elif score >= 1:
        bias = "CAUTIOUSLY BULLISH"; conviction = "LOW"
    elif score == 0:
        bias = "NEUTRAL"; conviction = "LOW"
    elif score >= -2:
        bias = "CAUTIOUSLY BEARISH"; conviction = "LOW"
    elif score >= -4:
        bias = "BEARISH"; conviction = "MEDIUM"
    else:
        bias = "BEARISH"; conviction = "HIGH"

    # Weekly context line
    weekly_parts = []
    if p1w is not None:  weekly_parts.append(f"1W: {pct(p1w)}")
    if p1m is not None:  weekly_parts.append(f"1M: {pct(p1m)}")
    if p3m is not None:  weekly_parts.append(f"3M: {pct(p3m)}")
    perf_str = "  ·  ".join(weekly_parts) if weekly_parts else ""

    # One-line action statement for bias box
    bias_summary_map = {
        "BULLISH":            "Structural and momentum signals are broadly aligned to the upside. Trend-following long bias is supported.",
        "CAUTIOUSLY BULLISH": "Bullish structural setup with caveats. Confirm on volume or wait for MA reclaim before adding exposure.",
        "NEUTRAL":            "Mixed signals — no clear directional edge. Monitor for resolution above/below key MAs before committing.",
        "CAUTIOUSLY BEARISH": "Bearish signals are emerging but not fully confirmed. Reduce exposure on rallies; watch key support.",
        "BEARISH":            "Trend, momentum, and oscillator signals are broadly aligned to the downside. Defensive positioning warranted.",
    }
    bias_summary = bias_summary_map.get(bias, "")

    # ══════════════════════════════════════════════════════════════════════════
    # TECHNICAL SUMMARY — evidence-based synthesis of entire technical posture
    # ══════════════════════════════════════════════════════════════════════════
    # Build a 3-sentence paragraph that ties together every section above
    # into a coherent picture of where this stock stands technically.

    # Sentence 1: Structural foundation
    if price and sma50 and sma200:
        gc = sma50 > sma200
        above50 = price > sma50
        above200 = price > sma200
        if gc and above50 and above200:
            s1 = (f"{comp} is in a structurally sound uptrend — the Golden Cross (SMA50 at "
                  f"${f(sma50)} above SMA200 at ${f(sma200)}) is intact and price is trading "
                  f"above both moving averages, confirming primary trend health.")
        elif gc and not above50 and above200:
            s1 = (f"{comp} remains within a larger uptrend (Golden Cross intact, SMA200 at "
                  f"${f(sma200)} acting as foundational support at {(price-sma200)/sma200*100:+.1f}%), "
                  f"but has pulled back below SMA50 (${f(sma50)}), indicating a short-term corrective "
                  f"phase that has not yet broken the primary trend.")
        elif not gc and above200:
            s1 = (f"{comp}'s SMA50 (${f(sma50)}) has crossed below SMA200 (${f(sma200)}), "
                  f"signalling a shift in intermediate trend — however, price continues to hold "
                  f"above the SMA200, leaving the long-term structure at a critical inflection point.")
        else:
            s1 = (f"{comp} is trading below both SMA50 (${f(sma50)}) and SMA200 (${f(sma200)}) "
                  f"with a Death Cross in effect, placing the stock in a confirmed intermediate downtrend "
                  f"with no structural support from either primary moving average.")
    else:
        s1 = f"{comp} is trading at ${f(price)} with limited MA history available."

    # Sentence 2: Momentum and oscillator convergence
    mom_rsi_parts = []
    if macd is not None and signal is not None:
        macd_above = macd > signal
        hist_exp   = hist is not None and hist_p is not None and abs(hist) > abs(hist_p)
        if macd_above and hist_exp:
            mom_rsi_parts.append("MACD is in a bullish crossover with an expanding histogram — momentum is accelerating to the upside")
        elif macd_above and not hist_exp:
            mom_rsi_parts.append("MACD is in a bullish configuration but the histogram is contracting, suggesting momentum is present but fading")
        elif not macd_above and hist_exp:
            mom_rsi_parts.append("MACD is in a bearish crossover with expanding negative histogram — selling momentum is building")
        else:
            mom_rsi_parts.append("MACD is bearish but histogram compression suggests the downside momentum may be exhausting")

    if rsi is not None:
        if rsi >= 70:
            mom_rsi_parts.append(f"RSI at {f(rsi,1)} is in overbought territory, elevating near-term pullback risk")
        elif rsi >= 60:
            mom_rsi_parts.append(f"RSI at {f(rsi,1)} is in the bullish momentum zone with room before overbought")
        elif rsi >= 50:
            mom_rsi_parts.append(f"RSI at {f(rsi,1)} sits just above the midline — momentum is positive but not yet strong")
        elif rsi >= 40:
            mom_rsi_parts.append(f"RSI at {f(rsi,1)} is below the 50 midline, reflecting a weak momentum environment")
        else:
            mom_rsi_parts.append(f"RSI at {f(rsi,1)} is in oversold territory, creating a potential mean-reversion opportunity")

    if len(mom_rsi_parts) == 2:
        s2 = f"On the momentum and oscillator front, {mom_rsi_parts[0]}; {mom_rsi_parts[1]}."
    elif mom_rsi_parts:
        s2 = f"Momentum indicators show {mom_rsi_parts[0]}."
    else:
        s2 = ""

    # Sentence 3: Trend strength + actionable conclusion
    if adx is not None and pdi is not None and mdi is not None:
        adx_rising = adx_p is not None and adx > adx_p
        di_bull    = pdi > mdi

        if adx >= 25 and di_bull and adx_rising:
            s3 = (f"ADX at {f(adx,1)} and rising confirms a strengthening uptrend with +DI ({f(pdi,1)}) "
                  f"leading -DI ({f(mdi,1)}) — trend-following positioning is well-supported. "
                  f"The weight of evidence across all indicators points to a {bias.lower()} technical posture "
                  f"with {conviction.lower()} conviction.")
        elif adx >= 25 and not di_bull:
            s3 = (f"ADX at {f(adx,1)} confirms a trending environment, but -DI ({f(mdi,1)}) is above "
                  f"+DI ({f(pdi,1)}), meaning the trend energy is pointed lower. "
                  f"On balance, the technical posture is {bias.lower()} with {conviction.lower()} conviction — "
                  f"caution is warranted on long positioning until DI alignment improves.")
        elif adx < 20:
            s3 = (f"ADX at {f(adx,1)} is below the trend threshold, indicating a non-trending, "
                  f"range-bound environment where directional signals carry less reliability. "
                  f"Overall technical posture is assessed as {bias.lower()} with {conviction.lower()} conviction, "
                  f"but patience for trend confirmation is advised before acting.")
        else:
            s3 = (f"ADX at {f(adx,1)} reflects an emerging trend. On aggregate, the technical evidence "
                  f"supports a {bias.lower()} bias with {conviction.lower()} conviction.")
    else:
        s3 = (f"On the overall evidence, the technical posture for {comp} is assessed as "
              f"{bias.lower()} with {conviction.lower()} conviction.")

    technical_summary = f"{s1} {s2} {s3}"

    # ══════════════════════════════════════════════════════════════════════════
    # TREND + MA SUITE — combined into one section
    # ══════════════════════════════════════════════════════════════════════════
    trend_ma_parts = [trend_text]  # start with existing trend structure

    if price and sma50 and sma200:
        # Stack alignment bonus scoring
        if price > sma50 > sma200:
            trend_ma_parts.append("MA Stack: FULL BULL — Price > SMA50 > SMA200, all layers aligned upward.")
            score += 1; factors.append("Bull Stack")
        elif price < sma50 < sma200:
            trend_ma_parts.append("MA Stack: FULL BEAR — Price < SMA50 < SMA200, all layers aligned downward.")
            score -= 1; factors.append("Bear Stack")
        elif sma50 > sma200 and price < sma50:
            trend_ma_parts.append(f"MA Stack: Corrective — Golden Cross intact but price pulled below SMA50 ${f(sma50)}. SMA200 ${f(sma200)} remains long-term anchor.")
        elif sma50 < sma200 and price > sma50:
            trend_ma_parts.append(f"MA Stack: Counter-trend — Death Cross in effect, price bouncing above SMA50. SMA200 ${f(sma200)} is overhead resistance.")

        # Slope context
        if sma200:
            d200 = (price - sma200) / sma200 * 100
            d50  = (price - sma50)  / sma50  * 100
            trend_ma_parts.append(
                f"Distance from key MAs: SMA50 {d50:+.1f}%  ·  SMA200 {d200:+.1f}%. "
                f"{'SMA200 acting as support.' if price > sma200 else 'SMA200 acting as resistance.'}"
            )

    trend_ma_text = " ".join(trend_ma_parts)

    # ══════════════════════════════════════════════════════════════════════════
    # 20-DAY FORWARD CLOUD FORECAST
    # References the composite cloud posture and which active signals are driving it
    # ══════════════════════════════════════════════════════════════════════════
    cloud_parts = []

    # Identify which signals are currently active (fired recently)
    active_signals = []
    if macd is not None and signal is not None:
        if macd > signal:
            active_signals.append("MACD_BULL_CROSS" if (macd_p is not None and macd_p <= sig_p) else "MACD_BULL")
        else:
            active_signals.append("MACD_BEAR_CROSS" if (macd_p is not None and macd_p >= sig_p) else "MACD_BEAR")
        if hist is not None and hist > 0 and hist_p is not None and abs(hist) > abs(hist_p):
            active_signals.append("MACD_HIST_EXPAND_BULL")
        elif hist is not None and hist < 0 and hist_p is not None and abs(hist) > abs(hist_p):
            active_signals.append("MACD_HIST_EXPAND_BEAR")
    if rsi is not None:
        if rsi < 30:  active_signals.append("RSI_OS_EXIT" if rsi_5 and rsi > rsi_5 else "RSI_OS_ENTRY")
        elif rsi > 70: active_signals.append("RSI_OB_ENTRY")
        elif rsi > 50: active_signals.append("RSI_MID_UP")
        else:          active_signals.append("RSI_MID_DOWN")
    if pdi is not None and mdi is not None:
        if pdi > mdi: active_signals.append("ADX_DI_BULL")
        else:         active_signals.append("ADX_DI_BEAR")
    if adx is not None and adx > 20:
        active_signals.append(f"ADX_TREND_START" if adx_p and adx > adx_p else "ADX_TRENDING")

    sig_str = ", ".join(active_signals[:5]) if active_signals else "no dominant signal"

    # Cloud direction based on overall signal posture
    if score >= 3:
        cloud_dir = "bullish"
        cloud_desc = (
            f"The Composite Forward Cloud is projecting a BULLISH 20-day trajectory from current price ${f(price)}. "
            f"Active signals driving this posture: {sig_str}. "
            f"The cloud's mean path targets the ${'...'} zone; the p75 band defines the upside scenario. "
            f"Key levels to watch on the upside: SMA resistance and recent swing highs. "
            f"The cloud will reprice on each new bar — if momentum signals deteriorate, expect the cloud to flatten."
        )
    elif score <= -3:
        cloud_dir = "bearish"
        cloud_desc = (
            f"The Composite Forward Cloud is projecting a BEARISH 20-day trajectory from current price ${f(price)}. "
            f"Active signals driving this posture: {sig_str}. "
            f"The p25 band defines the downside risk scenario. "
            f"Key support levels: SMA200 ${f(sma200)} and recent swing lows. "
            f"A close back above SMA50 ${f(sma50)} would invalidate the bearish cloud posture."
        )
    else:
        cloud_dir = "neutral/consolidating"
        cloud_desc = (
            f"The Composite Forward Cloud is projecting a NEUTRAL to CONSOLIDATING 20-day outlook from ${f(price)}. "
            f"Active signals: {sig_str}. "
            f"The cloud bands are relatively compressed — the market is in a signal-waiting mode. "
            f"Watch for: RSI crossing 50 (bullish), MACD crossover, or price reclaiming SMA50 ${f(sma50)} to shift the cloud bullish. "
            f"Conversely, a break below SMA200 ${f(sma200)} with expanding ADX would shift the cloud bearish."
        )

    # Add specific level targets from the cloud (using SMA and recent structure as proxy)
    if hi52 and lo52 and price:
        pct_hi = (price - hi52) / hi52 * 100
        if pct_hi > -8:
            cloud_desc += f" Near-term target: a retest of the 52W high ${f(hi52)} is within the p75 cloud band."
        if sma50 and abs(price - sma50) / sma50 < 0.05:
            cloud_desc += f" SMA50 ${f(sma50)} is the pivot — cloud posture shifts on which side price resolves."

    cloud_text = cloud_desc

    return {
        "ticker":       ticker,
        "company":      comp,
        "price":        price,
        "chg_pct":      chg_pct,
        "trend_ma":     trend_ma_text,
        "cloud_forecast": cloud_text,
        "momentum":     momentum_text,
        "oscillator":   oscillator_text,
        "technical_summary": technical_summary,
        "strength":     strength_text,
        "levels":       levels_text,
        "bias":         bias,
        "conviction":   conviction,
        "score":        score,
        "factors":      factors,
        "bias_summary": bias_summary,
        "perf_str":     perf_str,
        "perf_1w":      p1w,
        "perf_1m":      p1m,
        "perf_3m":      p3m,
        "bar_count":    bar_count,
    }


# ── Step 6: Build landscape PDF ───────────────────────────────────────────────

def build_pdf(stocks: list[dict], output_path: Path) -> None:
    """Landscape A4 — left half chart, right half CMT analysis prose."""
    try:
        from reportlab.lib.pagesizes import landscape, A4
        from reportlab.lib.units import mm
        from reportlab.lib import colors
        from reportlab.pdfgen import canvas
    except ImportError:
        print("pip install reportlab")
        return

    PAGE_W, PAGE_H = landscape(A4)
    MARGIN    = 5 * mm    # halved — fills more white space
    HEADER_H  = 12 * mm   # compact dark title band
    SUB_H     = 8  * mm   # single-line company/meta header
    HALF_W    = (PAGE_W - 2 * MARGIN - 4 * mm) / 2
    CHART_TOP = PAGE_H - MARGIN - HEADER_H - SUB_H - 1 * mm

    BLACK      = colors.HexColor('#000000')
    DARK       = colors.HexColor('#1A1A1A')
    DGREY      = colors.HexColor('#333333')
    MGREY      = colors.HexColor('#555555')
    LGREY      = colors.HexColor('#888888')
    XLGREY     = colors.HexColor('#CCCCCC')
    VLIGHT     = colors.HexColor('#F7F7F7')
    WHITE      = colors.white
    GOLD       = colors.HexColor('#B8860B')  # dark gold for accent

    class ReportCanvas(canvas.Canvas):
        def __init__(self, filename, stocks_list, **kwargs):
            super().__init__(filename, **kwargs)
            self._stocks = stocks_list
            self._page_idx = 0

        def showPage(self):
            if self._page_idx < len(self._stocks):
                self._render_page(self._stocks[self._page_idx])
                self._page_idx += 1
            super().showPage()

        def save(self):
            super().save()

        def _render_page(self, stock):
            a = stock.get("analysis", {})
            ticker  = a.get("ticker", "")
            company = a.get("company", "")
            price   = a.get("price")
            chg     = a.get("chg_pct")
            p1w     = a.get("perf_1w")
            p1m     = a.get("perf_1m")
            exch    = EXCHANGE_MAP.get(ticker, "NYSE")
            bc      = a.get("bar_count", 0)

            # ── Header bar — title sits INSIDE the dark band ─────────────────
            hdr_top = PAGE_H - MARGIN          # top of header band
            hdr_bot = hdr_top - HEADER_H       # bottom of header band
            self.setFillColor(DARK)
            self.rect(MARGIN, hdr_bot, PAGE_W - 2*MARGIN, HEADER_H, fill=1, stroke=0)

            # Title text — vertically centred inside the dark band
            title_y    = hdr_bot + HEADER_H * 0.55   # upper half of band
            subtitle_y = hdr_bot + HEADER_H * 0.20   # lower half of band

            self.setFillColor(WHITE)
            self.setFont("Helvetica-Bold", 10.5)
            self.drawString(MARGIN + 3*mm, title_y, REPORT_TITLE)

            self.setFont("Helvetica", 8)
            self.drawRightString(PAGE_W - MARGIN - 3*mm, title_y,
                                 f"Week of {REPORT_DATE}")

            self.setFillColor(colors.HexColor('#AAAAAA'))
            self.setFont("Helvetica-Oblique", 7)
            self.drawString(MARGIN + 3*mm, subtitle_y, REPORT_SUBTITLE)

            # ── Company sub-header — ticker + meta on SAME LINE ───────────────
            y_sub = hdr_bot - 6*mm   # just below the header band
            self.setFillColor(DARK)
            self.setFont("Helvetica-Bold", 11)

            # Build meta string for same-line placement
            price_str = f"${price:.2f}" if price else "N/A"
            chg_str   = f" ({chg:+.2f}%)" if chg is not None else ""
            p1w_str   = f"  1W: {p1w:+.1f}%" if p1w is not None else ""
            p1m_str   = f"  1M: {p1m:+.1f}%" if p1m is not None else ""
            meta      = f"  ·  {exch}  ·  Daily  ·  {price_str}{chg_str}{p1w_str}{p1m_str}"

            # Draw ticker+company in bold, then meta inline in grey
            ticker_label = f"{ticker}  —  {company}"
            self.drawString(MARGIN, y_sub, ticker_label)
            ticker_w = self.stringWidth(ticker_label, "Helvetica-Bold", 11)
            self.setFont("Helvetica", 8)
            self.setFillColor(MGREY)
            self.drawString(MARGIN + ticker_w + 2*mm, y_sub + 0.8*mm, meta)

            # Thin divider line
            self.setStrokeColor(XLGREY)
            self.setLineWidth(0.3)
            self.line(MARGIN, y_sub - 2.5*mm, PAGE_W - MARGIN, y_sub - 2.5*mm)

            # ── CHART (left half) — fills full column, no border ────────────────
            img_path = stock.get("screenshot")
            chart_h  = CHART_TOP - MARGIN - 2*mm
            chart_x  = MARGIN
            chart_w  = HALF_W

            if img_path and Path(img_path).exists():
                # Fill the entire chart column — stretch to fit, no border, no outline
                self.setStrokeColor(WHITE)  # ensure no outline drawn around image
                self.setLineWidth(0)
                self.drawImage(img_path, chart_x, MARGIN + 2*mm,
                               width=chart_w, height=chart_h,
                               preserveAspectRatio=False,  # fill full column
                               anchor='sw',
                               mask='auto')                # strips any transparent edges
            else:
                # Placeholder — white background, no border
                self.setFillColor(WHITE)
                self.rect(chart_x, MARGIN + 2*mm, chart_w, chart_h,
                          fill=1, stroke=0)  # stroke=0 removes black outline
                self.setFillColor(MGREY)
                self.setFont("Helvetica", 9)
                self.drawCentredString(chart_x + chart_w/2,
                                       MARGIN + 2*mm + chart_h/2,
                                       "Launch TV Desktop for live chart screenshot")
                self.setFont("Helvetica-Oblique", 7)
                self.drawCentredString(chart_x + chart_w/2,
                                       MARGIN + 2*mm + chart_h/2 - 5*mm,
                                       "scripts\\launch_tv_windows.bat → rerun report")

            # Chart footnote — indicators shown
            self.setFillColor(LGREY)
            self.setFont("Helvetica-Oblique", 6.5)
            self.drawString(chart_x, MARGIN - 0.5*mm,
                            f"{ticker} · Daily · 18M+Cloud · OBQ-MA · OBQ-MACD · OBQ-RSI · OBQ-ADX · OBQ-SR · Forward Cloud · TradingView")

            # ── ANALYSIS (right half) ─────────────────────────────────────────
            ax   = MARGIN + HALF_W + 5*mm
            aw   = HALF_W - 2*mm
            cy   = CHART_TOP  # current y, drawing downward

            def section_hdr(label, y):
                """Draw a section header with a thin rule below."""
                y -= 1*mm
                self.setFillColor(DARK)
                self.setFont("Helvetica-Bold", 7)
                self.drawString(ax, y, label)
                y -= 2.2*mm
                self.setStrokeColor(XLGREY)
                self.setLineWidth(0.25)
                self.line(ax, y, ax + aw, y)
                return y - 2.5*mm

            def body(text, y, size=7.8, line_h=3.6, color=DGREY):
                """Word-wrap text block, return new y."""
                if not text:
                    return y
                self.setFillColor(color)
                self.setFont("Helvetica", size)
                words = str(text).split()
                line  = ""
                for word in words:
                    test = (line + " " + word).strip()
                    if self.stringWidth(test, "Helvetica", size) <= aw:
                        line = test
                    else:
                        if line:
                            self.drawString(ax, y, line)
                            y -= line_h * mm
                        line = word
                        if y < MARGIN + 20*mm:
                            break  # don't overflow into bias box
                if line and y >= MARGIN + 20*mm:
                    self.drawString(ax, y, line)
                    y -= line_h * mm
                return y - 0.8*mm

            sections = [
                ("▌ TREND & MA STRUCTURE  (SMA20 · SMA50 · SMA200 · Stack)", a.get("trend_ma",        "")),
                ("▌ 20-DAY FORWARD CLOUD FORECAST  (Composite Signal Posture)", a.get("cloud_forecast", "")),
                ("▌ MOMENTUM  (MACD 12,26,9)",                                a.get("momentum",        "")),
                ("▌ OSCILLATOR  (RSI 14 · Divergences)",                      a.get("oscillator",      "")),
                ("▌ TREND STRENGTH  (ADX 14 · +DI / -DI)",                   a.get("strength",        "")),
                ("▌ KEY LEVELS  (S/R · 52W Range · ATR)",                     a.get("levels",          "")),
                ("▌ TECHNICAL SUMMARY",                                        a.get("technical_summary","")),
            ]

            for hdr_label, content in sections:
                cy = section_hdr(hdr_label, cy)
                cy = body(content, cy)
                cy -= 0.5*mm

            # ── Bias box ──────────────────────────────────────────────────────
            bias       = a.get("bias", "NEUTRAL")
            conviction = a.get("conviction", "LOW")
            summary    = a.get("bias_summary", "")
            factors    = a.get("factors", [])
            perf_str   = a.get("perf_str", "")

            box_h  = 18*mm
            box_y  = MARGIN + 1*mm
            # Dark header band inside bias box
            self.setFillColor(DARK)
            self.rect(ax, box_y + box_h - 7*mm, aw, 7*mm, fill=1, stroke=0)
            # Box border
            self.setStrokeColor(DARK)
            self.setLineWidth(1)
            self.rect(ax, box_y, aw, box_h, fill=0, stroke=1)

            # Bias label in header band
            self.setFillColor(WHITE)
            self.setFont("Helvetica-Bold", 9)
            self.drawString(ax + 3*mm, box_y + box_h - 5*mm,
                            f"ANALYST BIAS:  {bias}  [{conviction} CONVICTION]")

            # Performance pills
            if perf_str:
                self.setFont("Helvetica", 7)
                self.setFillColor(colors.HexColor('#AAAAAA'))
                self.drawRightString(ax + aw - 2*mm,
                                     box_y + box_h - 5*mm, perf_str)

            # Summary text
            self.setFillColor(DGREY)
            self.setFont("Helvetica", 7.5)
            words = summary.split()
            line  = ""
            sy    = box_y + box_h - 9.5*mm
            for word in words:
                test = (line + " " + word).strip()
                if self.stringWidth(test, "Helvetica", 7.5) <= aw - 6*mm:
                    line = test
                else:
                    self.drawString(ax + 3*mm, sy, line)
                    sy -= 3.2*mm
                    line = word
            if line:
                self.drawString(ax + 3*mm, sy, line)

            # Factor pills
            if factors:
                fx = ax + 3*mm
                fy = box_y + 2*mm
                self.setFont("Helvetica", 6)
                for fac in factors[:6]:
                    fw = self.stringWidth(fac, "Helvetica", 6) + 4*mm
                    if fx + fw > ax + aw - 2*mm:
                        break
                    self.setFillColor(VLIGHT)
                    self.setStrokeColor(XLGREY)
                    self.setLineWidth(0.3)
                    self.roundRect(fx, fy, fw, 3.5*mm, 1*mm, fill=1, stroke=1)
                    self.setFillColor(DGREY)
                    self.drawString(fx + 2*mm, fy + 1*mm, fac)
                    fx += fw + 2*mm

            # CMT footnote
            self.setFillColor(XLGREY)
            self.setFont("Helvetica-Oblique", 6)
            self.drawRightString(
                PAGE_W - MARGIN, MARGIN - 1.5*mm,
                "For professional use only. Not investment advice. GoldenOpp Research · CMT Analysis"
            )

    # ── Write the PDF ─────────────────────────────────────────────────────────
    c = ReportCanvas(str(output_path), stocks_list=stocks, pagesize=landscape(A4))
    for _ in stocks:
        c.showPage()
    # Appendix pages
    _render_appendix(c, PAGE_W, PAGE_H, MARGIN, HEADER_H, mm, colors,
                     DARK, DGREY, MGREY, LGREY, XLGREY, VLIGHT, WHITE)
    c.save()
    print(f"\n  PDF: {output_path}")



def _render_appendix(c, PW, PH, MAR, HDR_H, mm, colors,
                     DARK, DG, MG, LG, XG, VL, WH):
    """
    Render 3 clean landscape appendix pages.
    Single-column layout — no coordinate mixing, no overflow.
    Each page uses one y-cursor that only moves downward.
    """
    from reportlab.lib import colors as _c

    DBLUE  = _c.HexColor('#1a3a5c')
    LGREY  = _c.HexColor('#888888')
    XLGREY = _c.HexColor('#CCCCCC')
    VLIGHT = _c.HexColor('#F7F7F7')
    ACCENT = _c.HexColor('#B8860B')

    BODY_X = MAR                        # left edge of text
    BODY_W = PW - 2 * MAR               # full width
    STOP_Y = MAR + 14 * mm              # never draw below this (disclaimer zone)

    # ── Primitive helpers — all take/return y, only move downward ─────────────

    def page_header(title, subtitle):
        """Draw the dark top band. Returns y just below the band."""
        hdr_bot = PH - MAR - HDR_H
        c.setFillColor(DARK)
        c.rect(MAR, hdr_bot, PW - 2*MAR, HDR_H, fill=1, stroke=0)
        title_y = hdr_bot + HDR_H * 0.58
        sub_y   = hdr_bot + HDR_H * 0.22
        c.setFillColor(WH);      c.setFont("Helvetica-Bold", 10.5)
        c.drawString(MAR + 3*mm, title_y, "GoldenOpp Research — Weekly Technical Analysis")
        c.setFont("Helvetica", 8)
        c.drawRightString(PW - MAR - 3*mm, title_y, f"Appendix  |  {REPORT_DATE}")
        c.setFillColor(_c.HexColor('#AAAAAA')); c.setFont("Helvetica-Oblique", 7)
        c.drawString(MAR + 3*mm, sub_y, subtitle)
        return hdr_bot - 4*mm   # y to start content from

    def section_bar(label, y):
        """Full-width dark section label bar. Returns y below it."""
        if y < STOP_Y + 10*mm: return y
        bar_h = 6*mm
        c.setFillColor(DBLUE)
        c.rect(BODY_X, y - bar_h + 1*mm, BODY_W, bar_h, fill=1, stroke=0)
        c.setFillColor(WH); c.setFont("Helvetica-Bold", 8)
        c.drawString(BODY_X + 3*mm, y - 3.5*mm, label)
        return y - bar_h - 2*mm

    def write_para(text, y, size=7.8, line_h=3.7, indent=0, bold=False,
                   color=None, width=None):
        """Word-wrap a paragraph. Returns y after last line."""
        if y < STOP_Y: return y
        if color is None: color = DG
        if width is None: width = BODY_W - indent
        font = "Helvetica-Bold" if bold else "Helvetica"
        c.setFillColor(color); c.setFont(font, size)
        x = BODY_X + indent
        words = str(text).split(); line = ""
        for word in words:
            test = (line + " " + word).strip()
            if c.stringWidth(test, font, size) <= width:
                line = test
            else:
                if line and y >= STOP_Y:
                    c.drawString(x, y, line)
                    y -= line_h * mm
                line = word
        if line and y >= STOP_Y:
            c.drawString(x, y, line)
            y -= line_h * mm
        return y - 1*mm

    def write_bullet(label, body, y):
        """Bold label + body text as a bullet item."""
        if y < STOP_Y + 5*mm: return y
        # Bold label on its own line
        c.setFillColor(DBLUE); c.setFont("Helvetica-Bold", 7.6)
        c.drawString(BODY_X + 4*mm, y, label)
        y -= 3.8*mm
        # Body indented
        y = write_para(body, y, size=7.4, line_h=3.5, indent=6*mm)
        return y - 0.5*mm

    def write_numbered(num, title, body, y):
        """Numbered step box with title and description."""
        if y < STOP_Y + 12*mm: return y
        box_h = 11*mm
        c.setFillColor(VLIGHT)
        c.rect(BODY_X, y - box_h, BODY_W, box_h, fill=1, stroke=0)
        c.setStrokeColor(DBLUE); c.setLineWidth(0.4)
        c.line(BODY_X, y - box_h, BODY_X, y)             # left accent line
        c.setFillColor(DBLUE); c.setFont("Helvetica-Bold", 7.8)
        c.drawString(BODY_X + 3*mm, y - 3.5*mm, f"  {num}.  {title}")
        y_body = y - 7*mm
        y_body = write_para(body, y_body, size=7.2, line_h=3.2, indent=6*mm,
                            width=BODY_W - 9*mm)
        return y - box_h - 1.5*mm

    def footer():
        c.setFillColor(LGREY); c.setFont("Helvetica-Oblique", 6)
        c.drawRightString(PW - MAR, MAR - 1.5*mm,
            "For professional use only. Not investment advice. "
            "GoldenOpp Research | OBQ Signal Suite v2")

    def spacer(y, gap=3):
        return y - gap * mm

    # ════════════════════════════════════════════════════════════════════
    # PAGE A — OBQ Indicator Suite & Forward Cloud Methodology
    # ════════════════════════════════════════════════════════════════════
    y = page_header("Appendix A",
                    "OBQ Indicator Suite Architecture & Forward Cloud Computation Methodology")

    y = section_bar("THE OBQ CUSTOM INDICATOR SUITE", y)
    y = write_para(
        "All technical indicators used in this report are custom Pine Script v6 indicators "
        "developed by Obsidian Quantitative (OBQ). Unlike standard TradingView indicators, "
        "every OBQ indicator is architected as a signal-exporting system. Each fires "
        "edge-triggered signals that are true ONLY on the bar the condition first occurs — "
        "never held true across multiple bars. This precision eliminates noise and ensures "
        "every signal in the Forward Cloud computation represents a genuine state transition.", y)

    y = spacer(y, 2)
    y = section_bar("OBQ INDICATOR SIGNAL REFERENCE", y)

    bullets = [
        ("OBQ-ADX (Trend Strength)",
         "8 edge-triggered signals: TREND_START (ADX crosses 20), TREND_STRONG (ADX crosses 40), "
         "TREND_WEAK (ADX falls below 20), TREND_PEAK (ADX turning down from above 40), "
         "DI_BULL_CROSS (+DI crosses above -DI), DI_BEAR_CROSS (-DI crosses above +DI), "
         "DI_BULL_EXPAND (+DI rising with ADX>20), DI_BEAR_EXPAND (-DI rising with ADX>20). "
         "Uses ta.dmi() with Wilder smoothing."),
        ("OBQ-MACD (Momentum)",
         "10 edge-triggered signals: BULL_CROSS / BEAR_CROSS (MACD line vs signal line), "
         "ABOVE_ZERO / BELOW_ZERO (MACD line vs zero), HIST_EXPAND_BULL / HIST_EXPAND_BEAR "
         "(histogram expanding in positive / negative territory), HIST_CONTRACT_BULL / "
         "HIST_CONTRACT_BEAR (histogram contracting), BULL_DIV / BEAR_DIV (price-histogram divergence)."),
        ("OBQ-RSI (Oscillator)",
         "8 edge-triggered signals: OB_ENTRY (RSI crosses above 70), OB_EXIT (RSI crosses below 70), "
         "OS_ENTRY (RSI crosses below 30), OS_EXIT (RSI crosses above 30), MID_UP (RSI crosses above 50), "
         "MID_DOWN (RSI crosses below 50), BULL_DIV (price lower low + RSI higher low), "
         "BEAR_DIV (price higher high + RSI lower high)."),
        ("OBQ-MA Suite (Moving Averages)",
         "26 edge-triggered signals across three MAs (SMA20, SMA50, SMA200): slope zone transitions "
         "(Q2D/Q1D/FLAT/Q1U/Q2U per MA, 15 signals), MA crossovers (MA20xMA50, MA20xMA200, MA50xMA200 "
         "bull and bear, 6 signals), price-MA crossovers (3 MAs x bull/bear, 6 signals), "
         "full stack alignment entries (STACK_BULL, STACK_BEAR, 2 signals). Slope quantized using "
         "empirically derived thresholds: FLAT = within 0.03%/bar, MILD = 0.03-0.12%/bar, STRONG = >0.12%/bar."),
        ("OBQ-SR Levels v2 (Support & Resistance)",
         "Non-repainting pivot-cluster engine. Combine zone: 0.75% (empirically calibrated on GDX "
         "2006-2026 — 91.3% hold rate at this setting). Levels drawn at confirmation bar, not at "
         "last bar, so they are visible BEFORE price returns to test them. Touch count determines "
         "line weight: 1-touch = thin/transparent, 5+ touches = thick/fully opaque black."),
    ]
    for lbl, body in bullets:
        y = write_bullet(lbl, body, y)

    y = spacer(y, 2)
    y = section_bar("NON-REPAINTING ARCHITECTURE", y)
    y = write_para(
        "All OBQ indicators are provably non-repainting. Four architectural rules enforced: "
        "(1) Pivots confirmed only after right_bars fully closed bars — never on the live bar. "
        "(2) S/R anchor price is immutable after creation — only touch count can increase, never the price. "
        "(3) Forward Cloud uses only historical closed bars (barstate.isconfirmed guard on all state logic). "
        "(4) No drawing on barstate.islast for price levels — all lines drawn at the confirmation bar "
        "and extend right, meaning they exist on the chart before price returns to test them.", y)

    y = spacer(y, 3)
    y = section_bar("FORWARD CLOUD — STEP-BY-STEP COMPUTATION", y)

    steps = [
        ("Signal Detection",
         "On every confirmed closed bar, the cloud indicator checks all monitored signal conditions: "
         "RSI zone crossings, MACD line/histogram transitions, ADX threshold crossings, DI crossovers, "
         "and MA slope zone entries. Only edge-triggered signals (state change this bar) are recorded."),
        ("Bar Index Accumulation",
         "When a signal fires, bar_index is stored in a var int[] array that accumulates over the full "
         "chart history (up to 3,000 bars, approximately 12 years of daily data). More history loaded "
         "= larger signal sample = more statistically robust distribution."),
        ("Forward Return Calculation",
         "On barstate.islast, for each stored signal bar index, forward returns are calculated for "
         "offsets d = 1 to 20 bars: ret[d] = (close[signal_bar + d] - close[signal_bar]) / "
         "close[signal_bar] x 100. Only complete windows where signal_bar + 20 < current bar are used."),
        ("Percentile Distribution",
         "For each forward offset d, all signal instances' returns are sorted. Percentile bands are "
         "extracted: p10, p25, p50 (median), p75, p90, and arithmetic mean. These represent the "
         "historical distribution of outcomes across all qualifying signal instances."),
        ("Cloud Rendering",
         "Percentile bands are anchored to the current close price and drawn as shaded bands extending "
         "20 bars to the right. Outer band (p10-p90) = full outcome range. Inner band (p25-p75) = "
         "interquartile zone. Mean line (solid) = expected path. Median (dashed) = historical midpoint."),
    ]
    for i, (title, body) in enumerate(steps, 1):
        y = write_numbered(str(i), title, body, y)

    footer()
    c.showPage()

    # ════════════════════════════════════════════════════════════════════
    # PAGE B — Composite Cloud Construction & How to Read It
    # ════════════════════════════════════════════════════════════════════
    y = page_header("Appendix B",
                    "Composite Cloud Construction, Signal Calibration & How to Read the Cloud")

    y = section_bar("COMPOSITE CLOUD — POOLING ALL SIGNALS", y)
    y = write_para(
        "The Composite mode combines all signals from all four indicator suites (RSI, MACD, ADX, MA) "
        "into a single unified dataset. Rather than averaging four separate clouds, it treats every "
        "individual signal instance from every indicator as one equal observation in a combined forward "
        "return distribution. This maximises sample size — typically 1,000 to 3,000+ instances on "
        "10+ years of daily data — and produces the most statistically stable projection.", y)

    y = spacer(y, 2)
    y = section_bar("SIGNAL POOLING LOGIC", y)
    y = write_para(
        "When Composite mode is selected, the following signals are pooled into a single return matrix: "
        "RSI signals (OS/OB entries and exits, midline crosses, bullish/bearish divergences) + "
        "MACD signals (line crossovers, zero-line crosses, histogram expansion/contraction) + "
        "ADX signals (trend start/strong/weak, DI crossovers and expansion) + "
        "MA signals (slope zone transitions, MA crossovers, price-MA crossovers, stack alignment). "
        "Each instance contributes one row to the return matrix. "
        "The percentile distribution at each forward bar d is computed across ALL instances simultaneously.", y)

    y = spacer(y, 2)
    y = section_bar("WIN RATE AND N-COUNT INTERPRETATION", y)
    y = write_para(
        "The cloud label displays two key statistics: n= (instance count) and w= (win rate). "
        "The win rate is the percentage of complete signal instances where price was higher at bar +20 "
        "than at the signal bar. A win rate above 50% means the composite of active signals has "
        "historically predicted positive 20-day returns more often than not. "
        "Rates above 65% with n > 100 indicate strong signal confluence and high forecast reliability. "
        "The n-count should ideally exceed 100 for statistical validity — charts with less than "
        "2 years of history may show lower n and less reliable projections.", y)

    y = spacer(y, 2)
    y = section_bar("S/R LEVEL CALIBRATION", y)
    y = write_para(
        "The S/R combine zone threshold of 0.75% was empirically derived from a full diagnostic sweep "
        "on GDX daily data spanning 2006 to 2026 (5,016 bars). Buffer values from 0.10% to 2.00% were "
        "tested. At 0.75%, confirmed levels achieved a 91.3% hold rate — meaning price reversed at "
        "least 0.5% within 10 bars of touching the level. This is the peak quality score across all "
        "tested values, balancing coverage (23 qualified levels per 500-bar window) with accuracy. "
        "The minimum touch threshold of 2 filters single-occurrence noise from genuine structural levels.", y)

    y = spacer(y, 3)
    y = section_bar("HOW TO READ THE FORWARD CLOUD", y)

    cloud_guide = [
        ("Outer Band (p10 to p90) — Full Outcome Range",
         "80% of all historical signal instances resolved within these bounds at day 20. "
         "A wide outer band indicates high outcome variance — the signal environment has produced "
         "a wide range of results historically. A narrow outer band indicates consistency and "
         "high conviction. Use the outer band for stop placement beyond the worst-case scenario."),
        ("Inner Band (p25 to p75) — Interquartile Zone",
         "50% of all historical outcomes landed within this band. This is the primary probability zone. "
         "The upper bound of the inner band defines a realistic near-term target; the lower bound "
         "defines a credible downside risk level. Position sizing and risk/reward calculations "
         "should reference the inner band boundaries."),
        ("Median Line — p50, shown dashed",
         "The historical midpoint: half of all instances finished above this level, half below. "
         "Compare current price to the median projected path. If price is tracking below the median, "
         "it is underperforming relative to the historical signal expectation."),
        ("Mean Line — Solid, thicker, primary target",
         "The arithmetic average of all forward returns. Shown as the price target in the cloud label "
         "(e.g. '$430.1 (+1.4%)'). Compare mean to median to detect distribution skew: "
         "Mean > Median = positive skew (more large upside outliers); Mean < Median = negative skew."),
        ("Cloud Label — n= and w= Statistics",
         "n = number of signal instances in the computation. Target n > 100 for reliability. "
         "w = percentage of instances where price was higher at day 20. "
         "w > 65% with n > 100 = high-confidence bullish cloud posture. "
         "w < 40% with n > 100 = high-confidence bearish cloud posture. "
         "40-60% range = neutral/consolidating posture."),
    ]
    for lbl, body in cloud_guide:
        y = write_bullet(lbl, body, y)

    footer()
    c.showPage()

    # ════════════════════════════════════════════════════════════════════
    # PAGE C — Knowledge Base & CMT Agent Calibration
    # ════════════════════════════════════════════════════════════════════
    y = page_header("Appendix C",
                    "Mining Knowledge Base Distillation & CMT-Level Analyst Agent Calibration")

    y = section_bar("KNOWLEDGE BASE CONSTRUCTION", y)
    y = write_para(
        "The analytical framework powering this report was built from a curated corpus of 26 knowledge "
        "domains covering every dimension of precious metals and mining stock analysis. The knowledge "
        "base was assembled from primary sources including the Mining Valuation Handbook (4th Edition, "
        "Rudenno), Don Durrett's How to Invest in Gold & Silver, Mineral Economics and Policy "
        "(Tilton & Guzman), Investing in Resources (Day), World Gold Council technical papers, "
        "CIM NI 43-101 disclosure standards, AISC reporting guidance, Fraser Institute jurisdiction "
        "risk surveys, and hundreds of company annual reports, MD&As, and NI 43-101 technical reports.", y)

    y = spacer(y, 2)
    y = section_bar("KNOWLEDGE DOMAINS — 26 ANALYTICAL AREAS", y)
    y = write_para(
        "Business Understanding (company types, lifecycle stages, royalty/streaming models) | "
        "Revenue & Production (AISC, grade-recovery-throughput, byproduct credits) | "
        "Profitability & Margins (operating leverage, sustaining vs growth capex) | "
        "Return Ratios (ROIC, ROA, capital efficiency) | "
        "Balance Sheet (hedging, stream obligations, mine closure liabilities) | "
        "Cash Flow (FCF frameworks, capital returns, dividend policy) | "
        "Ownership Structure (insider signals, institutional flows, ETF rebalancing effects) | "
        "Management Quality (capital allocation track record, governance standards) | "
        "Competitive Advantage (cost curve positioning, Tier 1 asset definition) | "
        "Valuation Methods (DCF, NAV/P-NAV, EV per ounce, royalty valuation) | "
        "Industry & Commodity (gold/silver/copper/PGM supply-demand, central bank flows) | "
        "Red Flags & Warning Signs (financial, governance, operational, technical) | "
        "Disclosure Analysis (NI 43-101, annual report, earnings call interpretation) | "
        "Geology & Technical (deposit types, reserve estimation, metallurgy, mining methods) | "
        "Geopolitics & Jurisdiction (country risk, permitting timelines, resource nationalism) | "
        "ESG, Tailings & Water Risk (GISTM framework, carbon disclosure) | "
        "ETF & Passive Flow Dynamics (GDX/GDXJ rebalancing effects, passive inflows) | "
        "Historical Mining Cycles (gold bull/bear markets, commodity supercycles) | "
        "Mine Development Pipeline (exploration through production, 10-stage journey).",
        y, size=7.4, line_h=3.5)

    y = spacer(y, 2)
    y = section_bar("KNOWLEDGE DISTILLATION PROCESS", y)
    y = write_para(
        "Raw source documents were processed through a four-stage distillation pipeline: "
        "(1) Domain Segmentation — all content organised into 26 analytical domains with explicit "
        "boundary definitions and cross-domain relationship mapping. "
        "(2) Concept Extraction — key frameworks, valuation formulas, industry benchmarks, and "
        "decision rules extracted and structured as machine-readable JSON knowledge files. "
        "(3) Cross-Referencing — relationships between domains were explicitly mapped "
        "(e.g. AISC connects revenue analysis, margin analysis, and DCF valuation simultaneously). "
        "(4) Calibration Validation — every extracted formula, benchmark, and threshold validated "
        "against primary source citations. The result is 135+ structured knowledge files totalling "
        "250,000+ lines of domain-specific analytical content, forming the analytical backbone "
        "of every written section in this report.", y)

    y = spacer(y, 3)
    y = section_bar("CMT AGENT CALIBRATION — FOUR PHASES", y)

    cmt = [
        ("Phase 1: CMT Curriculum Integration",
         "CMT Level I-III curriculum was integrated into the agent's analytical framework. "
         "This includes Dow Theory primary/secondary/minor trend structure, Elliott Wave principles, "
         "intermarket analysis frameworks, relative strength methodology, market breadth interpretation, "
         "and CMT-standard definitions and interpretive rules for all indicators used in this report."),
        ("Phase 2: Mining-Specific Technical Overlay",
         "Standard CMT analysis was augmented with mining sector-specific technical patterns: "
         "gold and silver seasonal tendencies, GDX/gold ratio analysis, juniors-vs-seniors relative "
         "strength dynamics, and the technical relationship between real interest rates, DXY, and "
         "precious metals price structure. Mining stock leverage to gold is explicitly modelled."),
        ("Phase 3: Empirical Signal Calibration",
         "The OBQ signal suite was backtested on GDX (2006-2026, 5,016 bars) and WPM to derive optimal "
         "parameters. S/R combine zones (0.75%), MA slope thresholds (flat: 0.03%/bar, mild: 0.12%/bar), "
         "RSI/MACD/ADX signal definitions, and Forward Cloud computation window (20 bars) were all "
         "data-validated against actual forward return distributions before deployment."),
        ("Phase 4: Analytical Language Standards",
         "The agent's prose generation is constrained to CMT-standard language conventions: "
         "evidence-based conclusions only (no speculation without data support), precise indicator "
         "attribution for every claim, directional bias explicitly qualified by conviction level, "
         "and strict separation of structural, momentum, and oscillator commentary. "
         "Every section follows the CMT method of multi-indicator confirmation before bias declaration."),
        ("Ongoing Calibration",
         "The Forward Cloud recalibrates automatically on every report run from live chart history. "
         "Signal win rates, n-counts, and distribution shapes update each week as new price history "
         "accumulates. The analyst bias scoring (0-10 scale) is driven entirely by quantitative "
         "signal output — no subjective adjustments are applied."),
    ]
    for lbl, body in cmt:
        y = write_bullet(lbl, body, y)

    # Disclaimer box at bottom
    disc_y = STOP_Y - 2*mm
    disc_h = 10*mm
    c.setFillColor(VLIGHT)
    c.rect(BODY_X, disc_y, BODY_W, disc_h, fill=1, stroke=0)
    c.setStrokeColor(XLGREY); c.setLineWidth(0.3)
    c.rect(BODY_X, disc_y, BODY_W, disc_h, fill=0, stroke=1)
    c.setFillColor(DARK); c.setFont("Helvetica-Bold", 7)
    c.drawString(BODY_X + 3*mm, disc_y + 7*mm, "IMPORTANT DISCLOSURES")
    disc = (
        "This report is produced by Obsidian Quantitative (OBQ) for internal professional use only and does not constitute "
        "investment advice, a solicitation, or an offer to buy or sell any security. All technical analysis is based on "
        "publicly available market data and proprietary OBQ indicators. Past performance of signal patterns is not indicative "
        "of future results. The Forward Cloud projections are statistical distributions of historical outcomes and should not "
        "be interpreted as price targets or guarantees. All mining and precious metals investments involve significant risk of loss."
    )
    write_para(disc, disc_y + 4.5*mm, size=6.5, line_h=3.0, color=MG)

    footer()
    c.showPage()

def run_report(tickers: list[str] = None) -> Path | None:
    tickers = tickers or DEFAULT_TICKERS

    print(f"\n{'='*60}")
    print(f"  GoldenOpp TA Weekly Report  --  {REPORT_DATE}")
    print(f"  Stocks: {', '.join(tickers)}")
    print(f"  Data source: TradingView Desktop (CDP)")
    print(f"{'='*60}")

    orc = TVOrchestrator()
    if not orc.health_check().get("cdp_connected"):
        print("ERROR: TradingView not connected.")
        return None

    stocks_data = []
    for ticker in tickers:
        print(f"\nProcessing {ticker}...")
        raw      = collect_stock_data(orc, ticker)
        analysis = generate_analysis(ticker, raw)
        print(f"  Bias: {analysis['bias']} [{analysis['conviction']}]  "
              f"Score: {analysis['score']}/9  "
              f"Bars: {analysis['bar_count']}")
        stocks_data.append({
            "ticker":     ticker,
            "screenshot": raw.get("screenshot"),
            "analysis":   analysis,
        })
        time.sleep(0.5)

    # Build PDF
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"GoldenOpp_TA_Weekly_Report_{date_str}.pdf"
    out_path = REPORTS_DIR / filename
    print(f"\nBuilding PDF ({len(stocks_data)} stock pages + 3 appendix pages)...")
    build_pdf(stocks_data, out_path)

    dl = Path(r"C:\Users\admin\Downloads") / filename
    shutil.copy2(out_path, dl)
    print(f"  Downloads: {dl}")
    return dl


def load_full_ticker_list() -> list[str]:
    """Load all tickers in the specified order: GLD SLV GDX GDXJ XME then ETF holdings."""
    try:
        import openpyxl, warnings
        warnings.filterwarnings("ignore")
        base = Path(r"C:\Users\admin\Desktop\GoldenOpp_Buildout_Claude\TickerLists")

        def get_us(path, min_row, col=1):
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            ws = wb.active
            out = []
            for row in ws.iter_rows(min_row=min_row, values_only=True):
                val = row[col]
                if val and isinstance(val, str):
                    t = val.strip()
                    if ' ' not in t and len(t) <= 6 and t != '--' and t.replace('.','').isalpha():
                        out.append(t)
            return out

        gdx  = get_us(base / "GDX_asof_20260429.xlsx",  4)
        gdxj = get_us(base / "GDXJ_asof_20260429.xlsx", 4)
        xme  = get_us(base / "holdings-daily-us-en-xme.xlsx", 6)

        LEAD = ["GLD", "SLV", "GDX", "GDXJ", "XME"]
        seen = set(LEAD)
        all_t = LEAD[:]
        skip = {"B"}  # B = Barrick TSX — skip
        for t in gdx + gdxj + xme:
            if t not in seen and t not in skip:
                all_t.append(t); seen.add(t)
        return all_t
    except Exception as e:
        print(f"Could not load ticker lists: {e}")
        return DEFAULT_TICKERS


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs="+", help="Specific tickers to run")
    parser.add_argument("--full",    action="store_true", help="Run all tickers from TickerLists/ folder")
    args = parser.parse_args()

    if args.full:
        tickers = load_full_ticker_list()
        print(f"Full run: {len(tickers)} tickers")
    elif args.tickers:
        tickers = args.tickers
    else:
        tickers = DEFAULT_TICKERS

    run_report(tickers)
