# ============================================================
# QUANTUM TRADING BOT — Configuration
# ============================================================
import os

# ── Alpaca Credentials ───────────────────────────────────────
ALPACA_API_KEY    = os.environ.get("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY", "")
ALPACA_PAPER      = True   # Set False ONLY for live money

# ── News API ─────────────────────────────────────────────────
NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "")

# ── Quantum Optimization ─────────────────────────────────────
QAOA_MAX_ASSETS  = 20
PORTFOLIO_BUDGET = 5
RISK_FACTOR      = 0.5
QAOA_MAXITER     = 150

# ── Cadence ──────────────────────────────────────────────────
SCAN_INTERVAL_SEC  = 300
NEWS_REFRESH_SEC   = 300

# ── Signal Thresholds ────────────────────────────────────────
BUY_SENTIMENT_MIN       = 0.15
SELL_SENTIMENT_MAX      = -0.10
RSI_OVERSOLD            = 35
RSI_OVERBOUGHT          = 70
MOMENTUM_WINDOW_DAYS    = 10
VOLUME_SPIKE_MULTIPLIER = 1.5
ANALYST_WEIGHT          = 0.3

# ── Risk Management ──────────────────────────────────────────
MAX_POSITION_PCT  = 0.08   # Max 8% of portfolio per stock
STOP_LOSS_PCT     = 0.07   # Hard stop at -7%
TAKE_PROFIT_PCT   = 0.20   # Take profit at +20%
TRAIL_PCT         = 0.05   # Trailing stop: lock in gains, trail by 5%
MAX_DRAWDOWN_PCT  = 0.15   # Halt bot if portfolio drops 15% from peak

# ── Partial Sell Thresholds ──────────────────────────────────
# Sell in tranches rather than all at once based on conditions
PARTIAL_SELL_STRONG_SELL_PCT = 1.00   # 100% — dump all on strong SELL signal
PARTIAL_SELL_WEAK_SIGNAL_PCT = 0.50   # 50% — trim on mild bearish signal
PARTIAL_SELL_OVERBOUGHT_PCT  = 0.33   # 33% — trim when RSI overbought
PARTIAL_SELL_HIGH_VOL_PCT    = 0.25   # 25% — trim when volatility spikes

# ── Logging ──────────────────────────────────────────────────
LOG_FILE = "trading_bot.log"
