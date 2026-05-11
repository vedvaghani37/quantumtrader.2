# ============================================================
# QUANTUM OPTIMIZATION MODULE
# ============================================================

import numpy as np
import pandas as pd
import yfinance as yf
import logging
from config import QAOA_MAX_ASSETS, PORTFOLIO_BUDGET, RISK_FACTOR, QAOA_MAXITER

logger = logging.getLogger(__name__)


def _extract_close(raw: pd.DataFrame, candidates: list) -> pd.DataFrame:
    """Handle both flat and MultiIndex columns from yfinance >= 0.2."""
    if isinstance(raw.columns, pd.MultiIndex):
        level0 = [c.lower() for c in raw.columns.get_level_values(0)]
        key    = "close" if "close" in level0 else None
        if key is None:
            raise KeyError("Cannot find 'Close' in MultiIndex columns")
        return raw.xs("Close" if "Close" in raw.columns.get_level_values(0) else "close",
                      axis=1, level=0)
    if "Close" in raw.columns:
        data = raw[["Close"]].copy()
        data.columns = candidates[:1]
        return data
    raise KeyError("Cannot find 'Close' column")


def run_quantum_optimization(candidates: list) -> list:
    if not candidates:
        return []
    candidates = candidates[:QAOA_MAX_ASSETS]
    logger.info(f"QAOA running on {len(candidates)} candidates: {candidates}")

    try:
        raw  = yf.download(candidates, period="6mo", interval="1d", progress=False, auto_adjust=True)
        data = _extract_close(raw, candidates).dropna(axis=1, how="all")
        available = [t for t in candidates if t in data.columns]
        if not available:
            return candidates[:PORTFOLIO_BUDGET]
        data    = data[available].dropna()
        if len(available) < 2:
            return available[:PORTFOLIO_BUDGET]
        returns = data.pct_change().dropna()
        mu      = returns.mean().values * 252
        sigma   = returns.cov().values  * 252
        budget  = min(PORTFOLIO_BUDGET, len(available))
    except Exception as e:
        logger.error(f"Data download failed: {e}")
        return candidates[:PORTFOLIO_BUDGET]

    try:
        from qiskit_finance.applications.optimization import PortfolioOptimization
        from qiskit_algorithms import QAOA
        from qiskit_algorithms.optimizers import COBYLA
        from qiskit_optimization.algorithms import MinimumEigenOptimizer
        from qiskit.primitives import StatevectorSampler

        problem = PortfolioOptimization(
            expected_returns=mu, covariances=sigma,
            risk_factor=RISK_FACTOR, budget=budget,
        )
        qaoa_mes       = QAOA(sampler=StatevectorSampler(),
                              optimizer=COBYLA(maxiter=QAOA_MAXITER), reps=2)
        result         = MinimumEigenOptimizer(qaoa_mes).solve(problem.to_quadratic_program())
        selected       = [available[i] for i, v in enumerate(result.x) if v == 1]
        logger.info(f"QAOA selected: {selected}")
        return selected
    except ImportError:
        logger.warning("Qiskit not installed — using classical Markowitz fallback.")
    except Exception as e:
        logger.error(f"QAOA failed ({e}) — using classical Markowitz fallback.")

    return _classical_markowitz(available, mu, sigma, budget)


def _classical_markowitz(tickers, mu, sigma, budget):
    variances   = np.diag(sigma)
    sharpe_like = mu / (np.sqrt(variances) + 1e-9)
    ranked      = sorted(range(len(tickers)), key=lambda i: sharpe_like[i], reverse=True)
    selected_idx = []
    for idx in ranked:
        if len(selected_idx) >= budget:
            break
        if all(
            abs(sigma[idx, s] / (np.sqrt(variances[idx]+1e-9) * np.sqrt(variances[s]+1e-9))) <= 0.85
            for s in selected_idx
        ):
            selected_idx.append(idx)
    selected = [tickers[i] for i in selected_idx]
    logger.info(f"Markowitz selected: {selected}")
    return selected
