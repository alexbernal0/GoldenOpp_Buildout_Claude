# OBQ Pine Script Indicator Suite

Complete collection of custom TradingView Pine Script v6 indicators built for the GoldenOpp mining stock analysis pipeline. These indicators are the foundation of all signal generation, forward projection, and composite analysis.

---

## Indicators

### 1. OBQ-ADX (`OBQ_ADX_v1.pine`)
**Trend strength signals — edge-triggered**
- ADX + DI lines plotted
- 8 signal types: TREND_START, TREND_STRONG, TREND_WEAK, TREND_PEAK, DI_BULL_CROSS, DI_BEAR_CROSS, DI_BULL_EXPAND, DI_BEAR_EXPAND
- Signals fire only on the bar they transition (never held true across bars)
- Export labels for AI pipeline integration

### 2. OBQ-MACD (`OBQ_MACD_v1.pine`)
**Momentum signals — edge-triggered**
- MACD histogram, signal line, zero line
- 10 signal types: BULL/BEAR CROSS, ABOVE/BELOW ZERO, HIST_EXPAND/CONTRACT BULL/BEAR, BULL/BEAR DIV
- Divergence detection included

### 3. OBQ-RSI (`OBQ_RSI_v2.pine`)
**Momentum oscillator — edge-triggered**
- RSI with configurable OB/OS levels
- 8 signal types: OB_ENTRY/EXIT, OS_ENTRY/EXIT, MID_UP/DOWN, BULL/BEAR DIV
- Divergence detection included

### 4. OBQ Aether Stops (`OBQ_AetherStops.pine`)
**ATR-based trailing stop system**
- Dynamic stop levels based on ATR multiplier
- Trend direction signals

### 5. OBQ S/R Levels v2 (`OBQ_SR_Levels_v2_black.pine`)
**Support & Resistance — Provably Non-Repainting**
- Pivot-cluster engine: every confirmed pivot is a candidate level
- Combine zone 0.75% (empirically derived from GDX 2006–2026 diagnostic)
- Touch-weighted visual: all black lines, thickness = touch count
  - 1 touch = hairline, 70% transparent
  - 2 touches = thin, 40% transparent
  - 3+ = solid, fully opaque
- Minimum 2 touches to display (filters noise)
- Levels drawn at confirmation bar — visible BEFORE price revisits them
- Non-repainting guarantee: anchor price never changes after creation

### 6. OBQ MA Suite (`OBQ_MA_Suite_v1.pine`)
**Moving average structure — edge-triggered signals**
- SMA 20, 50, 200 plotted
- Slope quantile bins (Q2D/Q1D/FLAT/Q1U/Q2U) per MA — fires on zone entry only
- Crossovers: MA×MA and Price×MA (all combinations)
- Stack alignment signals (STACK_BULL / STACK_BEAR)
- Total: ~26 distinct signals, all edge-triggered
- Export labels for AI pipeline

### 7. OBQ Forward Cloud v2 (`OBQ_Forward_Cloud_v2_selfcalc.pine`)
**Self-calculating forward projection cloud**
- Reads full chart history of the stock it's applied to
- Calculates RSI + MACD + ADX + MA signal instances from that history
- Computes forward return distributions (p10/p25/p50/p75/p90 + mean)
- Draws projection cloud 20 bars forward from current price
- Works on ANY ticker — no hardcoded data
- Composite mode pools all signal types for maximum sample size
- Color coded by source (purple=Composite, green=MA, blue=RSI/MACD/ADX)

---

## Signal Export Format

All indicators with `Export Labels = true` output labels in this format:
```
SIGNAL_NAME|YYYY-MM-DD|close_price|indicator_value
```
Example: `ADX_TREND_START|2026-04-30|86.22|22.41`

This format feeds directly into:
- Forward Cloud generator (calculate return distributions)
- GoldenOpp agent pipeline (conviction scoring)
- MotherDuck signal tables

---

## Configuration

### S/R Levels — Empirically Derived Settings
From GDX 2006–2026 diagnostic sweep:
- `combine_pct = 0.75%` — 91.3% level hold rate
- `lookback = 500 bars` (~2yr daily)
- `min_touches = 2` — filters noise
- `hot_threshold = 3` — solid lines

### MA Suite — Slope Thresholds
- `slope_flat = 0.03%` per bar — below this = FLAT zone
- `slope_mild = 0.12%` per bar — between flat and mild = Q1

### Forward Cloud — Parameters
- `projection_bars = 20` — 20 bar forward window
- `max_history = 3000 bars` — ~12 years daily
- `min_instances = 5` — minimum signal count before drawing

---

## Non-Repainting Architecture (S/R + Forward Cloud)

Both the S/R indicator and Forward Cloud are designed to be non-repainting:
- Pivots confirmed only after `right_bars` closed bars
- Levels drawn at confirmation bar, extend right (visible before price returns)
- Anchor price never changes after creation — only touch count increments
- Forward Cloud uses only historical data (signal bar + d must be < current bar)
- No `barstate.islast` drawing for price levels
