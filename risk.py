# ============================================================
# RISK MANAGEMENT MODULE
# ============================================================
# Handles:
#   - Volatility-adjusted position sizing
#   - PARTIAL sells based on market conditions (new)
#   - Trailing stop logic (new)
#   - Hard stop-loss / take-profit
#   - Portfolio drawdown kill-switch
#
# PARTIAL SELL LOGIC (how much to sell):
#   The bot no longer always sells 100%. It decides how much
#   to sell based on the strength of the sell signal:
#
#   Signal strength         | Action
#   ─────────────────────── | ──────────────────────────────
#   Strong SELL (news+tech) | Sell 100% — exit immediately
#   Weak/borderline SELL    | Sell 50%  — reduce exposure
#   RSI overbought only     | Sell 33%  — trim the position
#   Volatility spike only   | Sell 25%  — defensive trim
#   Stop-loss triggered     | Sell 100% — hard exit always
#   Take-profit triggered   | Sell 100% — lock in full gain
#   Trailing stop triggered | Sell 100% — protect gains
# ============================================================

import logging
import math
from dataclasses import dataclass, field
from typing import Optional
from config import (
    MAX_POSITION_PCT, STOP_LOSS_PCT, TAKE_PROFIT_PCT,
    MAX_DRAWDOWN_PCT, TRAIL_PCT,
    PARTIAL_SELL_STRONG_SELL_PCT, PARTIAL_SELL_WEAK_SIGNAL_PCT,
    PARTIAL_SELL_OVERBOUGHT_PCT, PARTIAL_SELL_HIGH_VOL_PCT,
)

logger = logging.getLogger(__name__)


@dataclass
class Position:
    ticker:        str
    qty:           int
    entry_price:   float
    current_price: float = 0.0
    peak_price:    float = 0.0    # Highest price seen since entry (for trailing stop)
    volatility:    float = 0.20   # Last-known annualized vol

    def __post_init__(self):
        if self.peak_price == 0.0:
            self.peak_price = self.current_price or self.entry_price

    def update_price(self, new_price: float):
        self.current_price = new_price
        if new_price > self.peak_price:
            self.peak_price = new_price

    @property
    def pnl_pct(self) -> float:
        if self.entry_price <= 0:
            return 0.0
        return (self.current_price - self.entry_price) / self.entry_price

    @property
    def drawdown_from_peak(self) -> float:
        """How far the price has fallen from the position's peak."""
        if self.peak_price <= 0:
            return 0.0
        return (self.peak_price - self.current_price) / self.peak_price

    @property
    def market_value(self) -> float:
        return self.qty * self.current_price

    @property
    def cost_basis(self) -> float:
        return self.qty * self.entry_price


@dataclass
class SellDecision:
    """
    Result of evaluating whether and how much of a position to sell.
    """
    should_sell:  bool  = False
    sell_qty:     int   = 0        # Number of shares to sell (0 = hold)
    sell_pct:     float = 0.0      # Fraction of position to sell
    reason:       str   = "HOLD"
    exit_type:    str   = "NONE"   # STOP_LOSS | TAKE_PROFIT | TRAIL | SIGNAL | TRIM


class RiskManager:
    def __init__(self, initial_equity: float):
        self.initial_equity = initial_equity
        self.peak_equity    = initial_equity
        self.trading_halted = False

    # ── Drawdown Kill-Switch ──────────────────────────────────

    def check_drawdown(self, current_equity: float) -> bool:
        self.peak_equity = max(self.peak_equity, current_equity)
        if self.peak_equity <= 0:
            return self.trading_halted
        drawdown = (self.peak_equity - current_equity) / self.peak_equity
        if drawdown >= MAX_DRAWDOWN_PCT:
            logger.critical(
                f"⛔ MAX DRAWDOWN {drawdown:.1%} reached "
                f"(peak=${self.peak_equity:,.2f}, now=${current_equity:,.2f}). "
                "Halting all trading."
            )
            self.trading_halted = True
        return self.trading_halted

    # ── Buy Sizing ───────────────────────────────────────────

    def position_size(
        self,
        ticker: str,
        current_price: float,
        portfolio_equity: float,
        volatility: float = 0.20,
    ) -> int:
        if current_price <= 0 or portfolio_equity <= 0:
            return 0
        base_dollars   = portfolio_equity * MAX_POSITION_PCT
        vol_scalar     = 0.20 / max(volatility, 0.10)
        target_dollars = min(base_dollars * vol_scalar, base_dollars)
        qty = math.floor(target_dollars / current_price)
        if qty < 1:
            return 0
        logger.info(
            f"{ticker}: buy sizing → {qty} shares @ ${current_price:.2f} "
            f"= ${qty * current_price:,.2f} "
            f"({qty * current_price / portfolio_equity:.1%} of portfolio)"
        )
        return qty

    # ── Sell Decision Engine ─────────────────────────────────

    def evaluate_sell(
        self,
        position:      Position,
        news_signal:   str   = "NEUTRAL",   # "BUY" | "SELL" | "NEUTRAL"
        news_score:    float = 0.0,
        tech_signal:   str   = "NEUTRAL",
        rsi:           float = 50.0,
        current_vol:   float = None,        # Current volatility for this ticker
    ) -> SellDecision:
        """
        Evaluate how much of a position to sell based on multiple conditions.

        Priority order (highest to lowest):
          1. Hard stop-loss        → sell 100%
          2. Trailing stop         → sell 100%
          3. Take-profit           → sell 100%
          4. Strong SELL signal    → sell 100%
          5. Weak SELL signal      → sell 50%
          6. RSI overbought        → sell 33% (trim)
          7. Volatility spike      → sell 25% (defensive trim)
          8. Otherwise             → hold
        """
        vol = current_vol if current_vol is not None else position.volatility

        # ── 1. Hard Stop-Loss ─────────────────────────────────
        if position.pnl_pct <= -STOP_LOSS_PCT:
            return SellDecision(
                should_sell = True,
                sell_qty    = position.qty,
                sell_pct    = 1.0,
                reason      = f"STOP_LOSS: P&L={position.pnl_pct:.1%} ≤ -{STOP_LOSS_PCT:.0%}",
                exit_type   = "STOP_LOSS",
            )

        # ── 2. Trailing Stop ──────────────────────────────────
        # Only activates once the position is in profit (peak > entry)
        if position.peak_price > position.entry_price:
            if position.drawdown_from_peak >= TRAIL_PCT:
                return SellDecision(
                    should_sell = True,
                    sell_qty    = position.qty,
                    sell_pct    = 1.0,
                    reason      = (
                        f"TRAILING_STOP: drew down {position.drawdown_from_peak:.1%} "
                        f"from peak ${position.peak_price:.2f}"
                    ),
                    exit_type   = "TRAIL",
                )

        # ── 3. Take-Profit ────────────────────────────────────
        if position.pnl_pct >= TAKE_PROFIT_PCT:
            return SellDecision(
                should_sell = True,
                sell_qty    = position.qty,
                sell_pct    = 1.0,
                reason      = f"TAKE_PROFIT: P&L={position.pnl_pct:.1%} ≥ +{TAKE_PROFIT_PCT:.0%}",
                exit_type   = "TAKE_PROFIT",
            )

        # ── 4. Strong SELL Signal (news AND technicals agree) ─
        news_is_sell = news_signal == "SELL" and news_score <= -0.20
        tech_is_sell = tech_signal == "SELL"
        if news_is_sell and tech_is_sell:
            qty = position.qty  # 100%
            return SellDecision(
                should_sell = True,
                sell_qty    = qty,
                sell_pct    = 1.0,
                reason      = f"STRONG_SELL: news={news_score:.2f} + tech=SELL",
                exit_type   = "SIGNAL",
            )

        # ── 5. Weak SELL Signal (only one signal fires) ───────
        if news_is_sell or tech_is_sell:
            qty = max(1, math.floor(position.qty * PARTIAL_SELL_WEAK_SIGNAL_PCT))
            return SellDecision(
                should_sell = True,
                sell_qty    = qty,
                sell_pct    = PARTIAL_SELL_WEAK_SIGNAL_PCT,
                reason      = (
                    f"WEAK_SELL 50%: "
                    + ("news_sell " if news_is_sell else "")
                    + ("tech_sell" if tech_is_sell else "")
                ),
                exit_type   = "SIGNAL",
            )

        # ── 6. RSI Overbought — trim 33% ─────────────────────
        if rsi > 75:   # Slightly tighter than config RSI_OVERBOUGHT for partial sells
            qty = max(1, math.floor(position.qty * PARTIAL_SELL_OVERBOUGHT_PCT))
            return SellDecision(
                should_sell = True,
                sell_qty    = qty,
                sell_pct    = PARTIAL_SELL_OVERBOUGHT_PCT,
                reason      = f"RSI_OVERBOUGHT 33%: RSI={rsi:.1f}",
                exit_type   = "TRIM",
            )

        # ── 7. Volatility Spike — defensive trim 25% ─────────
        if vol > 0.60 and position.pnl_pct > 0:   # High vol + we're in profit = trim
            qty = max(1, math.floor(position.qty * PARTIAL_SELL_HIGH_VOL_PCT))
            return SellDecision(
                should_sell = True,
                sell_qty    = qty,
                sell_pct    = PARTIAL_SELL_HIGH_VOL_PCT,
                reason      = f"VOL_SPIKE 25%: vol={vol:.0%}",
                exit_type   = "TRIM",
            )

        # ── 8. Hold ───────────────────────────────────────────
        return SellDecision(
            should_sell = False,
            sell_qty    = 0,
            sell_pct    = 0.0,
            reason      = (
                f"HOLD | P&L={position.pnl_pct:+.1%} | "
                f"RSI={rsi:.0f} | news={news_signal} | tech={tech_signal}"
            ),
            exit_type   = "NONE",
        )

    def check_position_exits(self, positions: dict) -> list:
        """
        Simple hard-exit check (stop-loss / take-profit only).
        Used during the fast position-monitor loop that runs without
        fetching fresh signals. Returns list of (ticker, reason).
        """
        to_sell = []
        for ticker, pos in positions.items():
            if pos.pnl_pct <= -STOP_LOSS_PCT:
                logger.warning(f"🛑 STOP LOSS: {ticker} P&L={pos.pnl_pct:.1%}")
                to_sell.append((ticker, "STOP_LOSS"))
            elif pos.peak_price > pos.entry_price and pos.drawdown_from_peak >= TRAIL_PCT:
                logger.info(f"📉 TRAILING STOP: {ticker} drew {pos.drawdown_from_peak:.1%} from peak")
                to_sell.append((ticker, "TRAILING_STOP"))
            elif pos.pnl_pct >= TAKE_PROFIT_PCT:
                logger.info(f"✅ TAKE PROFIT: {ticker} P&L={pos.pnl_pct:.1%}")
                to_sell.append((ticker, "TAKE_PROFIT"))
        return to_sell
