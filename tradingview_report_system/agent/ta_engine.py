"""
ta_engine.py — Technical analysis engine using tradingview_ta + yfinance.

Provides: single-symbol analysis, multi-timeframe alignment, signal scanning,
and basic strategy backtesting.

Install: pip install tradingview_ta yfinance pandas_ta
"""

from __future__ import annotations

import warnings
from datetime import datetime, timedelta
from typing import Optional

warnings.filterwarnings("ignore")

try:
    from tradingview_ta import TA_Handler, Interval, Exchange
    HAS_TV_TA = True
except ImportError:
    HAS_TV_TA = False

try:
    import yfinance as yf
    HAS_YF = True
except ImportError:
    HAS_YF = False

try:
    import pandas as pd
    import numpy as np
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

# ── Interval mapping ──────────────────────────────────────────────────────────

TV_INTERVALS = {
    "1m": Interval.INTERVAL_1_MINUTE if HAS_TV_TA else "1m",
    "5m": Interval.INTERVAL_5_MINUTES if HAS_TV_TA else "5m",
    "15m": Interval.INTERVAL_15_MINUTES if HAS_TV_TA else "15m",
    "1h": Interval.INTERVAL_1_HOUR if HAS_TV_TA else "1h",
    "4h": Interval.INTERVAL_4_HOURS if HAS_TV_TA else "4h",
    "1d": Interval.INTERVAL_1_DAY if HAS_TV_TA else "1d",
    "1w": Interval.INTERVAL_1_WEEK if HAS_TV_TA else "1w",
    "1M": Interval.INTERVAL_1_MONTH if HAS_TV_TA else "1M",
} if HAS_TV_TA else {}

MTF_TIMEFRAMES = ["1w", "1d", "4h", "1h", "15m"]


# ── Core Analysis ─────────────────────────────────────────────────────────────

def analyze(symbol: str, exchange: str = "NASDAQ", interval: str = "1d") -> dict:
    """
    Full TA for one symbol: recommendation, indicators, oscillators, moving averages.

    Returns:
        {
            symbol, exchange, interval,
            recommendation: {summary, oscillators, moving_averages},
            indicators: {RSI, MACD, BB_upper, BB_lower, EMA20, SMA50, ...},
            raw: {all raw indicator values}
        }
    """
    if not HAS_TV_TA:
        return {"error": "tradingview_ta not installed. Run: pip install tradingview_ta"}

    tv_interval = TV_INTERVALS.get(interval, Interval.INTERVAL_1_DAY)

    try:
        handler = TA_Handler(
            symbol=symbol.upper(),
            screener="america",
            exchange=exchange.upper(),
            interval=tv_interval,
        )
        analysis = handler.get_analysis()

        indicators = analysis.indicators
        summary = analysis.summary
        oscillators = analysis.oscillators
        moving_averages = analysis.moving_averages

        return {
            "symbol": symbol.upper(),
            "exchange": exchange.upper(),
            "interval": interval,
            "recommendation": {
                "summary": summary.get("RECOMMENDATION", "N/A"),
                "buy_count": summary.get("BUY", 0),
                "sell_count": summary.get("SELL", 0),
                "neutral_count": summary.get("NEUTRAL", 0),
                "oscillators": oscillators.get("RECOMMENDATION", "N/A"),
                "moving_averages": moving_averages.get("RECOMMENDATION", "N/A"),
            },
            "indicators": {
                "RSI": round(indicators.get("RSI", 0) or 0, 2),
                "RSI[1]": round(indicators.get("RSI[1]", 0) or 0, 2),
                "MACD": round(indicators.get("MACD.macd", 0) or 0, 4),
                "MACD_signal": round(indicators.get("MACD.signal", 0) or 0, 4),
                "MACD_hist": round((indicators.get("MACD.macd", 0) or 0) - (indicators.get("MACD.signal", 0) or 0), 4),
                "BB_upper": round(indicators.get("BB.upper", 0) or 0, 2),
                "BB_lower": round(indicators.get("BB.lower", 0) or 0, 2),
                "BB_basis": round(indicators.get("BB.middle", 0) or 0, 2),
                "EMA20": round(indicators.get("EMA20", 0) or 0, 2),
                "SMA20": round(indicators.get("SMA20", 0) or 0, 2),
                "SMA50": round(indicators.get("SMA50", 0) or 0, 2),
                "SMA200": round(indicators.get("SMA200", 0) or 0, 2),
                "ADX": round(indicators.get("ADX", 0) or 0, 2),
                "ATR": round(indicators.get("ATR", 0) or 0, 4),
                "Stoch_K": round(indicators.get("Stoch.K", 0) or 0, 2),
                "Stoch_D": round(indicators.get("Stoch.D", 0) or 0, 2),
                "close": round(indicators.get("close", 0) or 0, 2),
                "open": round(indicators.get("open", 0) or 0, 2),
                "high": round(indicators.get("high", 0) or 0, 2),
                "low": round(indicators.get("low", 0) or 0, 2),
                "volume": indicators.get("volume", 0),
                "change": round(indicators.get("change", 0) or 0, 4),
            },
        }

    except Exception as e:
        return {"error": str(e), "symbol": symbol, "exchange": exchange}


def multi_timeframe(symbol: str, exchange: str = "NASDAQ") -> dict:
    """
    Analyze across 5 timeframes and calculate alignment score.

    Returns:
        {
            symbol,
            timeframes: {1w: {...}, 1d: {...}, 4h: {...}, 1h: {...}, 15m: {...}},
            alignment: {score: float 0-100, direction: BUY/SELL/NEUTRAL, detail: str}
        }
    """
    if not HAS_TV_TA:
        return {"error": "tradingview_ta not installed"}

    results = {}
    for tf in MTF_TIMEFRAMES:
        a = analyze(symbol, exchange, tf)
        rec = a.get("recommendation", {}).get("summary", "NEUTRAL") if "error" not in a else "ERROR"
        results[tf] = {
            "recommendation": rec,
            "RSI": a.get("indicators", {}).get("RSI", 0),
            "MACD": a.get("indicators", {}).get("MACD", 0),
        }

    # Calculate alignment score
    weights = {"1w": 3, "1d": 2.5, "4h": 2, "1h": 1, "15m": 0.5}
    total_weight = sum(weights.values())
    buy_score = 0
    sell_score = 0

    for tf, data in results.items():
        w = weights.get(tf, 1)
        rec = data.get("recommendation", "NEUTRAL")
        if "BUY" in rec:
            buy_score += w * (2 if "STRONG" in rec else 1)
        elif "SELL" in rec:
            sell_score += w * (2 if "STRONG" in rec else 1)

    net = (buy_score - sell_score) / (total_weight * 2) * 100
    if net > 20:
        direction = "BUY"
    elif net < -20:
        direction = "SELL"
    else:
        direction = "NEUTRAL"

    return {
        "symbol": symbol.upper(),
        "exchange": exchange.upper(),
        "timeframes": results,
        "alignment": {
            "score": round(net, 1),
            "direction": direction,
            "buy_weight": round(buy_score, 1),
            "sell_weight": round(sell_score, 1),
            "detail": f"{direction} signal across {len([t for t in results.values() if 'BUY' in t.get('recommendation','')])} of {len(MTF_TIMEFRAMES)} timeframes",
        },
    }


def scan_by_signal(symbols: list[str], signal: str, exchange: str = "NASDAQ") -> list[str]:
    """
    Filter a list of symbols by TA signal type.

    signal options:
        'oversold'      — RSI < 30
        'overbought'    — RSI > 70
        'trending_up'   — price > SMA200 and SMA50 > SMA200
        'trending_down' — price < SMA200
        'golden_cross'  — SMA50 crossed above SMA200 (RSI based proxy)
        'breakout'      — RSI 50-70, price making new highs proxy
        'buy_signal'    — TV recommendation = BUY or STRONG_BUY
        'sell_signal'   — TV recommendation = SELL or STRONG_SELL
    """
    if not HAS_TV_TA:
        return []

    matched = []
    for sym in symbols:
        try:
            a = analyze(sym, exchange, "1d")
            if "error" in a:
                continue
            ind = a.get("indicators", {})
            rec = a.get("recommendation", {}).get("summary", "NEUTRAL")
            rsi = ind.get("RSI", 50)
            sma50 = ind.get("SMA50", 0)
            sma200 = ind.get("SMA200", 0)
            close = ind.get("close", 0)

            match = False
            if signal == "oversold" and rsi < 30:
                match = True
            elif signal == "overbought" and rsi > 70:
                match = True
            elif signal == "trending_up" and close > sma200 > 0 and sma50 > sma200:
                match = True
            elif signal == "trending_down" and close < sma200 > 0:
                match = True
            elif signal == "golden_cross" and sma50 > sma200 > 0 and rsi > 45:
                match = True
            elif signal == "breakout" and 50 <= rsi <= 70 and sma50 > sma200 > 0:
                match = True
            elif signal == "buy_signal" and "BUY" in rec:
                match = True
            elif signal == "sell_signal" and "SELL" in rec:
                match = True

            if match:
                matched.append(sym)
        except Exception:
            continue

    return matched


# ── Backtesting ───────────────────────────────────────────────────────────────

def backtest_strategy(
    symbol: str,
    strategy: str = "rsi",
    period_days: int = 365,
    exchange: str = "NASDAQ",
    commission: float = 0.001,
) -> dict:
    """
    Backtest one of 6 strategies on historical data.

    Strategies: rsi, bollinger, macd, ema_cross, supertrend (approx), donchian
    Returns: total_return, sharpe, max_drawdown, win_rate, num_trades, vs_buyhold
    """
    if not HAS_YF or not HAS_PANDAS:
        return {"error": "yfinance and pandas required: pip install yfinance pandas pandas_ta"}

    ticker = symbol.replace("NASDAQ:", "").replace("NYSE:", "").replace("AMEX:", "")
    end = datetime.now()
    start = end - timedelta(days=period_days + 60)  # extra for indicator warmup

    try:
        df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
        if df.empty:
            return {"error": f"No data for {ticker}"}
    except Exception as e:
        return {"error": f"Data download failed: {e}"}

    df = df.dropna()
    if len(df) < 60:
        return {"error": f"Insufficient data: {len(df)} rows"}

    # Generate signals based on strategy
    df = _add_indicators(df)
    df = _generate_signals(df, strategy)

    # Simulate trades
    trades, equity_curve = _simulate_trades(df, commission)

    if not trades:
        return {
            "symbol": ticker,
            "strategy": strategy,
            "period_days": period_days,
            "num_trades": 0,
            "total_return": 0,
            "note": "No trades generated in this period",
        }

    # Metrics
    returns = [t["pnl_pct"] for t in trades]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]

    total_return = round((equity_curve[-1] / equity_curve[0] - 1) * 100, 2)
    buy_hold_return = round((float(df["Close"].iloc[-1]) / float(df["Close"].iloc[0]) - 1) * 100, 2)

    # Sharpe (annualized, daily returns)
    if len(equity_curve) > 1:
        daily_rets = pd.Series(equity_curve).pct_change().dropna()
        sharpe = round(daily_rets.mean() / daily_rets.std() * (252 ** 0.5), 2) if daily_rets.std() > 0 else 0.0
    else:
        sharpe = 0.0

    # Max drawdown
    curve = pd.Series(equity_curve)
    rolling_max = curve.cummax()
    drawdown = (curve - rolling_max) / rolling_max
    max_dd = round(drawdown.min() * 100, 2)

    # Profit factor
    gross_profit = sum(r for r in returns if r > 0)
    gross_loss = abs(sum(r for r in returns if r < 0))
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf")

    return {
        "symbol": ticker,
        "strategy": strategy,
        "period_days": period_days,
        "num_trades": len(trades),
        "total_return_pct": total_return,
        "buy_hold_return_pct": buy_hold_return,
        "alpha_pct": round(total_return - buy_hold_return, 2),
        "win_rate_pct": round(len(wins) / len(returns) * 100, 1) if returns else 0,
        "sharpe_ratio": sharpe,
        "max_drawdown_pct": max_dd,
        "profit_factor": profit_factor,
        "avg_win_pct": round(sum(wins) / len(wins), 2) if wins else 0,
        "avg_loss_pct": round(sum(losses) / len(losses), 2) if losses else 0,
        "best_trade_pct": round(max(returns), 2) if returns else 0,
        "worst_trade_pct": round(min(returns), 2) if returns else 0,
        "commission_used": commission,
    }


def _add_indicators(df) -> "pd.DataFrame":
    """Add all indicators needed for backtesting strategies."""
    import pandas as pd

    close = df["Close"].squeeze()
    high = df["High"].squeeze()
    low = df["Low"].squeeze()

    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss
    df["RSI"] = 100 - (100 / (1 + rs))

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["MACD"] = ema12 - ema26
    df["MACD_signal"] = df["MACD"].ewm(span=9, adjust=False).mean()

    # Bollinger Bands
    df["BB_basis"] = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    df["BB_upper"] = df["BB_basis"] + 2 * bb_std
    df["BB_lower"] = df["BB_basis"] - 2 * bb_std

    # EMAs / SMAs
    df["EMA20"] = close.ewm(span=20, adjust=False).mean()
    df["EMA50"] = close.ewm(span=50, adjust=False).mean()
    df["SMA50"] = close.rolling(50).mean()
    df["SMA200"] = close.rolling(200).mean()

    # ATR (for Supertrend)
    hl = high - low
    hc = (high - close.shift()).abs()
    lc = (low - close.shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    df["ATR"] = tr.rolling(10).mean()

    # Donchian
    df["DC_high"] = high.rolling(20).max()
    df["DC_low"] = low.rolling(20).min()

    return df.dropna()


def _generate_signals(df, strategy: str) -> "pd.DataFrame":
    """Add signal column: 1 = buy, -1 = sell, 0 = hold."""
    df = df.copy()
    close = df["Close"].squeeze()

    if strategy == "rsi":
        df["signal"] = 0
        df.loc[df["RSI"] < 30, "signal"] = 1
        df.loc[df["RSI"] > 70, "signal"] = -1

    elif strategy == "bollinger":
        df["signal"] = 0
        df.loc[close <= df["BB_lower"], "signal"] = 1
        df.loc[close >= df["BB_upper"], "signal"] = -1

    elif strategy == "macd":
        df["signal"] = 0
        prev_macd = df["MACD"].shift(1)
        prev_sig = df["MACD_signal"].shift(1)
        df.loc[(df["MACD"] > df["MACD_signal"]) & (prev_macd <= prev_sig), "signal"] = 1
        df.loc[(df["MACD"] < df["MACD_signal"]) & (prev_macd >= prev_sig), "signal"] = -1

    elif strategy == "ema_cross":
        df["signal"] = 0
        prev_ema20 = df["EMA20"].shift(1)
        prev_ema50 = df["EMA50"].shift(1)
        df.loc[(df["EMA20"] > df["EMA50"]) & (prev_ema20 <= prev_ema50), "signal"] = 1
        df.loc[(df["EMA20"] < df["EMA50"]) & (prev_ema20 >= prev_ema50), "signal"] = -1

    elif strategy == "supertrend":
        # Simplified ATR-based trend following
        df["signal"] = 0
        upper = (df["High"].squeeze() + df["Low"].squeeze()) / 2 + 1.5 * df["ATR"]
        lower = (df["High"].squeeze() + df["Low"].squeeze()) / 2 - 1.5 * df["ATR"]
        df.loc[close > upper.shift(1), "signal"] = 1
        df.loc[close < lower.shift(1), "signal"] = -1

    elif strategy == "donchian":
        df["signal"] = 0
        df.loc[close >= df["DC_high"].shift(1), "signal"] = 1
        df.loc[close <= df["DC_low"].shift(1), "signal"] = -1

    else:
        df["signal"] = 0

    return df


def _simulate_trades(df, commission: float) -> tuple[list, list]:
    """Simulate long-only trades from signal column. Returns (trades, equity_curve)."""
    import pandas as pd

    trades = []
    equity = 10000.0
    equity_curve = [equity]
    in_trade = False
    entry_price = 0.0
    entry_date = None

    close = df["Close"].squeeze()

    for i in range(1, len(df)):
        sig = df["signal"].iloc[i]
        price = float(close.iloc[i])
        date = df.index[i]

        if not in_trade and sig == 1:
            in_trade = True
            entry_price = price * (1 + commission)
            entry_date = date

        elif in_trade and sig == -1:
            exit_price = price * (1 - commission)
            pnl_pct = (exit_price / entry_price - 1) * 100
            equity *= (1 + pnl_pct / 100)
            trades.append({
                "entry_date": str(entry_date)[:10],
                "exit_date": str(date)[:10],
                "entry_price": round(entry_price, 2),
                "exit_price": round(exit_price, 2),
                "pnl_pct": round(pnl_pct, 2),
            })
            in_trade = False
            equity_curve.append(equity)

    return trades, equity_curve
