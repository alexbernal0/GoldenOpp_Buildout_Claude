# GoldenOpp TradingView TA Report System — Complete User Guide

**Version:** 1.0  |  **Built by:** Obsidian Quantitative (OBQ)  
**Purpose:** Automated CMT-grade weekly technical analysis reports for mining stocks

---

## What This System Does

This system connects to your live **TradingView Desktop** app via Chrome DevTools Protocol (CDP),
automatically switches to each stock in your watchlist, takes a screenshot of the chart with all
your OBQ indicators visible, pulls the price data, runs a full CMT-level technical analysis,
and produces a **professional landscape A4 PDF report** with one page per stock.

**A full 88-ticker run takes ~20 minutes and produces a 91-page PDF.**

---

## Folder Structure

```
tradingview_report_system/
  agent/
    weekly_ta_report.py    <- THE MAIN SCRIPT — run this
    tv_orchestrator.py     <- CDP bridge (do not modify)
    screener.py            <- TradingView screener API
    ta_engine.py           <- Indicator calculations
    sentiment.py           <- News sentiment (optional)
  pine_scripts/
    install_txt/
      HOW_TO_INSTALL.md    <- How to install indicators in TradingView
      OBQ_ADX_v1.txt       <- Paste into TV Pine Editor
      OBQ_MACD_v1.txt
      OBQ_RSI_v2.txt
      OBQ_MA_Suite_v1.txt
      OBQ_SR_Levels_v2_black.txt
      OBQ_Forward_Cloud_v2_selfcalc.txt
    *.pine                 <- Source files
  controller/
    src/                   <- Node.js CDP controller (do not modify)
    package.json
  ticker_lists/
    GDX_asof_20260429.xlsx
    GDXJ_asof_20260429.xlsx
    holdings-daily-us-en-xme.xlsx
  requirements.txt
  USER_GUIDE.md            <- You are here
```

---

## Prerequisites

### 1. Python 3.10+
```bash
pip install reportlab pillow numpy openpyxl tradingview_ta requests
```

### 2. Node.js 18+
Download from https://nodejs.org

Then install the CDP controller:
```bash
cd tradingview_report_system/controller
npm install
```

### 3. TradingView Desktop (Windows Store)
- Install from https://www.tradingview.com/desktop/
- Log in with your **Premium** account
- Install all 6 OBQ indicators on your chart (see **Step 3** below)

---

## Step-by-Step Setup

### Step 1 — Install Python Dependencies
```bash
pip install reportlab pillow numpy openpyxl tradingview_ta requests
```

### Step 2 — Install Node.js Controller
```bash
cd tradingview_report_system/controller
npm install
```

### Step 3 — Install OBQ Indicators in TradingView

The report screenshots your live TradingView chart, so all OBQ indicators must be loaded.

**Open `pine_scripts/install_txt/HOW_TO_INSTALL.md` for full instructions.**

Quick summary — repeat for each of the 6 indicators:
1. Open TradingView Desktop
2. Pine Editor (bottom of screen) → click **`+`** tab button (new tab — critical!)
3. Select all `Ctrl+A`, paste the code from the `.txt` file
4. Click **"Add to chart"**
5. Save your layout (`Ctrl+S`)

**6 indicators to install (in this order):**

| File | Goes on |
|---|---|
| `OBQ_MA_Suite_v1.txt` | Main price chart (overlay) |
| `OBQ_SR_Levels_v2_black.txt` | Main price chart (overlay) |
| `OBQ_Forward_Cloud_v2_selfcalc.txt` | Main price chart (overlay) |
| `OBQ_MACD_v1.txt` | Sub-panel 1 |
| `OBQ_RSI_v2.txt` | Sub-panel 2 |
| `OBQ_ADX_v1.txt` | Sub-panel 3 |

> **Note:** If you have additional indicators (IV Suite, PQS, etc.) those will also appear in the screenshot automatically — the system captures your full chart exactly as it looks.

### Step 4 — Configure Paths

Open `agent/weekly_ta_report.py` and update these two paths near the top if needed:

```python
# Path to the controller CLI (line ~55)
CONTROLLER = str(Path(__file__).parent.parent / "controller")

# Path to ticker lists (near bottom of file)
base = Path(r"C:\YOUR_PATH\tradingview_report_system\ticker_lists")
```

---

## Running Reports

### Launch TradingView with CDP First (REQUIRED every session)

Close any existing TradingView window, then run this PowerShell command:

```powershell
# Find your exact TV path first:
Get-AppxPackage | Where-Object { $_.Name -like "*TradingView*" } | Select-Object InstallLocation

# Then launch with debug port (replace path with yours):
$exe = "C:\Program Files\WindowsApps\TradingView.Desktop_3.1.0.7818_x64__n534cwy3pjxzj\TradingView.exe"
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $exe
$psi.Arguments = "--remote-debugging-port=9222"
$psi.WorkingDirectory = Split-Path $exe
$psi.UseShellExecute = $true
[System.Diagnostics.Process]::Start($psi)
```

Wait ~15-20 seconds for TradingView to fully load.

---

### Run Commands

Navigate to the `agent/` folder first:
```bash
cd tradingview_report_system/agent
```

**Test with one ticker:**
```bash
python -u weekly_ta_report.py --tickers GLD
```

**Run a custom list of stocks:**
```bash
python -u weekly_ta_report.py --tickers WPM GOLD AEM NEM KGC FNV
```

**Run the full 88-ticker universe (GDX + GDXJ + XME holdings):**
```bash
python -u weekly_ta_report.py --full
```

**Output:** `C:\Users\YOUR_NAME\Downloads\GoldenOpp_TA_Weekly_Report_YYYY-MM-DD.pdf`

---

## Understanding the Report

### Per-Stock Page Layout (Landscape A4)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  GoldenOpp Research — Weekly Technical Analysis          Week of May 2026│
├──────────────────────────────────────────────────────────────────────────┤
│  WPM — Wheaton Precious Metals  ·  NYSE  ·  $125.60 (+0.5%)  ·  1W: -1% │
├─────────────────────────────┬──────────────────────────────────────────  │
│                             │ ▌ TREND & MA STRUCTURE                     │
│   LIVE TRADINGVIEW          │ Analysis text...                           │
│   CHART SCREENSHOT          │ ▌ 20-DAY FORWARD CLOUD FORECAST            │
│                             │ Analysis text...                           │
│   (Dec 2025 → present       │ ▌ MOMENTUM  (MACD)                        │
│    + 35 days forward)       │ Analysis text...                           │
│                             │ ▌ OSCILLATOR  (RSI)                       │
│   Shows all your            │ Analysis text...                           │
│   indicators +              │ ▌ TREND STRENGTH  (ADX)                   │
│   Forward Cloud             │ Analysis text...                           │
│                             │ ▌ KEY LEVELS                              │
│                             │ Analysis text...                           │
│                             │ ▌ TECHNICAL SUMMARY                       │
│                             │ 3-sentence synthesis...                   │
│                             ├────────────────────────────────────────── │
│                             │ ANALYST BIAS: BULLISH [HIGH CONVICTION]   │
│                             │ Active signals: Golden Cross, RSI Bull...  │
└─────────────────────────────┴──────────────────────────────────────────  │
```

### The 7 Analysis Sections

| Section | What It Covers |
|---|---|
| **Trend & MA Structure** | Golden/Death Cross, price vs SMA20/50/200, stack alignment (price>MA20>MA50>MA200), distance from each MA |
| **20-Day Forward Cloud** | Which signals are currently active, what the Composite Cloud is projecting, specific price targets from the cloud bands, what would change the posture |
| **Momentum (MACD)** | MACD line vs signal line, histogram direction, crossover detection, momentum building vs fading |
| **Oscillator (RSI)** | Zone classification (OS/OB/neutral), 5-session trend, divergence detection |
| **Trend Strength (ADX)** | Trending vs ranging, +DI/-DI spread, ADX rising/falling, directional bias |
| **Key Levels** | 52W range, MA levels, ATR volatility benchmark, S/R levels note |
| **Technical Summary** | Full 3-sentence synthesis of the entire technical picture + bias with conviction |

### Analyst Bias Scoring

The bias score (0-10) is calculated from these quantitative factors:

| Factor | Points |
|---|---|
| Golden Cross (SMA50 > SMA200) | +2 |
| Price above SMA20 | +1 |
| Price above SMA200 | +1 |
| MACD above signal line | +1 |
| MACD histogram expanding | +1 |
| RSI > 55 | +1 |
| +DI > -DI | +1 |
| ADX > 25 (trend confirmed) | +1 |
| Full bull stack (price>MA20>MA50>MA200) | +1 |

**Score → Bias:**
- 6-10: BULLISH (HIGH conviction)
- 3-5: BULLISH (MEDIUM conviction)
- 1-2: CAUTIOUSLY BULLISH
- 0: NEUTRAL
- -1 to -2: CAUTIOUSLY BEARISH
- -3 to -4: BEARISH (MEDIUM)
- -5 to -10: BEARISH (HIGH)

### The 3 Appendix Pages

Every report ends with 3 methodology pages:
- **Appendix A:** Full OBQ indicator architecture + Forward Cloud 5-step computation
- **Appendix B:** Composite Cloud construction + how to read each band (p10/p25/p50/p75/p90 + mean)
- **Appendix C:** Knowledge base distillation + CMT agent calibration phases

---

## The Forward Cloud Explained

The Forward Cloud is the most important indicator in this system. It projects **where price statistically goes** after the current combination of signals.

**How it calculates:**
1. Scans ALL historical bars on the chart for signal instances (RSI zones, MACD crosses, ADX transitions, MA slope changes)
2. For each signal, records what price did over the next 20 bars
3. Computes the full distribution: p10, p25, p50, p75, p90 percentiles + mean
4. Draws shaded bands projecting 20 bars forward from today

**Reading the cloud:**
- **Outer shaded band (p10-p90):** Full outcome range — 80% of historical instances resolved here
- **Inner shaded band (p25-p75):** The probable zone — use for price targets and stops
- **Mean line (solid):** The single best forecast — shown as "$X (+Y%)" in the label
- **n= and w=:** Sample size and win rate. n>100 with w>60% = high confidence

**The key insight:** The cloud tells you what historically happened when these exact signals fired together. If the cloud is pointing up with w=72%, that means 72% of similar historical setups ended higher at day 20.

---

## Customizing Your Ticker List

### Add Your Own Stocks
Edit `agent/weekly_ta_report.py` and find the `DEFAULT_TICKERS` variable near the top.
Change it to whatever stocks you want as the default.

Or just pass them on the command line:
```bash
python -u weekly_ta_report.py --tickers AAPL MSFT NVDA TSM
```

The system works on **any ticker** TradingView supports — not just mining stocks.

### Update ETF Holdings (weekly)
Download fresh files from:
- **GDX:** https://www.vaneck.com/us/en/investments/gold-miners-etf-gdx/ → Holdings tab → Download
- **GDXJ:** https://www.vaneck.com/us/en/investments/junior-gold-miners-etf-gdxj/ → Holdings tab
- **XME:** https://www.ssga.com/us/en/intermediary/etfs/funds/spdr-sp-metals-mining-etf-xme → Download

Save as Excel (.xlsx) in `ticker_lists/` with the same filenames.

### Add New ETF Lists
In `weekly_ta_report.py`, find `load_full_ticker_list()` and add:
```python
your_etf = get_us(base / "your_new_file.xlsx", min_row=4)
```

---

## Troubleshooting

### "ERROR: TradingView not connected"
TV is not running with the debug port. Follow Step 4 (Launch TradingView with CDP) above.

### "Got 0 bars" for a ticker
TradingView doesn't recognize the ticker. Try:
- Adding exchange prefix: `NYSE:WPM` or `NASDAQ:AAPL`
- Check if the ticker is listed on a US exchange

### Chart shows black margins
The screenshot was taken before the chart finished loading. This is rare after the 8-second render wait, but if it happens, increase the sleep values in `collect_stock_data()`:
```python
time.sleep(5.0)  # increase this
```

### PDF is very large / slow
Normal for 88+ pages. Reduce `time.sleep` values between tickers to speed up, but below 5 seconds risks incomplete chart renders.

### Wrong TV path on launch
```powershell
# Find your exact path:
Get-AppxPackage | Where-Object { $_.Name -like "*TradingView*" } | Select-Object InstallLocation, Version
```

---

## Tips for Best Results

1. **Set TV to your preferred layout BEFORE running** — the report captures whatever is on screen
2. **Keep sub-panels small** — gives more room to the main price chart in the screenshot
3. **Run during market hours** for fresh data, or after-hours for complete daily bars
4. **Test with 3-5 tickers first** before running the full 88-ticker batch
5. **The Forward Cloud takes a few seconds to compute** on each new symbol — the 5-second wait handles this
6. **Your layout is shared with your coworker** — any indicators they have on chart (IV Suite, PQS, etc.) will appear automatically in the screenshots
