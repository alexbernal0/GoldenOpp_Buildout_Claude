# GoldenOpp TradingView TA Report System

Generate professional CMT-grade PDF technical analysis reports for any stock list directly from your live TradingView Desktop — with all your custom indicators visible in every screenshot.

## 3-Minute Quick Start

```bash
# 1. Install Python deps
pip install reportlab pillow numpy openpyxl tradingview_ta requests

# 2. Install Node.js controller
cd controller && npm install && cd ..

# 3. Install OBQ indicators in TradingView
#    -> See pine_scripts/install_txt/HOW_TO_INSTALL.md

# 4. Launch TradingView with CDP (run in PowerShell)
$exe = (Get-ChildItem "C:\Program Files\WindowsApps" -Filter "TradingView.exe" -Recurse -EA 0 | Select-Object -First 1).FullName
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $exe; $psi.Arguments = "--remote-debugging-port=9222"
$psi.WorkingDirectory = Split-Path $exe; $psi.UseShellExecute = $true
[System.Diagnostics.Process]::Start($psi)

# 5. Run the report
cd agent
python -u weekly_ta_report.py --tickers GLD WPM AEM       # specific stocks
python -u weekly_ta_report.py --full                       # full 88-ticker run
```

**Output:** `Downloads/GoldenOpp_TA_Weekly_Report_YYYY-MM-DD.pdf`

---

## What You Get

**One page per stock** — clean landscape A4:
- Left half: Live TradingView screenshot with ALL your indicators (OBQ suite + any others you have loaded)
- Right half: 7-section CMT analysis generated from live chart data
- Bottom: Analyst bias rating (BULLISH/BEARISH with conviction level)

**3 appendix pages** at the end of every report explaining the methodology.

---

## Contents

| Folder/File | What it is |
|---|---|
| `agent/weekly_ta_report.py` | **THE MAIN SCRIPT** |
| `agent/tv_orchestrator.py` | CDP bridge to TradingView |
| `pine_scripts/install_txt/` | OBQ indicators as .txt — paste into TV Pine Editor |
| `pine_scripts/install_txt/HOW_TO_INSTALL.md` | Step-by-step install guide |
| `ticker_lists/*.xlsx` | GDX/GDXJ/XME holdings for `--full` run |
| `controller/` | Node.js CDP controller (run `npm install` here) |
| `USER_GUIDE.md` | **Complete documentation — read this** |

---

## Key Commands

```bash
cd agent

# Single test
python -u weekly_ta_report.py --tickers GLD

# Your stocks
python -u weekly_ta_report.py --tickers WPM GOLD AEM NEM KGC FNV OR

# Full mining universe (88 tickers, ~20 min)
python -u weekly_ta_report.py --full
```

---

**Read `USER_GUIDE.md` for full setup instructions, troubleshooting, and explanation of every section in the report.**
