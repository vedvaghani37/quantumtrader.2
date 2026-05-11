# ============================================================
# SIGNALS MODULE — News, Earnings & Analyst Ratings
# ============================================================

import re
import time
import logging
import requests
import numpy as np
import yfinance as yf
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from config import NEWS_API_KEY, BUY_SENTIMENT_MIN, SELL_SENTIMENT_MAX, ANALYST_WEIGHT

logger = logging.getLogger(__name__)

BULLISH_WORDS = {
    "beat","beats","surge","surges","rally","rallies","upgrade","upgraded",
    "outperform","buy","strong","record","profit","growth","gain","gains",
    "bullish","positive","exceed","exceeds","raise","raised","overweight",
    "breakout","momentum","innovation","partnership","deal","contract",
    "expansion","dividend","buyback","repurchase",
}
BEARISH_WORDS = {
    "miss","misses","missed","fall","falls","drop","drops","crash",
    "downgrade","downgraded","underperform","sell","weak","loss","losses",
    "decline","declines","bearish","negative","lawsuit","investigation",
    "fraud","recall","warning","cut","layoff","layoffs","restructure",
    "debt","default","disappoints",
}

def _keyword_score(text: str) -> float:
    if not text:
        return 0.0
    words = set(re.findall(r"\b\w+\b", text.lower()))
    bull  = len(words & BULLISH_WORDS)
    bear  = len(words & BEARISH_WORDS)
    total = bull + bear
    return 0.0 if total == 0 else (bull - bear) / total


@dataclass
class SignalResult:
    ticker:           str
    news_score:       float = 0.0
    earnings_score:   float = 0.0
    analyst_score:    float = 0.0
    composite_score:  float = 0.0
    num_articles:     int   = 0
    headline_samples: list  = field(default_factory=list)
    signal:           str   = "NEUTRAL"
    timestamp:        str   = ""

    def __post_init__(self):
        self.composite_score = (
            0.50 * self.news_score
            + 0.20 * self.earnings_score
            + ANALYST_WEIGHT * self.analyst_score
        )
        if self.composite_score >= BUY_SENTIMENT_MIN:
            self.signal = "BUY"
        elif self.composite_score <= SELL_SENTIMENT_MAX:
            self.signal = "SELL"
        else:
            self.signal = "NEUTRAL"
        self.timestamp = datetime.now().isoformat()


def fetch_news_sentiment(ticker: str, company_name: str = "") -> tuple:
    headlines = []
    if NEWS_API_KEY:
        query = company_name if company_name else ticker
        try:
            r = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": f'"{query}" stock',
                    "from": (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d"),
                    "sortBy": "relevancy", "pageSize": 20,
                    "language": "en", "apiKey": NEWS_API_KEY,
                },
                timeout=8,
            )
            if r.status_code == 200:
                headlines = [
                    a.get("title","") + " " + (a.get("description") or "")
                    for a in r.json().get("articles", [])
                ]
        except Exception as e:
            logger.debug(f"NewsAPI error for {ticker}: {e}")

    if not headlines:
        try:
            headlines = [n.get("title","") for n in (yf.Ticker(ticker).news or [])[:15]]
        except Exception as e:
            logger.debug(f"yfinance news error for {ticker}: {e}")

    if not headlines:
        return 0.0, 0, []
    scores = [_keyword_score(h) for h in headlines]
    return float(np.mean(scores)), len(headlines), [h[:100] for h in headlines[:3]]


def fetch_earnings_signal(ticker: str) -> float:
    try:
        dates_df = yf.Ticker(ticker).get_earnings_dates(limit=4)
        if dates_df is not None and not dates_df.empty:
            cols = [c for c in dates_df.columns
                    if any(k in c.lower() for k in ["estimate","reported","actual"])]
            if len(cols) >= 2:
                df = dates_df[cols].dropna()
                if not df.empty:
                    latest = df.iloc[0]
                    est, act = float(latest.iloc[0]), float(latest.iloc[1])
                    if est != 0:
                        return float(np.clip((act - est) / abs(est) * 2, -1.0, 1.0))
    except Exception as e:
        logger.debug(f"Earnings signal error for {ticker}: {e}")
    return 0.0


_RATING_MAP = {
    "strong buy": 1.0, "strong-buy": 1.0, "top pick": 1.0,
    "buy": 0.7, "overweight": 0.7, "outperform": 0.7,
    "market outperform": 0.7, "sector outperform": 0.6,
    "add": 0.5, "accumulate": 0.5,
    "neutral": 0.0, "hold": 0.0, "equal-weight": 0.0,
    "market perform": 0.0, "sector perform": 0.0, "in-line": 0.0,
    "underperform": -0.6, "sector underperform": -0.6,
    "market underperform": -0.6, "underweight": -0.7,
    "sell": -0.8, "strong sell": -1.0, "reduce": -0.5,
}


def fetch_analyst_signal(ticker: str) -> float:
    try:
        recs = yf.Ticker(ticker).recommendations
        if recs is None or recs.empty:
            return 0.0
        scores, weights = [], []
        for i, (_, row) in enumerate(recs.tail(5).iterrows()):
            action   = str(row.get("Action",   "")).lower().strip()
            to_grade = str(row.get("To Grade", "")).lower().strip()
            if action == "up":       s = 0.6
            elif action == "down":   s = -0.6
            elif to_grade in _RATING_MAP: s = _RATING_MAP[to_grade]
            else: s = next((v for k,v in _RATING_MAP.items() if k in to_grade), 0.0)
            scores.append(s); weights.append(i + 1)
        if not scores:
            return 0.0
        return float(np.clip(np.average(scores, weights=weights), -1.0, 1.0))
    except Exception as e:
        logger.debug(f"Analyst signal error for {ticker}: {e}")
        return 0.0


def get_full_signal(ticker: str, company_name: str = "") -> SignalResult:
    news_score, num_articles, samples = fetch_news_sentiment(ticker, company_name)
    result = SignalResult(
        ticker=ticker,
        news_score=news_score,
        earnings_score=fetch_earnings_signal(ticker),
        analyst_score=fetch_analyst_signal(ticker),
        num_articles=num_articles,
        headline_samples=samples,
    )
    logger.info(
        f"[{ticker}] {result.signal} | composite={result.composite_score:+.2f} "
        f"(news={news_score:+.2f}, earn={result.earnings_score:+.2f}, "
        f"analyst={result.analyst_score:+.2f})"
    )
    return result


def batch_signals(tickers: list, delay_sec: float = 0.3) -> dict:
    results = {}
    for ticker in tickers:
        try:
            sig = get_full_signal(ticker)
            if sig.signal in ("BUY", "SELL"):
                results[ticker] = sig
            time.sleep(delay_sec)
        except Exception as e:
            logger.warning(f"Signal error for {ticker}: {e}")
    return results
