# ============================================================
# COLAB LAUNCHER — Run cell by cell
# ============================================================


# ╔══════════════════════════════════════════════════════════╗
# ║  CELL 1 — Install dependencies                          ║
# ╚══════════════════════════════════════════════════════════╝

# !pip install alpaca-py yfinance requests pandas numpy \
#              qiskit qiskit-finance qiskit-algorithms qiskit-optimization


# ╔══════════════════════════════════════════════════════════╗
# ║  CELL 2 — Set credentials                               ║
# ╚══════════════════════════════════════════════════════════╝

import os
os.environ["ALPACA_API_KEY"]    = "YOUR_NEW_ALPACA_KEY"    # ← paste your NEW key
os.environ["ALPACA_SECRET_KEY"] = "YOUR_NEW_SECRET_KEY"    # ← paste your NEW secret
os.environ["NEWS_API_KEY"]      = ""                        # optional, free at newsapi.org
print("✅ Credentials set (session-only)")


# ╔══════════════════════════════════════════════════════════╗
# ║  CELL 3 — Upload bot files                              ║
# ╚══════════════════════════════════════════════════════════╝

# Upload all .py files via Colab sidebar → Files → Upload:
#   config.py, universe.py, signals.py, technicals.py,
#   quantum_optimizer.py, risk.py, executor.py, bot.py, automation.py


# ╔══════════════════════════════════════════════════════════╗
# ║  CELL 4 — Verify Alpaca connection                      ║
# ╚══════════════════════════════════════════════════════════╝

from alpaca.trading.client import TradingClient
client  = TradingClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"], paper=True)
account = client.get_account()
print(f"✅ Alpaca PAPER connected")
print(f"   Cash:      ${float(account.cash):,.2f}")
print(f"   Portfolio: ${float(account.portfolio_value):,.2f}")


# ╔══════════════════════════════════════════════════════════╗
# ║  CELL 5 — Quick signal test                             ║
# ╚══════════════════════════════════════════════════════════╝

from signals import get_full_signal
for ticker in ["AAPL", "NVDA", "MSFT", "TSLA", "META"]:
    sig = get_full_signal(ticker)
    print(f"  {ticker:6s}  {sig.signal:7s}  composite={sig.composite_score:+.2f}")


# ╔══════════════════════════════════════════════════════════╗
# ║  CELL 6 — Quick technicals test                         ║
# ╚══════════════════════════════════════════════════════════╝

from technicals import get_technicals
for ticker in ["AAPL", "NVDA", "MSFT"]:
    t = get_technicals(ticker)
    if t:
        print(f"  {ticker:6s}  RSI={t.rsi:.1f}  Mom={t.momentum_pct:+.1f}%  Signal={t.tech_signal}")


# ╔══════════════════════════════════════════════════════════╗
# ║  CELL 7 — Create deployment files (for 24/7 hosting)    ║
# ╚══════════════════════════════════════════════════════════╝

# Run this to generate Railway/Render/Docker/GitHub Actions files.
# Then download them from the Colab file panel and follow the guide.

from automation import setup_all_deployment_files
setup_all_deployment_files()


# ╔══════════════════════════════════════════════════════════╗
# ║  CELL 8 — START THE BOT (Colab only, not 24/7)          ║
# ╚══════════════════════════════════════════════════════════╝
#
# ⚠️  Colab will disconnect after ~90 min of browser idle.
#     For 24/7 operation, use Railway.app (see Cell 7).
#     Even if Colab disconnects, GTC stop-loss and take-profit
#     orders placed at Alpaca will still protect your positions.

from bot import QuantumTradingBot
bot = QuantumTradingBot()
bot.run()


# ╔══════════════════════════════════════════════════════════╗
# ║  CELL 9 — (Optional) View current open positions        ║
# ╚══════════════════════════════════════════════════════════╝

# from executor import AlpacaExecutor
# ex = AlpacaExecutor()
# print(ex.get_portfolio_summary()["summary"])


# ╔══════════════════════════════════════════════════════════╗
# ║  CELL 10 — (Optional) Manual sell a position            ║
# ╚══════════════════════════════════════════════════════════╝

# from executor import AlpacaExecutor
# ex = AlpacaExecutor()
# ex.sell("AAPL", reason="manual sell")     # Sell full AAPL position
# ex.sell_all(reason="manual liquidation")  # Sell everything


# ╔══════════════════════════════════════════════════════════╗
# ║  CELL 11 — Check what GTC orders are active at Alpaca   ║
# ╚══════════════════════════════════════════════════════════╝

# These are your stop-loss and take-profit orders that survive
# bot downtime. Run this to see what's currently active.

# from alpaca.trading.client import TradingClient
# from alpaca.trading.requests import GetOrdersRequest
# from alpaca.trading.enums import QueryOrderStatus
# import os
#
# c = TradingClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"], paper=True)
# orders = c.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN))
# print(f"\n{'─'*60}")
# print(f"  Active GTC orders at Alpaca ({len(orders)} total):")
# for o in orders:
#     print(f"  {o.symbol:<6}  {str(o.side):<12}  qty={o.qty}  "
#           f"type={str(o.order_type):<8}  "
#           f"stop=${getattr(o,'stop_price','N/A')}  limit=${getattr(o,'limit_price','N/A')}")
# print(f"{'─'*60}\n")
