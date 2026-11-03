"""Performance statistics for the research backtester."""
import numpy as np


def summarize(result):
    trades = result["trades"]
    equity = result["equity"].astype(float)
    ending = float(result["ending_equity"])

    if equity.empty:
        max_dd = 0.0
    else:
        # Include initial account equity (1.0) as the first high-water mark.
        path = np.concatenate(([1.0], equity.to_numpy(dtype=float)))
        peaks = np.maximum.accumulate(path)
        max_dd = float(np.min(path / np.maximum(peaks, 1e-12) - 1.0))

    if trades.empty:
        return {
            "total_trades": 0, "win_rate": 0.0, "profit_factor": 0.0,
            "net_return": ending - 1.0, "max_drawdown": max_dd,
            "winning_trades": 0, "losing_trades": 0,
            "average_trade": 0.0, "expectancy": 0.0,
        }

    returns = trades["return"].astype(float)
    wins = returns[returns > 0]
    losses = returns[returns < 0]
    gross_profit = float(wins.sum())
    gross_loss = float(abs(losses.sum()))
    pf = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)

    return {
        "total_trades": int(len(trades)),
        "win_rate": float((returns > 0).mean()),
        "profit_factor": float(pf),
        "net_return": ending - 1.0,
        "max_drawdown": max_dd,
        "winning_trades": int((returns > 0).sum()),
        "losing_trades": int((returns < 0).sum()),
        "average_trade": float(returns.mean()),
        "expectancy": float(returns.mean()),
    }
