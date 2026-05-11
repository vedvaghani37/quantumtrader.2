# ============================================================
# MAIN BOT — Real-Time Market Scanner & Trader
# ============================================================
# KEY IMPROVEMENTS IN THIS VERSION:
#
# 1. PARTIAL SELL LOGIC — the bot now decides HOW MUCH to sell:
#    - Strong SELL signal (news + tech agree) → sell 100%
#    - Weak SELL signal (only one fires)      → sell 50%
#    - RSI overbought                         → trim 33%
#    - High volatility spike + in profit      → trim 25%
#    - Stop-loss / take-profit / trailing     → sell 100%
#
# 2. PROTECTIVE ORDERS — after every buy, GTC stop-loss and
#    take-profit limit orders are placed at Alpaca. These
#    execute even when the bot is completely offline.
#
# 3. AUTOMATION — see automation.py for how to keep this
#    running 24/7 without Colab.
# ============================================================

import os
import time
import logging
import threading

from config import SCAN_INTERVAL_SEC, NEWS_REFRESH_SEC, LOG_FILE
from universe import get_extended_universe
from signals import batch_signals, get_full_signal
from technicals import batch_technicals, get_technicals
from quantum_optimizer import run_quantum_optimization
from executor import AlpacaExecutor
from risk import RiskManager

logging.basicConfig(
    level    = logging.INFO,
    format   = "%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt  = "%Y-%m-%d %H:%M:%S",
    handlers = [
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def _require_env(var: str) -> str:
    val = os.environ.get(var, "")
    if not val:
        raise EnvironmentError(
            f"\n{'='*60}\n  Missing: {var}\n"
            f"  Set it with: os.environ['{var}'] = 'your_value'\n{'='*60}"
        )
    return val


class QuantumTradingBot:
    def __init__(self):
        logger.info("=" * 60)
        logger.info("  QUANTUM TRADING BOT — Starting Up")
        logger.info("=" * 60)

        _require_env("ALPACA_API_KEY")
        _require_env("ALPACA_SECRET_KEY")

        self.executor = AlpacaExecutor()
        equity        = self.executor.get_equity()
        self.risk_mgr = RiskManager(initial_equity=equity)
        logger.info(f"Starting equity: ${equity:,.2f}")

        logger.info("Loading stock universe...")
        self.universe = get_extended_universe(max_size=1500)
        logger.info(f"Universe: {len(self.universe)} tickers")

        self._stop_event    = threading.Event()
        self.last_news_time = 0.0
        self.cycle          = 0

    # ── Public API ───────────────────────────────────────────

    def run(self):
        """Run until interrupted or stop() is called."""
        logger.info("Bot started. Ctrl+C or bot.stop() to exit.\n")
        try:
            while not self._stop_event.is_set():
                if not self.executor.is_market_open():
                    logger.info("Market closed — sleeping 5 min...")
                    time.sleep(300)
                    continue
                self._main_cycle()
        except KeyboardInterrupt:
            logger.info("Interrupted by user.")
        finally:
            self._shutdown()

    def stop(self):
        self._stop_event.set()

    # ── Main Cycle ───────────────────────────────────────────

    def _main_cycle(self):
        self.cycle += 1
        logger.info(f"\n{'─'*48}  CYCLE {self.cycle}  {'─'*48}")

        equity = self.executor.get_equity()

        if self.risk_mgr.check_drawdown(equity):
            logger.critical("Max drawdown hit — liquidating everything.")
            self.executor.sell_all("MAX_DRAWDOWN")
            time.sleep(3600)
            return

        # ── 1. Smart position monitoring (partial sells) ──────
        self._monitor_positions_smart()

        # ── 2. Periodic news re-check on holdings ─────────────
        now = time.time()
        if now - self.last_news_time >= NEWS_REFRESH_SEC:
            self._news_check_holdings()
            self.last_news_time = now

        # ── 3. Scan universe for new buys ─────────────────────
        self._scan_and_buy(equity)

        # ── 4. Print summary ──────────────────────────────────
        logger.info(self.executor.get_portfolio_summary()["summary"])
        logger.info(f"Sleeping {SCAN_INTERVAL_SEC}s...\n")
        time.sleep(SCAN_INTERVAL_SEC)

    # ── Smart Position Monitor (with partial sells) ───────────

    def _monitor_positions_smart(self):
        """
        For each open position, fetch current technicals and evaluate
        the full sell decision including partial exits.
        This is where the bot actually decides HOW MUCH to sell.
        """
        positions = self.executor.get_open_positions()
        if not positions:
            return

        logger.info(f"Monitoring {len(positions)} open position(s)...")

        for ticker, pos in positions.items():
            try:
                # Get fresh technicals (price, RSI, volatility)
                tech = get_technicals(ticker)
                if tech:
                    pos.update_price(tech.current_price)
                    pos.volatility = tech.volatility
                    rsi        = tech.rsi
                    tech_sig   = tech.tech_signal
                    current_vol = tech.volatility
                else:
                    rsi         = 50.0
                    tech_sig    = "NEUTRAL"
                    current_vol = pos.volatility

                # Get fresh news signal for held positions
                news_sig   = get_full_signal(ticker)
                news_signal = news_sig.signal
                news_score  = news_sig.composite_score

                # Ask the risk manager for a sell decision
                decision = self.risk_mgr.evaluate_sell(
                    position    = pos,
                    news_signal = news_signal,
                    news_score  = news_score,
                    tech_signal = tech_sig,
                    rsi         = rsi,
                    current_vol = current_vol,
                )

                if decision.should_sell:
                    pct_str = f"{decision.sell_pct:.0%}"
                    logger.info(
                        f"  → {ticker}: SELL {pct_str} ({decision.sell_qty} shares) | "
                        f"{decision.reason}"
                    )
                    self.executor.sell(
                        ticker,
                        qty    = decision.sell_qty,
                        reason = decision.reason,
                    )

                    # After a partial sell, update protective orders
                    remaining_qty = pos.qty - decision.sell_qty
                    if remaining_qty > 0 and tech:
                        self.executor.place_protective_orders(
                            ticker, remaining_qty, tech.current_price
                        )
                else:
                    logger.info(f"  → {ticker}: {decision.reason}")

            except Exception as e:
                logger.error(f"Monitor error for {ticker}: {e}")

    # ── News Re-Check on Holdings ────────────────────────────

    def _news_check_holdings(self):
        """
        Lightweight re-check — only news/earnings/analyst, no technicals.
        Fires every NEWS_REFRESH_SEC (5 min). Strong SELL = full exit.
        """
        positions = self.executor.get_open_positions()
        if not positions:
            return
        logger.info(f"News re-check on {len(positions)} holding(s)...")
        for ticker in list(positions.keys()):
            try:
                sig = get_full_signal(ticker)
                if sig.signal == "SELL" and sig.composite_score <= -0.25:
                    logger.warning(
                        f"  📰 Strong news SELL on {ticker} "
                        f"(score={sig.composite_score:+.2f}) — full exit."
                    )
                    self.executor.sell(ticker, reason=f"NEWS_SELL {sig.composite_score:.2f}")
            except Exception as e:
                logger.error(f"News re-check error for {ticker}: {e}")

    # ── Universe Scan & Buy Logic ────────────────────────────

    def _scan_and_buy(self, equity: float):
        cash = self.executor.get_cash()
        held = set(self.executor.get_open_positions().keys())

        if cash < 100:
            logger.info("Cash < $100 — skipping new buys.")
            return

        # Step 1: Fast technical scan
        logger.info(f"Technical scan: {len(self.universe)} tickers...")
        tech_results = batch_technicals(self.universe)

        tech_buys  = [t for t, r in tech_results.items() if r.tech_signal == "BUY"  and t not in held]
        tech_sells = [t for t, r in tech_results.items() if r.tech_signal == "SELL" and t in held]

        logger.info(f"Technical: {len(tech_buys)} buy candidates, {len(tech_sells)} sell signals")

        for ticker in tech_sells:
            logger.info(f"📊 Technical SELL on held {ticker}.")
            self.executor.sell(ticker, reason="TECHNICAL_SELL")

        if not tech_buys:
            logger.info("No technical buy candidates this cycle.")
            return

        # Step 2: Deep signal scan on top 50 (most oversold first)
        top_candidates = sorted(tech_buys, key=lambda t: tech_results[t].rsi)[:50]
        logger.info(f"Deep signal scan: {len(top_candidates)} candidates...")
        signal_results = batch_signals(top_candidates, delay_sec=0.2)

        buy_candidates = [t for t, s in signal_results.items() if s.signal == "BUY"]
        signal_sells   = [t for t, s in signal_results.items() if s.signal == "SELL" and t in held]

        for ticker in signal_sells:
            sig = signal_results[ticker]
            logger.warning(f"📰 Signal SELL on held {ticker} (score={sig.composite_score:+.2f}).")
            self.executor.sell(ticker, reason="SIGNAL_SELL")

        if not buy_candidates:
            logger.info("No confirmed buy candidates after signal filtering.")
            return

        # Step 3: QAOA optimization
        logger.info(f"QAOA on {len(buy_candidates)} candidates...")
        selected = run_quantum_optimization(buy_candidates)
        logger.info(f"Selected: {selected}")

        # Step 4: Execute buys
        for ticker in selected:
            if ticker in held:
                continue
            tech  = tech_results.get(ticker)
            price = tech.current_price if tech else 0.0
            vol   = tech.volatility    if tech else 0.20
            if price <= 0:
                continue
            qty = self.risk_mgr.position_size(ticker, price, equity, vol)
            sig = signal_results.get(ticker)
            reason = f"QUANTUM_SELECT score={sig.composite_score:+.2f}" if sig else "QUANTUM_SELECT"
            self.executor.buy(ticker, qty, reason=reason)

    # ── Shutdown ─────────────────────────────────────────────

    def _shutdown(self):
        logger.info("Shutting down — cancelling pending orders...")
        self.executor.cancel_all_orders()
        logger.info("Final " + self.executor.get_portfolio_summary()["summary"])
        logger.info("Bot stopped.")


if __name__ == "__main__":
    bot = QuantumTradingBot()
    bot.run()
