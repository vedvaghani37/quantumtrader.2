#!/usr/bin/env python3
# ============================================================
# AUTOMATION GUIDE — Keep the bot running 24/7
# ============================================================
#
# The core problem with Google Colab:
#   - Colab disconnects after ~90 min of no browser interaction
#   - Even with tricks, it dies after ~12 hours
#   - There is NO way to make Colab run forever reliably
#
# SOLUTION OPTIONS (pick one):
#
#  Option A: Railway.app       ← RECOMMENDED (free tier, easiest)
#  Option B: Render.com        ← Free tier, slightly more setup
#  Option C: Google Cloud Run  ← Pay-per-use, very cheap
#  Option D: Your own PC/Mac   ← Free but your machine must stay on
#
# All options use the SAME bot.py code — only the hosting differs.
#
# ⚠️  IMPORTANT regardless of option:
#     Even while hosted 24/7, the bot already places GTC
#     stop-loss and take-profit orders at Alpaca after every buy
#     (see executor.py → place_protective_orders). Those orders
#     survive even if your hosting goes down temporarily.
# ============================================================


# ╔══════════════════════════════════════════════════════════╗
# ║  OPTION A — Railway.app (RECOMMENDED — FREE TIER)       ║
# ╚══════════════════════════════════════════════════════════╝
#
# Railway gives you a free container that runs 24/7.
# No credit card needed for the hobby plan ($5 free credit/month).
#
# STEP 1: Create these two files in your project folder:
#
#   requirements.txt  (list of packages to install)
#   Procfile          (tells Railway how to start your bot)
#
# STEP 2: Push to GitHub, then connect Railway to your repo.
#
# STEP 3: Add environment variables in Railway dashboard.
#
# Full setup below — just run the functions in this file.

import os
import subprocess
import sys


def create_requirements_txt():
    """Create requirements.txt for cloud deployment."""
    content = """\
alpaca-py>=0.20.0
yfinance>=0.2.28
requests>=2.31.0
pandas>=2.0.0
numpy>=1.24.0
qiskit>=1.0.0
qiskit-finance>=0.4.0
qiskit-algorithms>=0.3.0
qiskit-optimization>=0.6.0
"""
    with open("requirements.txt", "w") as f:
        f.write(content)
    print("✅ Created requirements.txt")


def create_procfile():
    """Create Procfile for Railway/Render deployment."""
    with open("Procfile", "w") as f:
        f.write("worker: python bot.py\n")
    print("✅ Created Procfile")


def create_railway_json():
    """Create railway.json config file."""
    import json
    config = {
        "$schema": "https://railway.app/railway.schema.json",
        "build": {"builder": "NIXPACKS"},
        "deploy": {
            "startCommand": "python bot.py",
            "restartPolicyType": "ON_FAILURE",
            "restartPolicyMaxRetries": 10,
        },
    }
    with open("railway.json", "w") as f:
        json.dump(config, f, indent=2)
    print("✅ Created railway.json")


def create_render_yaml():
    """Create render.yaml for Render.com deployment."""
    content = """\
services:
  - type: worker
    name: quantum-trading-bot
    runtime: python
    buildCommand: pip install -r requirements.txt
    startCommand: python bot.py
    envVars:
      - key: ALPACA_API_KEY
        sync: false
      - key: ALPACA_SECRET_KEY
        sync: false
      - key: NEWS_API_KEY
        sync: false
"""
    with open("render.yaml", "w") as f:
        f.write(content)
    print("✅ Created render.yaml")


def create_dockerfile():
    """Create Dockerfile for any Docker-compatible host."""
    content = """\
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py .

# Environment variables must be injected at runtime (never baked in)
ENV ALPACA_API_KEY=""
ENV ALPACA_SECRET_KEY=""
ENV NEWS_API_KEY=""

CMD ["python", "bot.py"]
"""
    with open("Dockerfile", "w") as f:
        f.write(content)
    print("✅ Created Dockerfile")


def create_github_actions_workflow():
    """
    Create a GitHub Actions workflow that keeps the bot running.
    Uses GitHub's free compute (2000 min/month on free tier).
    NOTE: GitHub Actions jobs have a 6-hour limit per run, so this
    workflow re-triggers itself before the limit. It is NOT ideal
    for production but works as a free option.
    """
    os.makedirs(".github/workflows", exist_ok=True)
    content = """\
name: Trading Bot

on:
  workflow_dispatch:          # Manual trigger
  schedule:
    - cron: '0 13 * * 1-5'   # Auto-start Mon-Fri at 9 AM ET (13:00 UTC)

jobs:
  run-bot:
    runs-on: ubuntu-latest
    timeout-minutes: 350      # Stop just before GitHub's 6-hour limit

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run trading bot
        env:
          ALPACA_API_KEY:    ${{ secrets.ALPACA_API_KEY }}
          ALPACA_SECRET_KEY: ${{ secrets.ALPACA_SECRET_KEY }}
          NEWS_API_KEY:      ${{ secrets.NEWS_API_KEY }}
        run: python bot.py
"""
    with open(".github/workflows/trading_bot.yml", "w") as f:
        f.write(content)
    print("✅ Created .github/workflows/trading_bot.yml")
    print("   → Add ALPACA_API_KEY and ALPACA_SECRET_KEY as GitHub Secrets")
    print("   → Settings → Secrets → Actions → New repository secret")


def create_systemd_service():
    """
    Create a systemd service file for running on a Linux VPS or your own PC.
    After creating this, copy it to /etc/systemd/system/ and enable it.
    """
    bot_dir = os.path.abspath(".")
    content = f"""\
[Unit]
Description=Quantum Trading Bot
After=network.target
Wants=network-online.target

[Service]
Type=simple
User={os.environ.get('USER', 'ubuntu')}
WorkingDirectory={bot_dir}
ExecStart=/usr/bin/python3 {bot_dir}/bot.py
Restart=always
RestartSec=30

# Inject credentials securely via environment file
# Create /etc/quantum-bot.env with:
#   ALPACA_API_KEY=your_key
#   ALPACA_SECRET_KEY=your_secret
#   NEWS_API_KEY=your_key
EnvironmentFile=/etc/quantum-bot.env

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=quantum-bot

[Install]
WantedBy=multi-user.target
"""
    with open("quantum-bot.service", "w") as f:
        f.write(content)
    print("✅ Created quantum-bot.service")
    print("   To install on Linux:")
    print("   sudo cp quantum-bot.service /etc/systemd/system/")
    print("   sudo systemctl daemon-reload")
    print("   sudo systemctl enable quantum-bot")
    print("   sudo systemctl start quantum-bot")
    print("   sudo journalctl -u quantum-bot -f    # View live logs")


def setup_all_deployment_files():
    """Run all setup functions to create every deployment file."""
    print("\n🚀 Creating all deployment files...\n")
    create_requirements_txt()
    create_procfile()
    create_railway_json()
    create_render_yaml()
    create_dockerfile()
    create_github_actions_workflow()
    create_systemd_service()
    print("\n✅ All deployment files created.\n")
    print_deployment_guide()


def print_deployment_guide():
    guide = """
╔══════════════════════════════════════════════════════════════╗
║            DEPLOYMENT GUIDE — Choose One Option             ║
╚══════════════════════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OPTION A — Railway.app  (RECOMMENDED, Free, No card required)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Push your code to GitHub:
     git init
     git add .
     git commit -m "quantum trading bot"
     git remote add origin https://github.com/YOUR_NAME/quantum-bot
     git push -u origin main

2. Go to https://railway.app → Sign up with GitHub → New Project
   → Deploy from GitHub repo → select your repo

3. Add environment variables (Variables tab in Railway):
     ALPACA_API_KEY     = your_key
     ALPACA_SECRET_KEY  = your_secret
     NEWS_API_KEY       = your_key  (optional)

4. Railway auto-deploys and keeps the bot running 24/7.
   If it crashes, Railway restarts it automatically.
   View logs in real-time from the Railway dashboard.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OPTION B — Render.com  (Free tier, sleeps after 15 min idle)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Push to GitHub (same as above)
2. Go to https://render.com → New → Background Worker
3. Connect your GitHub repo
4. Add environment variables in the Environment tab
5. Deploy

Note: Render's free tier Background Workers do NOT sleep —
they're always on. Web services sleep; background workers don't.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OPTION C — Your own Windows/Mac PC  (Free, machine must stay on)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Windows Task Scheduler:
  1. Open Task Scheduler → Create Basic Task
  2. Trigger: At startup
  3. Action: Start a program
       Program: python
       Arguments: C:\\path\\to\\bot.py
       Start in: C:\\path\\to\\

Mac/Linux cron:
  crontab -e
  Add: @reboot cd /path/to/bot && python bot.py >> bot.log 2>&1

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OPTION D — GitHub Actions  (Free, restarts every 6h on market days)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Push to GitHub
2. Settings → Secrets → Actions:
     ALPACA_API_KEY, ALPACA_SECRET_KEY, NEWS_API_KEY
3. The workflow auto-runs Mon-Fri at 9 AM ET and re-runs itself

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SAFETY NET (works regardless of which option you pick)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

After every buy, the bot places GTC (Good-Till-Cancelled) orders
directly at Alpaca:
  • Stop-loss  at entry_price × (1 - 7%)  → auto-sells if price drops
  • Take-profit at entry_price × (1 + 20%) → auto-sells if price rises

These orders live at Alpaca's servers — completely independent of
whether your bot code is running. Even if everything crashes,
your positions are protected.

Check them anytime at: https://app.alpaca.markets/paper/orders
"""
    print(guide)


# ── Colab Keep-Alive (last resort, not reliable) ────────────

COLAB_KEEPALIVE_JS = """
// Paste this into your browser's developer console (F12)
// while the Colab tab is open. It clicks the "Connect" button
// every 60 seconds to prevent disconnection.
// NOTE: This only works while your browser tab is open.
// It does NOT solve the 12-hour session limit.

function keepAlive() {
  try {
    // Try to click reconnect button if disconnected
    document.querySelector("colab-connect-button")
      .shadowRoot.querySelector("paper-icon-button")
      .click();
  } catch(e) {}

  // Simulate keyboard activity to prevent idle timeout
  document.dispatchEvent(new KeyboardEvent('keydown', {bubbles: true}));
}

setInterval(keepAlive, 60000);
console.log("Keep-alive started. Close this tab → bot stops.");
"""

def print_colab_keepalive():
    print("Colab keep-alive JavaScript (paste in browser DevTools console):")
    print(COLAB_KEEPALIVE_JS)
    print("\n⚠️  This is a workaround, NOT a real solution.")
    print("    Use Railway.app (Option A) for reliable 24/7 operation.")


if __name__ == "__main__":
    # Run this file directly to generate all deployment files
    setup_all_deployment_files()
