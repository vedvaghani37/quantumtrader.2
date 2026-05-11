# ============================================================
# TECHNICAL ANALYSIS MODULE
# ============================================================

import numpy as np
import pandas as pd
import yfinance as yf
import logging
from dataclasses import dataclass
from typing import Optional
from config import RSI_OVERSOLD, RSI_OVERBOUGHT, MOMENTUM_WINDOW_DAYS, VOLUME_SPIKE_MULTIPLIER

logger = logging.getLogger(__name__)


@dataclass
class TechResult:
    ticker:        str
    rsi:           float = 50.0
    momentum_pct:  float = 0.0
    volume_spike:  bool  = False
    above_sma50:   bool  = False
    sma50_cross:   str   = "NONE"
    volatility:    float = 0.20
    tech_signal:   str   = "NEUTRAL"
    current_price: float = 0.0


def compute_rsi(closes: pd.Series, period: int = 14) -> float:
    delta    = closes.diff().dropna()
    gain     = delta.clip(lower=0)
    loss     = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs       = avg_gain / avg_loss.replace(0, np.nan)
    rsi      = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not rsi.empty else 50.0


def get_technicals(ticker: str) -> Optional[TechResult]:
    try:
        df = yf.download(ticker, period="3mo", interval="1d", progress=False, auto_adjust=True)
        if df.empty or len(df) < 20:
            return None

        closes        = df["Close"].squeeze()
        volumes       = df["Volume"].squeeze()
        current_price = float(closes.iloc[-1])

        rsi = compute_rsi(closes)

        if len(closes) > MOMENTUM_WINDOW_DAYS:
            base = float(closes.iloc[-MOMENTUM_WINDOW_DAYS])
            momentum_pct = (current_price - base) / base * 100 if base != 0 else 0.0
        else:
            momentum_pct = 0.0

        avg_vol      = float(volumes.iloc[-21:-1].mean()) if len(volumes) > 21 else float(volumes.mean())
        today_vol    = float(volumes.iloc[-1])
        volume_spike = avg_vol > 0 and (today_vol / avg_vol) >= VOLUME_SPIKE_MULTIPLIER

        sma50       = float(closes.rolling(50).mean().iloc[-1]) if len(closes) >= 50 else float(closes.mean())
        above_sma50 = current_price > sma50

        sma_cross = "NONE"
        if len(closes) >= 202:
            sma50_s  = closes.rolling(50).mean()
            sma200_s = closes.rolling(200).mean()
            if sma50_s.iloc[-1] > sma200_s.iloc[-1] and sma50_s.iloc[-2] <= sma200_s.iloc[-2]:
                sma_cross = "GOLDEN"
            elif sma50_s.iloc[-1] < sma200_s.iloc[-1] and sma50_s.iloc[-2] >= sma200_s.iloc[-2]:
                sma_cross = "DEATH"

        daily_returns = closes.pct_change().dropna()
        volatility    = float(daily_returns.std() * np.sqrt(252))
        if np.isnan(volatility) or volatility <= 0:
            volatility = 0.20

        score = 0
        if rsi < RSI_OVERSOLD:     score += 2
        if rsi > RSI_OVERBOUGHT:   score -= 2
        if momentum_pct > 5:       score += 1
        if momentum_pct < -5:      score -= 1
        if volume_spike:           score += 1
        if above_sma50:            score += 1
        else:                      score -= 1
        if sma_cross == "GOLDEN":  score += 2
        if sma_cross == "DEATH":   score -= 2

        tech_signal = "BUY" if score >= 2 else ("SELL" if score <= -2 else "NEUTRAL")

        return TechResult(
            ticker=ticker, rsi=rsi, momentum_pct=momentum_pct,
            volume_spike=volume_spike, above_sma50=above_sma50,
            sma50_cross=sma_cross, volatility=volatility,
            tech_signal=tech_signal, current_price=current_price,
        )
    except Exception as e:
        logger.debug(f"Technicals error for {ticker}: {e}")
        return None


def batch_technicals(tickers: list) -> dict:
    results = {}
    for ticker in tickers:
        t = get_technicals(ticker)
        if t is not None:
            results[ticker] = t
    return results
