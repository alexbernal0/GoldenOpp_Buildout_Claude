"""
sentiment.py — News and sentiment analysis for trading research.

Sources:
  - RSS feeds: Reuters, Yahoo Finance, Mining.com, MarketWatch
  - Simple keyword sentiment scoring (no external API keys needed)
  - Optional Reddit via PRAW (if configured)
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta
from typing import Optional

try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ── Sentiment lexicon ─────────────────────────────────────────────────────────

BULLISH_WORDS = [
    "surge", "rally", "soar", "jump", "rise", "gain", "climb", "bull",
    "upgrade", "outperform", "beat", "record", "high", "boom", "strong",
    "positive", "growth", "breakout", "buy", "upside", "optimistic",
    "profit", "revenue beat", "earnings beat", "acquisition", "partnership",
    "gold rush", "silver lining", "discovery", "resource upgrade",
]

BEARISH_WORDS = [
    "crash", "fall", "drop", "decline", "plunge", "sink", "bear",
    "downgrade", "underperform", "miss", "low", "weak", "loss", "sell",
    "downside", "pessimistic", "cut", "layoff", "shutdown", "halt",
    "warning", "risk", "concern", "disappointing", "below expectations",
    "write-down", "impairment", "strike", "permit denied",
]

# ── RSS Feed sources ──────────────────────────────────────────────────────────

RSS_FEEDS = {
    "reuters_business": "https://feeds.reuters.com/reuters/businessNews",
    "reuters_markets": "https://feeds.reuters.com/reuters/marketsNews",
    "marketwatch": "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines",
    "mining_com": "https://www.mining.com/feed/",
    "kitco": "https://www.kitco.com/rss/kitcoNewsRSS.xml",
    "seekingalpha_gold": "https://seekingalpha.com/tag/gold-and-precious-metals.xml",
}

# Cache: {ticker: (timestamp, result)}
_news_cache: dict[str, tuple[float, list]] = {}
CACHE_TTL = 300  # 5 minutes


# ── Core Functions ────────────────────────────────────────────────────────────

def get_news(ticker: str, max_items: int = 10) -> list[dict]:
    """
    Fetch news for a ticker from RSS feeds.
    Returns list of {title, summary, source, url, published, sentiment}.
    """
    if not HAS_FEEDPARSER:
        return [{"error": "feedparser not installed. Run: pip install feedparser"}]

    # Check cache
    cache_key = ticker.upper()
    if cache_key in _news_cache:
        ts, cached = _news_cache[cache_key]
        if time.time() - ts < CACHE_TTL:
            return cached[:max_items]

    ticker_upper = ticker.upper()
    all_news = []

    # Try Yahoo Finance RSS first (most reliable for individual stocks)
    yahoo_url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker_upper}&region=US&lang=en-US"
    try:
        feed = feedparser.parse(yahoo_url)
        for entry in feed.entries[:15]:
            all_news.append({
                "title": entry.get("title", ""),
                "summary": entry.get("summary", "")[:200],
                "source": "Yahoo Finance",
                "url": entry.get("link", ""),
                "published": entry.get("published", ""),
                "ticker_match": True,
            })
    except Exception:
        pass

    # Mining-specific sources if ticker matches mining keywords
    mining_tickers = {"GOLD", "NEM", "AEM", "WPM", "KGC", "AGI", "PAAS", "HL", "CDE", "AG"}
    is_miner = ticker_upper in mining_tickers

    if is_miner:
        for source_name, url in [("Mining.com", RSS_FEEDS["mining_com"]),
                                   ("Kitco", RSS_FEEDS["kitco"])]:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:10]:
                    title = entry.get("title", "")
                    summary = entry.get("summary", "")
                    # Filter for relevance
                    combined = (title + " " + summary).lower()
                    if ticker_upper.lower() in combined or "gold" in combined or "silver" in combined:
                        all_news.append({
                            "title": title,
                            "summary": summary[:200],
                            "source": source_name,
                            "url": entry.get("link", ""),
                            "published": entry.get("published", ""),
                            "ticker_match": ticker_upper.lower() in combined,
                        })
            except Exception:
                continue

    # Score sentiment for each article
    scored = []
    for item in all_news:
        text = (item["title"] + " " + item["summary"]).lower()
        bull = sum(1 for w in BULLISH_WORDS if w in text)
        bear = sum(1 for w in BEARISH_WORDS if w in text)
        score = (bull - bear) / max(bull + bear, 1)
        label = "BULLISH" if score > 0.1 else "BEARISH" if score < -0.1 else "NEUTRAL"
        scored.append({**item, "sentiment_score": round(score, 2), "sentiment": label})

    # Sort: ticker matches first, then by recency
    scored.sort(key=lambda x: (not x.get("ticker_match", False), 0))

    # Cache result
    _news_cache[cache_key] = (time.time(), scored)

    return scored[:max_items]


def market_sentiment_score(ticker: str) -> dict:
    """
    Aggregate sentiment score for a ticker from news.

    Returns:
        {
            ticker, score (-1 to 1), label (BULLISH/BEARISH/NEUTRAL),
            article_count, bullish_count, bearish_count, neutral_count,
            top_headlines: [str]
        }
    """
    news = get_news(ticker, max_items=20)

    if not news or (len(news) == 1 and "error" in news[0]):
        return {
            "ticker": ticker,
            "score": 0.0,
            "label": "NEUTRAL",
            "article_count": 0,
            "note": "No news found or feedparser not available",
        }

    scores = [item.get("sentiment_score", 0) for item in news]
    bullish = sum(1 for item in news if item.get("sentiment") == "BULLISH")
    bearish = sum(1 for item in news if item.get("sentiment") == "BEARISH")
    neutral = sum(1 for item in news if item.get("sentiment") == "NEUTRAL")

    avg_score = sum(scores) / len(scores) if scores else 0
    label = "BULLISH" if avg_score > 0.1 else "BEARISH" if avg_score < -0.1 else "NEUTRAL"

    top_headlines = [item["title"] for item in news[:5]]

    return {
        "ticker": ticker,
        "score": round(avg_score, 3),
        "label": label,
        "article_count": len(news),
        "bullish_count": bullish,
        "bearish_count": bearish,
        "neutral_count": neutral,
        "top_headlines": top_headlines,
    }


def combined_analysis(ticker: str, tv_data: dict | None = None) -> dict:
    """
    Merge TA signal + news sentiment into a single confluence decision.

    tv_data: optional dict from tv_orchestrator (RSI, MA recommendation, etc.)

    Returns:
        {
            ticker, decision (BUY/SELL/HOLD/WATCH),
            confidence (0-100), signals: [str], summary: str
        }
    """
    sentiment = market_sentiment_score(ticker)
    signals = []
    buy_score = 0
    sell_score = 0

    # Sentiment signal
    if sentiment["label"] == "BULLISH":
        buy_score += 2
        signals.append(f"News BULLISH ({sentiment['article_count']} articles, score={sentiment['score']:.2f})")
    elif sentiment["label"] == "BEARISH":
        sell_score += 2
        signals.append(f"News BEARISH ({sentiment['article_count']} articles, score={sentiment['score']:.2f})")
    else:
        signals.append(f"News NEUTRAL ({sentiment['article_count']} articles)")

    # TA signal (if provided)
    if tv_data:
        rec = tv_data.get("recommendation", {}).get("summary", "")
        rsi = tv_data.get("indicators", {}).get("RSI", 50)
        sma50 = tv_data.get("indicators", {}).get("SMA50", 0)
        sma200 = tv_data.get("indicators", {}).get("SMA200", 0)

        if "STRONG_BUY" in rec:
            buy_score += 3
            signals.append("TA: STRONG BUY")
        elif "BUY" in rec:
            buy_score += 2
            signals.append("TA: BUY")
        elif "STRONG_SELL" in rec:
            sell_score += 3
            signals.append("TA: STRONG SELL")
        elif "SELL" in rec:
            sell_score += 2
            signals.append("TA: SELL")
        else:
            signals.append("TA: NEUTRAL")

        if rsi < 30:
            buy_score += 1
            signals.append(f"RSI oversold ({rsi:.1f})")
        elif rsi > 70:
            sell_score += 1
            signals.append(f"RSI overbought ({rsi:.1f})")

        if sma50 > sma200 > 0:
            buy_score += 1
            signals.append("Golden cross (SMA50 > SMA200)")
        elif sma50 < sma200 and sma200 > 0:
            sell_score += 1
            signals.append("Death cross (SMA50 < SMA200)")

    # Confidence and decision
    total = buy_score + sell_score
    if total == 0:
        decision = "HOLD"
        confidence = 50
    else:
        if buy_score > sell_score:
            decision = "BUY" if buy_score >= 3 else "WATCH"
            confidence = int(min(buy_score / max(total, 1) * 100, 95))
        else:
            decision = "SELL" if sell_score >= 3 else "CAUTION"
            confidence = int(min(sell_score / max(total, 1) * 100, 95))

    return {
        "ticker": ticker,
        "decision": decision,
        "confidence": confidence,
        "signals": signals,
        "buy_score": buy_score,
        "sell_score": sell_score,
        "sentiment": sentiment,
        "summary": f"{decision} ({confidence}% confidence) — {len(signals)} signals: {', '.join(signals[:2])}",
    }
