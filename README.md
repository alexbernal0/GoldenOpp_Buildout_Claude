# GoldenOpp -- Weekly Technical Analysis Report System

**Professional CMT-grade technical analysis reports for mining, metals, and ETF universe.**

Generates a comprehensive PDF report covering 88 tickers (GDX + GDXJ + XME holdings) with live TradingView chart screenshots, 7-section CMT institutional analysis per stock, 20-day Forward Cloud forecast, and 3-page methodology appendix.

## Quick Start

```bash
# 1. Launch TradingView Desktop with CDP (see ta_report_agent/USER_GUIDE.md)
# 2. Run full 88-ticker report:
cd OBQ_AutoResearch/Tradingview_Agents
python -u workflows/weekly_ta_report.py --full
# Output: Downloads/GoldenOpp_TA_Weekly_Report_YYYY-MM-DD.pdf
```

## Repository Structure

```
GoldenOpp_Buildout_Claude/
|-- pine_indicators/          OBQ Custom TradingView Indicators (Pine Script v6)
|   |-- install_txt/          .txt copies -- paste into TV Pine Editor to install
|   |   |-- HOW_TO_INSTALL.md Step-by-step install guide for new coworkers
|   |   |-- OBQ_ADX_v1.txt
|   |   |-- OBQ_MACD_v1.txt
|   |   |-- OBQ_RSI_v2.txt
|   |   |-- OBQ_MA_Suite_v1.txt
|   |   |-- OBQ_SR_Levels_v2_black.txt
|   |   +-- OBQ_Forward_Cloud_v2_selfcalc.txt
|   +-- README.md             Indicator signal reference
|-- ta_report_agent/          Weekly TA Report Generator
|   |-- weekly_ta_report.py   Main script -- run this
|   +-- USER_GUIDE.md         Full setup + usage instructions
|-- TickerLists/              ETF holdings Excel files (update weekly)
+-- OBQ_GoldenOpp/            Legacy agent code + 135-file knowledge base
```

## OBQ Indicator Suite

All indicators are Pine Script v6, edge-triggered signals (fire ONCE on state change only):

| Indicator       | Signals | Purpose                            |
|-----------------|---------|------------------------------------|
| OBQ-ADX         | 8       | Trend strength (ADX, +DI, -DI)     |
| OBQ-MACD        | 10      | Momentum (crosses, histogram, div) |
| OBQ-RSI         | 8       | Oscillator (zones, divergence)     |
| OBQ-MA Suite    | 26      | MA structure (slope zones, stack)  |
| OBQ-SR Levels   | N/A     | Support/resistance, non-repainting |
| OBQ-Forward Cloud | N/A  | 20-day self-calculating projection |

## The Forward Cloud

Self-calculating from live chart history -- no hardcoded data, works on any ticker:
1. Detects all RSI/MACD/ADX/MA signal instances in full chart history
2. Calculates 1-20 bar forward returns for each instance
3. Computes p10/p25/p50/p75/p90 percentile distribution + mean
4. Draws shaded projection bands 20 bars forward from current price

## Requirements

- Python 3.10+: pip install reportlab pillow numpy openpyxl
- Node.js 18+, TradingView Desktop v3.1.0, TradingView Premium account
