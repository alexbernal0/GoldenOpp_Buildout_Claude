"""
screener.py â€” TradingView public screener API wrapper.

Uses TradingView's undocumented but public scanner REST API.
No authentication required. Same access as the website without login.

API endpoint: https://scanner.tradingview.com/<market>/scan
"""

import json
import time
from functools import lru_cache
from typing import Any

try:
    import requests
    SESSION = requests.Session()
    SESSION.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/json",
        "Origin": "https://www.tradingview.com",
        "Referer": "https://www.tradingview.com/",
    })
except ImportError:
    SESSION = None

# â”€â”€ Constants â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

SCAN_BASE = "https://scanner.tradingview.com"
_RATE_LIMIT_DELAY = 0.3  # seconds between API calls to avoid 429s

MARKET_ENDPOINTS = {
    "america": f"{SCAN_BASE}/america/scan",
    "crypto": f"{SCAN_BASE}/crypto/scan",
    "forex": f"{SCAN_BASE}/forex/scan",
    "etf": f"{SCAN_BASE}/etf/scan",
    "global": f"{SCAN_BASE}/global/scan",
}

DEFAULT_COLUMNS = [
    "name", "close", "change", "change_abs", "volume", "market_cap_basic",
    "RSI", "RSI[1]", "MACD.macd", "MACD.signal",
    "price_earnings_ttm", "price_book_fq",
    "return_on_equity", "gross_margin_ttm", "net_margin_ttm",
    "piotroski_f_score_ttm", "altman_z_score_ttm",
    "SMA50", "SMA200", "EMA20",
    "sector", "industry", "exchange",
    "Perf.W", "Perf.1M", "Perf.3M", "Perf.Y",
    "price_52_week_high", "price_52_week_low",
    "beta_1_year", "average_volume_90d_calc",
    "debt_to_equity", "current_ratio",
    "total_revenue_yoy_growth_ttm", "earnings_per_share_diluted_ttm",
]

FUNDAMENTAL_COLUMNS = [
    "name", "close", "market_cap_basic",
    "price_earnings_ttm", "price_book_fq", "price_sales_current",
    "enterprise_value_ebitda_ttm", "price_earnings_growth_ttm",
    "return_on_equity", "return_on_assets",
    "gross_margin_ttm", "operating_margin_ttm", "net_margin_ttm",
    "total_revenue_yoy_growth_ttm", "earnings_per_share_diluted_yoy_growth_ttm",
    "debt_to_equity", "current_ratio", "free_cash_flow_ttm",
    "dividend_yield_recent", "continuous_dividend_payout_years",
    "piotroski_f_score_ttm", "altman_z_score_ttm", "graham_numbers_ttm",
    "Recommend.All", "analyst_recommendations_buy", "analyst_recommendations_sell",
    "price_target_average",
    "sector", "industry", "exchange",
    "RSI", "SMA50", "SMA200", "Perf.W", "Perf.1M", "Perf.3M", "Perf.Y",
    "beta_1_year",
]

# â”€â”€ Presets â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

PRESETS = {
    "value_stocks": {
        "filters": [
            {"left": "price_earnings_ttm", "operation": "less", "right": 15},
            {"left": "price_book_fq", "operation": "less", "right": 1.5},
            {"left": "return_on_equity", "operation": "greater", "right": 10},
            {"left": "market_cap_basic", "operation": "greater", "right": 1e9},
        ],
        "sort_by": "piotroski_f_score_ttm",
    },
    "momentum_stocks": {
        "filters": [
            {"left": "RSI", "operation": "in_range", "right": [50, 70]},
            {"left": "Perf.1M", "operation": "greater", "right": 5},
            {"left": "market_cap_basic", "operation": "greater", "right": 5e8},
        ],
        "sort_by": "Perf.1M",
    },
    "breakout_scanner": {
        "filters": [
            {"left": "RSI", "operation": "in_range", "right": [50, 75]},
            {"left": "Perf.W", "operation": "greater", "right": 2},
            {"left": "average_volume_90d_calc", "operation": "greater", "right": 500000},
        ],
        "sort_by": "Perf.W",
    },
    "quality_stocks": {
        "filters": [
            {"left": "return_on_equity", "operation": "greater", "right": 12},
            {"left": "debt_to_equity", "operation": "less", "right": 1.0},
            {"left": "piotroski_f_score_ttm", "operation": "greater", "right": 6},
            {"left": "market_cap_basic", "operation": "greater", "right": 1e9},
        ],
        "sort_by": "piotroski_f_score_ttm",
    },
    "oversold_miners": {
        "filters": [
            {"left": "RSI", "operation": "less", "right": 40},
            {"left": "sector", "operation": "equal", "right": "Non-Energy Minerals"},
            {"left": "market_cap_basic", "operation": "greater", "right": 1e8},
        ],
        "sort_by": "RSI",
        "sort_order": "asc",
    },
    "mining_momentum": {
        "filters": [
            {"left": "RSI", "operation": "in_range", "right": [45, 70]},
            {"left": "sector", "operation": "equal", "right": "Non-Energy Minerals"},
            {"left": "Perf.1M", "operation": "greater", "right": 1},
        ],
        "sort_by": "Perf.1M",
    },
}

# â”€â”€ Internal helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _post(url: str, payload: dict, retries: int = 3) -> list[dict]:
    """POST to screener API, return list of result rows."""
    if SESSION is None:
        raise RuntimeError("requests library required: pip install requests")

    for attempt in range(retries):
        try:
            time.sleep(_RATE_LIMIT_DELAY)
            r = SESSION.post(url, json=payload, timeout=15)
            r.raise_for_status()
            data = r.json()
            rows = data.get("data", [])
            columns = payload.get("columns", [])
            results = []
            for row in rows:
                d = row.get("d", [])
                record = {"ticker": row.get("s", "")}
                for i, col in enumerate(columns):
                    record[col] = d[i] if i < len(d) else None
                results.append(record)
            return results
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise RuntimeError(f"Screener API error after {retries} attempts: {e}")


def _build_payload(
    filters: list,
    markets: list = None,
    sort_by: str = "market_cap_basic",
    sort_order: str = "desc",
    limit: int = 50,
    columns: list = None,
) -> dict:
    return {
        "filter": filters,
        "options": {"lang": "en"},
        "markets": markets or ["america"],
        "symbols": {"query": {"types": []}, "tickers": []},
        "columns": columns or DEFAULT_COLUMNS,
        "sort": {"sortBy": sort_by, "sortOrder": sort_order},
        "range": [0, min(limit, 200)],
    }


# â”€â”€ Public API â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def screen_stocks(
    filters: list = None,
    markets: list = None,
    sort_by: str = "market_cap_basic",
    sort_order: str = "desc",
    limit: int = 50,
    columns: list = None,
) -> list[dict]:
    """
    Screen stocks with custom filters.

    filters example:
        [{"left": "RSI", "operation": "less", "right": 30}]

    Supported operations: less, greater, equal, not_equal, in_range,
        crosses_above, crosses_below, less_or_equal, greater_or_equal
    """
    payload = _build_payload(
        filters=filters or [],
        markets=markets or ["america"],
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        columns=columns,
    )
    return _post(MARKET_ENDPOINTS["america"], payload)


def screen_crypto(
    filters: list = None,
    sort_by: str = "market_cap_basic",
    limit: int = 50,
) -> list[dict]:
    """Screen cryptocurrencies."""
    payload = _build_payload(
        filters=filters or [],
        markets=["crypto"],
        sort_by=sort_by,
        limit=limit,
        columns=["name", "close", "change", "volume", "market_cap_basic",
                 "RSI", "Perf.W", "Perf.1M", "Volatility.M"],
    )
    return _post(MARKET_ENDPOINTS["crypto"], payload)


def lookup_symbols(symbols: list, columns: list = None) -> list[dict]:
    """
    Direct lookup by exact ticker symbols.
    symbols: ['NASDAQ:AAPL', 'NYSE:GOLD', 'NYSE:NEM']
    """
    payload = {
        "symbols": {"tickers": symbols},
        "columns": columns or DEFAULT_COLUMNS,
    }
    return _post(MARKET_ENDPOINTS["america"], payload)


def get_preset(preset_name: str) -> dict:
    """Return a named preset config dict."""
    if preset_name not in PRESETS:
        available = list(PRESETS.keys())
        raise ValueError(f"Unknown preset '{preset_name}'. Available: {available}")
    return PRESETS[preset_name]


def run_preset(preset_name: str, limit: int = 50, columns: list = None) -> list[dict]:
    """Run a named preset and return results."""
    preset = get_preset(preset_name)
    return screen_stocks(
        filters=preset.get("filters", []),
        sort_by=preset.get("sort_by", "market_cap_basic"),
        sort_order=preset.get("sort_order", "desc"),
        limit=limit,
        columns=columns,
    )


def due_diligence(ticker: str, exchange: str = "NYSE") -> dict:
    """
    Full fundamental + technical snapshot for one ticker.
    Returns structured dict: valuation, profitability, growth, balance_sheet, technicals, performance.
    """
    symbol = f"{exchange}:{ticker}" if ":" not in ticker else ticker
    rows = lookup_symbols([symbol], columns=FUNDAMENTAL_COLUMNS)

    if not rows:
        # Try NASDAQ
        symbol_nasdaq = f"NASDAQ:{ticker}"
        rows = lookup_symbols([symbol_nasdaq], columns=FUNDAMENTAL_COLUMNS)

    if not rows:
        return {"error": f"Symbol not found: {ticker}", "ticker": ticker}

    r = rows[0]

    def safe(key: str, fmt=None):
        v = r.get(key)
        if v is None:
            return "N/A"
        if fmt == "pct":
            return f"{v:.1f}%"
        if fmt == "2f":
            return round(v, 2)
        return v

    return {
        "ticker": ticker,
        "symbol": r.get("ticker", symbol),
        "price": safe("close", "2f"),
        "valuation": {
            "P/E": safe("price_earnings_ttm", "2f"),
            "P/B": safe("price_book_fq", "2f"),
            "P/S": safe("price_sales_current", "2f"),
            "EV/EBITDA": safe("enterprise_value_ebitda_ttm", "2f"),
            "PEG": safe("price_earnings_growth_ttm", "2f"),
        },
        "profitability": {
            "ROE": safe("return_on_equity", "pct"),
            "ROA": safe("return_on_assets", "pct"),
            "ROIC": safe("return_on_invested_capital_fq", "pct"),
            "Gross Margin": safe("gross_margin_ttm", "pct"),
            "Operating Margin": safe("operating_margin_ttm", "pct"),
            "Net Margin": safe("net_margin_ttm", "pct"),
        },
        "growth": {
            "Revenue Growth YoY": safe("total_revenue_yoy_growth_ttm", "pct"),
            "EPS Growth YoY": safe("earnings_per_share_diluted_yoy_growth_ttm", "pct"),
            "EPS TTM": safe("earnings_per_share_diluted_ttm", "2f"),
        },
        "balance_sheet": {
            "D/E Ratio": safe("debt_to_equity", "2f"),
            "Current Ratio": safe("current_ratio", "2f"),
            "FCF TTM": safe("free_cash_flow_ttm"),
        },
        "composite_scores": {
            "Piotroski F-Score": safe("piotroski_f_score_ttm"),
            "Altman Z-Score": safe("altman_z_score_ttm", "2f"),
            "Graham Number": safe("graham_numbers_ttm", "2f"),
            "Analyst Rec": safe("Recommend.All", "2f"),
            "Price Target": safe("price_target_average", "2f"),
        },
        "technicals": {
            "RSI": safe("RSI", "2f"),
            "SMA50": safe("SMA50", "2f"),
            "SMA200": safe("SMA200", "2f"),
            "Beta 1Y": safe("beta_1_year", "2f"),
        },
        "performance": {
            "1 Week": safe("Perf.W", "pct"),
            "1 Month": safe("Perf.1M", "pct"),
            "3 Month": safe("Perf.3M", "pct"),
            "1 Year": safe("Perf.Y", "pct"),
        },
        "sector": safe("sector"),
        "industry": safe("industry"),
        "exchange": safe("exchange"),
    }


def screen_miners(limit: int = 20) -> list[dict]:
    """Screen for mining stocks in Non-Energy Minerals sector."""
    return screen_stocks(
        filters=[
            {"left": "sector", "operation": "equal", "right": "Non-Energy Minerals"},
            {"left": "market_cap_basic", "operation": "greater", "right": 1e8},
        ],
        sort_by="market_cap_basic",
        limit=limit,
    )

