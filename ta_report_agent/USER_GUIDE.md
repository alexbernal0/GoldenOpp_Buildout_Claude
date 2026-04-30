# GoldenOpp Weekly TA Report — User Guide

## What This Does

Generates a professional **CMT-grade PDF technical analysis report** for any list of mining, metals, and ETF tickers.

- Connects to your live **TradingView Desktop** via CDP
- Switches to each ticker, waits for full chart render, takes a screenshot
- Pulls OHLCV data and calculates all indicators locally
- Generates CMT institutional prose for 7 analysis sections
- Builds a landscape A4 PDF with chart image + analysis side-by-side
- Appends 3 appendix pages explaining methodology

**Output:** `C:\Users\admin\Downloads\GoldenOpp_TA_Weekly_Report_YYYY-MM-DD.pdf`

---

## Prerequisites

### 1. TradingView Desktop v3.1.0 (Windows Store)
Must be installed and logged in with your Premium account.

### 2. OBQ Custom Indicators on Chart
Before running the report, your TradingView chart must have these indicators loaded:
- OBQ-MA Suite (SMA 20/50/200)
- OBQ-MACD Signals
- OBQ-RSI Signals
- OBQ-ADX Signals
- OBQ S/R Levels v2
- OBQ Forward Cloud v2 (self-calculating)

See `pine_indicators/install_txt/` for installation instructions.

### 3. Python Dependencies
```bash
pip install reportlab pillow numpy openpyxl
```

### 4. Node.js CDP Controller
```bash
cd OBQ_AutoResearch/Tradingview_Agents/controller
npm install
```

---

## How to Run

### Step 1 — Launch TradingView with CDP
Close any existing TradingView instance, then run:
```powershell
$exe = "C:\Program Files\WindowsApps\TradingView.Desktop_3.1.0.7818_x64__n534cwy3pjxzj\TradingView.exe"
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $exe; $psi.Arguments = "--remote-debugging-port=9222"
$psi.WorkingDirectory = Split-Path $exe; $psi.UseShellExecute = $true
[System.Diagnostics.Process]::Start($psi)
```
Wait ~20 seconds for TV to fully load.

### Step 2 — Run the Report

**Single ticker test:**
```bash
cd OBQ_AutoResearch/Tradingview_Agents
python -u workflows/weekly_ta_report.py --tickers GLD
```

**Specific tickers:**
```bash
python -u workflows/weekly_ta_report.py --tickers GLD SLV GDX GDXJ WPM AEM NEM
```

**Full 88-ticker run (all GDX/GDXJ/XME holdings):**
```bash
python -u workflows/weekly_ta_report.py --full
```
Runtime: ~20 minutes for full run.

---

## Ticker Run Order (--full)

1. **ETF Benchmarks:** GLD, SLV, GDX, GDXJ, XME
2. **GDX Holdings** (US-listed): AEM, NEM, FNV, AU, WPM, KGC, GFI, PAAS, AGI, CDE, RGLD, EQX, AG, HL, IAG, HMY, BVN, BTG, EGO, SSRM, OR, ARMN, ORLA, CGAU, EXK, FSM, SA, DRD...
3. **GDXJ Holdings** (additional US-listed small/mid caps)
4. **XME Holdings** (metals & mining broader universe)

Ticker lists sourced from: `TickerLists/` folder (update these files weekly from ETF provider websites).

---

## Report Structure (per page)

| Section | Content |
|---|---|
| **Header** | Dark band: report title + date |
| **Company line** | Ticker, company name, exchange, price, performance |
| **Left half** | Live TradingView chart screenshot (Dec 2025 → +35 days forward, shows full cloud) |
| **Right half** | 7 analysis sections |
| → Trend & MA Structure | Golden/Death Cross, stack alignment, MA distances |
| → 20-Day Forward Cloud | Active signals, cloud posture, price targets |
| → Momentum (MACD) | Crossovers, histogram, trend direction |
| → Oscillator (RSI) | Zone classification, divergences |
| → Trend Strength (ADX) | Trend/range assessment, DI alignment |
| → Key Levels | S/R levels, 52W range, ATR |
| → Technical Summary | Full synthesis in 3 sentences |
| **Bias Box** | BULLISH/BEARISH + conviction + signal factors |

**Appendix Pages (last 3 pages of every report):**
- **Appendix A:** OBQ Indicator Suite architecture + Forward Cloud computation steps
- **Appendix B:** Composite Cloud construction + how to read each band
- **Appendix C:** Knowledge base distillation + CMT agent calibration phases

---

## Updating Ticker Lists

Download fresh holdings files from ETF providers:
- **GDX:** https://www.vaneck.com/us/en/investments/gold-miners-etf-gdx/
- **GDXJ:** https://www.vaneck.com/us/en/investments/junior-gold-miners-etf-gdxj/
- **XME:** https://www.ssga.com/us/en/intermediary/etfs/funds/spdr-sp-metals-mining-etf-xme

Save as Excel (.xlsx) in `TickerLists/` folder with the same naming convention.

---

## Troubleshooting

**"TradingView not connected"**
→ CDP not running. Run the PowerShell launch command above.

**"Got 0 bars"**
→ Ticker not found on TradingView. Skip it or try adding exchange prefix (e.g. NYSE:WPM).

**Black borders on chart images**
→ TV took screenshot before chart loaded. The script waits 8 seconds but some slow connections need more. Increase `time.sleep(5.0)` in `collect_stock_data()`.

**PDF build slow**
→ Normal for 88+ pages with high-resolution images. Takes 2-5 minutes after all screenshots collected.

---

## File Locations

| File | Purpose |
|---|---|
| `weekly_ta_report.py` | Main report generator script |
| `../pine_indicators/` | Pine Script source files (.pine) |
| `../pine_indicators/install_txt/` | Same files as .txt for easy copy-paste into TV editor |
| `../TickerLists/` | ETF holdings Excel files |
| `../OBQ_AutoResearch/Tradingview_Agents/reports/` | All generated PDF reports |
| `../OBQ_AutoResearch/Tradingview_Agents/reports/screenshots/` | Chart screenshots cache |
