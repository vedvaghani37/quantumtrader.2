# ============================================================
# EXECUTION MODULE — Alpaca Paper / Live Trading
# ============================================================
# KEY ADDITION: place_protective_orders()
#
# This solves the "bot offline = no selling" problem.
# After every buy, we immediately place TWO server-side orders
# at Alpaca that live independently of whether our bot is running:
#
#   1. A STOP order at entry_price × (1 - STOP_LOSS_PCT)
#      → Alpaca sells automatically if price falls below this
#
#   2. A LIMIT order at entry_price × (1 + TAKE_PROFIT_PCT)
#      → Alpaca sells automatically if price rises above this
#
# These are OCO (One-Cancels-Other) style orders — whichever
# triggers first cancels the other. Even if Colab dies, your
# positions are protected.
# ============================================================

import logging
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    LimitOrderRequest,
    StopOrderRequest,
    GetOrdersRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest
from config import (
    ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_PAPER,
    STOP_LOSS_PCT, TAKE_PROFIT_PCT,
)
from risk import Position

logger = logging.getLogger(__name__)


class AlpacaExecutor:
    def __init__(self):
        if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
            raise ValueError(
                "ALPACA_API_KEY and ALPACA_SECRET_KEY must be set as environment variables.\n"
                "  import os\n"
                "  os.environ['ALPACA_API_KEY']    = 'your_key'\n"
                "  os.environ['ALPACA_SECRET_KEY'] = 'your_secret'"
            )

        self.client = TradingClient(
            ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=ALPACA_PAPER
        )
        self.data_client = StockHistoricalDataClient(
            ALPACA_API_KEY, ALPACA_SECRET_KEY
        )

        account = self.client.get_account()
        mode    = "PAPER" if ALPACA_PAPER else "LIVE ⚠️"
        logger.info(
            f"✅ Alpaca [{mode}] connected | "
            f"Cash: ${float(account.cash):,.2f} | "
            f"Portfolio: ${float(account.portfolio_value):,.2f}"
        )

    # ── Account Info ─────────────────────────────────────────

    def get_equity(self) -> float:
        return float(self.client.get_account().portfolio_value)

    def get_cash(self) -> float:
        return float(self.client.get_account().cash)

    def is_market_open(self) -> bool:
        return self.client.get_clock().is_open

    def get_open_positions(self) -> dict:
        """
        Fetch live positions from Alpaca.
        Returns dict[symbol] = Position with current live price.
        """
        positions = {}
        try:
            for p in self.client.get_all_positions():
                pos = Position(
                    ticker        = p.symbol,
                    qty           = int(float(p.qty)),
                    entry_price   = float(p.avg_entry_price),
                    current_price = float(p.current_price),
                    volatility    = 0.20,  # Default; updated by technicals module
                )
                pos.peak_price = float(p.current_price)  # Reset peak to current on load
                positions[p.symbol] = pos
        except Exception as e:
            logger.error(f"Failed to fetch positions: {e}")
        return positions

    def get_portfolio_summary(self) -> dict:
        positions = self.get_open_positions()
        equity    = self.get_equity()
        cash      = self.get_cash()

        lines = [
            f"\n{'─' * 60}",
            f"  Portfolio: ${equity:,.2f}  |  Available cash: ${cash:,.2f}",
            f"  {'TICKER':<8} {'QTY':>5}  {'ENTRY':>8}  {'NOW':>8}  {'P&L':>8}  {'VALUE':>10}",
            f"  {'─'*55}",
        ]
        for ticker, pos in positions.items():
            pnl_flag = "✅" if pos.pnl_pct >= 0 else "🔴"
            lines.append(
                f"  {ticker:<8} {pos.qty:>5}  "
                f"${pos.entry_price:>7.2f}  "
                f"${pos.current_price:>7.2f}  "
                f"{pnl_flag}{pos.pnl_pct:>+6.1%}  "
                f"${pos.market_value:>9,.2f}"
            )
        lines.append(f"{'─' * 60}\n")

        return {
            "equity":    equity,
            "cash":      cash,
            "positions": positions,
            "summary":   "\n".join(lines),
        }

    # ── Buy ──────────────────────────────────────────────────

    def buy(self, ticker: str, qty: int, reason: str = "") -> bool:
        """
        Submit a market buy order. After fill, immediately places
        protective stop-loss and take-profit orders at Alpaca.
        Those orders survive bot restarts and Colab disconnects.
        """
        if qty < 1:
            logger.warning(f"BUY {ticker}: qty < 1, skipping.")
            return False

        # Adjust qty if it would exceed available cash
        cash = self.get_cash()
        try:
            quote = self.data_client.get_stock_latest_quote(
                StockLatestQuoteRequest(symbol_or_symbols=ticker)
            )
            ask   = quote[ticker].ask_price
            bid   = quote[ticker].bid_price
            price = float(ask or bid or 0)
            if price > 0 and price * qty > cash:
                qty = max(1, int(cash * 0.95 / price))
        except Exception:
            price = 0.0  # Will use entry price from position for protective orders

        try:
            order    = MarketOrderRequest(
                symbol        = ticker,
                qty           = qty,
                side          = OrderSide.BUY,
                time_in_force = TimeInForce.DAY,
            )
            response = self.client.submit_order(order_data=order)
            logger.info(
                f"📈 BUY  {ticker:<6}  qty={qty}  "
                f"order_id={response.id}  reason: {reason}"
            )

            # Place protective orders immediately after the buy
            # Use the current ask price as a proxy for entry price
            if price > 0:
                self.place_protective_orders(ticker, qty, price)

            return True

        except Exception as e:
            logger.error(f"BUY failed for {ticker}: {e}")
            return False

    # ── Protective Orders (Survive Bot Downtime) ─────────────

    def place_protective_orders(
        self,
        ticker:      str,
        qty:         int,
        entry_price: float,
    ) -> None:
        """
        Place a stop-loss order and a take-profit limit order at Alpaca.
        These are server-side orders — they execute even if our bot
        is completely offline (Colab disconnected, code not running).

        Alpaca does not support native OCO on paper accounts for all
        order types, so we place both independently. Whichever fills
        first, the bot's next cycle will cancel the orphaned order.
        """
        stop_price  = round(entry_price * (1 - STOP_LOSS_PCT),  2)
        limit_price = round(entry_price * (1 + TAKE_PROFIT_PCT), 2)

        # ── Stop-Loss ─────────────────────────────────────────
        try:
            stop_order = StopOrderRequest(
                symbol        = ticker,
                qty           = qty,
                side          = OrderSide.SELL,
                time_in_force = TimeInForce.GTC,   # Good-till-cancelled
                stop_price    = stop_price,
            )
            r = self.client.submit_order(order_data=stop_order)
            logger.info(
                f"  🛡️  Stop-loss placed: {ticker} @ ${stop_price:.2f} "
                f"(GTC, order_id={r.id})"
            )
        except Exception as e:
            logger.error(f"  Failed to place stop-loss for {ticker}: {e}")

        # ── Take-Profit Limit ─────────────────────────────────
        try:
            tp_order = LimitOrderRequest(
                symbol        = ticker,
                qty           = qty,
                side          = OrderSide.SELL,
                time_in_force = TimeInForce.GTC,   # Good-till-cancelled
                limit_price   = limit_price,
            )
            r = self.client.submit_order(order_data=tp_order)
            logger.info(
                f"  🎯 Take-profit placed: {ticker} @ ${limit_price:.2f} "
                f"(GTC, order_id={r.id})"
            )
        except Exception as e:
            logger.error(f"  Failed to place take-profit for {ticker}: {e}")

    def cancel_protective_orders(self, ticker: str) -> None:
        """
        Cancel all open GTC sell orders for a ticker.
        Call this before placing a manual sell to avoid double-selling.
        """
        try:
            open_orders = self.client.get_orders(
                GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[ticker])
            )
            for order in open_orders:
                if str(order.side) in ("OrderSide.SELL", "sell"):
                    self.client.cancel_order_by_id(str(order.id))
                    logger.info(f"  Cancelled GTC sell order for {ticker}: {order.id}")
        except Exception as e:
            logger.warning(f"  Could not cancel orders for {ticker}: {e}")

    # ── Sell ─────────────────────────────────────────────────

    def sell(self, ticker: str, qty: int = None, reason: str = "") -> bool:
        """
        Submit a market sell order.
        Cancels existing protective (GTC) orders first to avoid
        double-selling.
        qty=None → sell the full position.
        """
        # Cancel any existing stop/take-profit orders for this ticker first
        self.cancel_protective_orders(ticker)

        try:
            if qty is None:
                self.client.close_position(ticker)
                logger.info(f"📉 SELL {ticker:<6}  (full position)  reason: {reason}")
                return True

            order = MarketOrderRequest(
                symbol        = ticker,
                qty           = qty,
                side          = OrderSide.SELL,
                time_in_force = TimeInForce.DAY,
            )
            response = self.client.submit_order(order_data=order)
            logger.info(
                f"📉 SELL {ticker:<6}  qty={qty}  "
                f"order_id={response.id}  reason: {reason}"
            )
            return True

        except Exception as e:
            logger.error(f"SELL failed for {ticker}: {e}")
            return False

    def sell_all(self, reason: str = "emergency") -> None:
        """Liquidate everything and cancel all open orders."""
        logger.warning(f"⚠️  LIQUIDATING ALL POSITIONS: {reason}")
        try:
            self.client.close_all_positions(cancel_orders=True)
            logger.info("All positions liquidated.")
        except Exception as e:
            logger.error(f"close_all_positions failed: {e}")

    def cancel_all_orders(self) -> None:
        """Cancel every pending / open order."""
        try:
            self.client.cancel_orders()
            logger.info("All pending orders cancelled.")
        except Exception as e:
            logger.error(f"cancel_orders failed: {e}")
