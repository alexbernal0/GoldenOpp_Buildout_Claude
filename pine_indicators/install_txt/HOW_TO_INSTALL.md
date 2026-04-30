# Installing OBQ Custom Indicators in TradingView

## Required Indicators (install all 6)

| File | Indicator Name | Overlay? | Pane |
|---|---|---|---|
| OBQ_MA_Suite_v1.txt | OBQ MA Suite | Yes | Main price chart |
| OBQ_SR_Levels_v2_black.txt | OBQ S/R Levels v2 | Yes | Main price chart |
| OBQ_Forward_Cloud_v2_selfcalc.txt | OBQ Forward Cloud v2 | Yes | Main price chart |
| OBQ_MACD_v1.txt | OBQ MACD Signals | No | Sub-panel 1 |
| OBQ_RSI_v2.txt | OBQ RSI Signals | No | Sub-panel 2 |
| OBQ_ADX_v1.txt | OBQ ADX Signals | No | Sub-panel 3 |

---

## Installation Steps (repeat for each indicator)

1. Open **TradingView Desktop**
2. Click the **Pine Script Editor** button (bottom of screen, lightning bolt icon)
3. In the editor, click the **`+`** tab button to open a **new tab** (critical — do not overwrite existing scripts)
4. **Select all** (`Ctrl+A`) in the new tab
5. Open the `.txt` file from this folder in any text editor (Notepad works fine)
6. **Copy all** the Pine Script code (`Ctrl+A`, `Ctrl+C`)
7. **Paste** into the TradingView Pine Editor (`Ctrl+V`)
8. Click **"Add to chart"** button in the editor toolbar
9. If a "Save and add to chart" dialog appears — type the indicator name and click Save

## Important Notes

- Install in the order listed above (overlays first, sub-panels second)
- After adding all 6, **save your chart layout** (Ctrl+S or the Save button in TV)
- The Forward Cloud v2 is **self-calculating** — it will take a few seconds to compute on first load on any new symbol
- Do NOT click "Update on chart" on existing indicators — always use the `+` new tab approach

## Recommended Chart Setup

- **Timeframe:** Daily (1D)
- **Starting view:** Dec 2025 to present + 35 days forward (to show the full cloud projection)
- All 6 indicators should be visible before running the TA report

## Troubleshooting

**"Add to chart" button not visible** → Click the `+` tab in the pine editor toolbar to open a fresh new tab

**Cloud shows no bands** → Not enough history loaded. Scroll chart back to load more bars, or increase "Max History Bars" in cloud settings to 3000

**S/R lines not showing** → Min touches is set to 2 — need at least 500 bars of history for levels to form
