"""Conservative BTC EMA research backtester.

Signals are generated from completed candles and entered at the next candle open.
Returns are sized by fixed fractional risk with a configurable notional cap.
OHLC ambiguity is resolved stop-first. This is a research simulator, not an
exchange-exact derivatives P&L engine.
"""
from __future__ import annotations

import pandas as pd
from strategy.indicators import add_indicators
from strategy.news_filter import blackout_reason


def _latest_htf(htf: pd.DataFrame | None, timestamp):
    if htf is None or htf.empty:
        return None
    eligible = htf.loc[htf.index <= timestamp]
    return None if eligible.empty else eligible.iloc[-1]


def _signal(side: str, sig, prior, variant: str, htf_row):
    """Evaluate a signal using only the last fully closed lower/HTF candles."""
    if variant == "ema":
        return True

    if variant in ("ema_rsi", "ema_rsi_volume", "ema_rsi_volume_htf"):
        if pd.isna(sig.rsi):
            return False
        if side == "long" and not (50 < sig.rsi < 75):
            return False
        if side == "short" and not (25 < sig.rsi < 50):
            return False

    if variant in ("ema_rsi_volume", "ema_rsi_volume_htf"):
        if pd.isna(sig.volume_sma) or not (sig.volume > sig.volume_sma):
            return False

    if variant == "ema_rsi_volume_htf":
        if htf_row is None or pd.isna(htf_row.ema_slow):
            return False
        if side == "long" and not (htf_row.close > htf_row.ema_slow):
            return False
        if side == "short" and not (htf_row.close < htf_row.ema_slow):
            return False

    if variant == "trend_pullback":
        if htf_row is None or pd.isna(htf_row.get("ema200")):
            return False
        if pd.isna(sig.rsi) or pd.isna(sig.volume_sma):
            return False
        if not (sig.volume > sig.volume_sma):
            return False
        if side == "long":
            return (
                htf_row.close > htf_row.ema200
                and htf_row.ema_slow > htf_row.ema200
                and sig.ema_fast > sig.ema_slow
                and prior.low <= prior.ema_fast
                and sig.close > sig.ema_fast
                and 52 < sig.rsi < 68
            )
        return (
            htf_row.close < htf_row.ema200
            and htf_row.ema_slow < htf_row.ema200
            and sig.ema_fast < sig.ema_slow
            and prior.high >= prior.ema_fast
            and sig.close < sig.ema_fast
            and 32 < sig.rsi < 48
        )

    return True


def _exit_fill(raw_price: float, side: str, slippage: float) -> float:
    # Adverse exit slippage.
    return raw_price * (1 - slippage if side == "long" else 1 + slippage)


def _bar_exit(pos: dict, bar, slippage: float):
    """Return (raw exit price, reason) or None. Conservative stop-first rule."""
    side = pos["side"]
    if side == "long":
        stop_hit = float(bar.low) <= pos["sl"]
        target_hit = float(bar.high) >= pos["tp"]
        if stop_hit:
            raw = min(float(bar.open), pos["sl"]) if float(bar.open) < pos["sl"] else pos["sl"]
            return raw, "stop"
        if target_hit:
            raw = max(float(bar.open), pos["tp"]) if float(bar.open) > pos["tp"] else pos["tp"]
            return raw, "target"
    else:
        stop_hit = float(bar.high) >= pos["sl"]
        target_hit = float(bar.low) <= pos["tp"]
        if stop_hit:
            raw = max(float(bar.open), pos["sl"]) if float(bar.open) > pos["sl"] else pos["sl"]
            return raw, "stop"
        if target_hit:
            raw = min(float(bar.open), pos["tp"]) if float(bar.open) < pos["tp"] else pos["tp"]
            return raw, "target"
    return None


def run_backtest(
    df, htf=None, fast=9, slow=20, fee=0.0005, slippage=0.0005,
    rr=2.0, variant="trend_pullback", atr_mult=1.5,
    news_blackouts=None, risk_per_trade=0.005, max_leverage=1.0,
):
    """Run a single-position, fixed-risk backtest.

    fee/slippage are decimal fractions per side (0.0005 = 0.05%).
    risk_per_trade is the equity fraction risked at the stop, before costs.
    max_leverage caps position notional as a multiple of current equity.
    """
    if df is None or len(df) < max(50, slow + 20):
        raise ValueError("Insufficient candles for a reliable indicator warm-up")
    if not (0 < risk_per_trade <= 0.02):
        raise ValueError("risk_per_trade must be between 0 and 2%")
    if max_leverage <= 0 or rr <= 0 or atr_mult <= 0:
        raise ValueError("max_leverage, reward/risk and ATR multiplier must be positive")

    d = add_indicators(df.copy(), fast, slow)
    h = add_indicators(htf.copy(), fast, slow) if htf is not None and not htf.empty else None
    blackouts = news_blackouts or []

    cash = 1.0
    equity_curve = []
    trades = []
    pos = None

    for i in range(2, len(d)):
        bar = d.iloc[i]
        prior = d.iloc[i - 2]
        sig = d.iloc[i - 1]
        exited_this_bar = False

        # Manage existing position first.
        if pos is not None:
            hit = _bar_exit(pos, bar, slippage)
            if hit:
                raw_exit, reason = hit
                exit_px = _exit_fill(raw_exit, pos["side"], slippage)
                direction = 1 if pos["side"] == "long" else -1
                price_return = direction * (exit_px - pos["entry"]) / pos["entry"]
                net_return = pos["leverage"] * price_return - 2 * fee * pos["leverage"]
                pnl = cash * net_return
                cash += pnl
                trades.append({
                    "side": pos["side"], "signal_time": pos["signal_time"],
                    "entry_time": pos["entry_time"], "exit_time": bar.name,
                    "entry": pos["entry"], "exit": exit_px, "stop": pos["sl"],
                    "target": pos["tp"], "leverage": pos["leverage"],
                    "risk_fraction": risk_per_trade, "gross_return_on_equity": pos["leverage"] * price_return,
                    "return": net_return, "pnl_on_equity": net_return,
                    "reason": reason, "news_blocked_entry": False,
                })
                pos = None
                exited_this_bar = True

        # Signal uses previous completed candle; entry is at current bar open.
        if pos is None and not exited_this_bar:
            if variant == "trend_pullback":
                # Pullback continuation trigger (not an EMA crossover trigger).
                up = (
                    sig.ema_fast > sig.ema_slow
                    and prior.low <= prior.ema_fast
                    and sig.close > sig.ema_fast
                )
                down = (
                    sig.ema_fast < sig.ema_slow
                    and prior.high >= prior.ema_fast
                    and sig.close < sig.ema_fast
                )
            else:
                up = prior.ema_fast <= prior.ema_slow and sig.ema_fast > sig.ema_slow
                down = prior.ema_fast >= prior.ema_slow and sig.ema_fast < sig.ema_slow

            side = "long" if up else ("short" if down else None)
            if side:
                blocked = blackout_reason(bar.name, blackouts)
                hrow = _latest_htf(h, sig.name)
                allowed = (not blocked) and _signal(side, sig, prior, variant, hrow)

                if allowed and pd.notna(sig.atr) and float(sig.atr) > 0:
                    raw_entry = float(bar.open)
                    entry = raw_entry * (1 + slippage if side == "long" else 1 - slippage)
                    stop_distance = float(sig.atr) * atr_mult
                    stop_fraction = stop_distance / entry
                    leverage = min(risk_per_trade / stop_fraction, max_leverage)
                    if leverage > 0:
                        pos = {
                            "side": side, "entry": entry,
                            "sl": entry - stop_distance if side == "long" else entry + stop_distance,
                            "tp": entry + stop_distance * rr if side == "long" else entry - stop_distance * rr,
                            "leverage": leverage, "signal_time": sig.name,
                            "entry_time": bar.name,
                        }
                        # Entry-bar SL/TP is checked too. Unknown intrabar order => stop first.
                        hit = _bar_exit(pos, bar, slippage)
                        if hit:
                            raw_exit, reason = hit
                            exit_px = _exit_fill(raw_exit, side, slippage)
                            direction = 1 if side == "long" else -1
                            price_return = direction * (exit_px - entry) / entry
                            net_return = leverage * price_return - 2 * fee * leverage
                            cash *= (1 + net_return)
                            trades.append({
                                "side": side, "signal_time": sig.name, "entry_time": bar.name,
                                "exit_time": bar.name, "entry": entry, "exit": exit_px,
                                "stop": pos["sl"], "target": pos["tp"], "leverage": leverage,
                                "risk_fraction": risk_per_trade,
                                "gross_return_on_equity": leverage * price_return,
                                "return": net_return, "pnl_on_equity": net_return,
                                "reason": reason, "news_blocked_entry": False,
                            })
                            pos = None
                            exited_this_bar = True

        # Mark open position once per candle; never subtract fees/slippage repeatedly.
        marked_equity = cash
        if pos is not None:
            direction = 1 if pos["side"] == "long" else -1
            unrealized = pos["leverage"] * direction * (float(bar.close) - pos["entry"]) / pos["entry"]
            estimated_costs = 2 * fee * pos["leverage"]
            marked_equity = cash * (1 + unrealized - estimated_costs)
        equity_curve.append(marked_equity)

    # Liquidate any remaining position at the final close, including adverse slippage.
    if pos is not None:
        last = d.iloc[-1]
        exit_px = _exit_fill(float(last.close), pos["side"], slippage)
        direction = 1 if pos["side"] == "long" else -1
        price_return = direction * (exit_px - pos["entry"]) / pos["entry"]
        net_return = pos["leverage"] * price_return - 2 * fee * pos["leverage"]
        cash *= (1 + net_return)
        trades.append({
            "side": pos["side"], "signal_time": pos["signal_time"],
            "entry_time": pos["entry_time"], "exit_time": last.name,
            "entry": pos["entry"], "exit": exit_px, "stop": pos["sl"],
            "target": pos["tp"], "leverage": pos["leverage"],
            "risk_fraction": risk_per_trade,
            "gross_return_on_equity": pos["leverage"] * price_return,
            "return": net_return, "pnl_on_equity": net_return,
            "reason": "end_of_test", "news_blocked_entry": False,
        })
        if equity_curve:
            equity_curve[-1] = cash

    return {
        "trades": pd.DataFrame(trades),
        "equity": pd.Series(equity_curve, index=d.index[2:2 + len(equity_curve)], dtype=float),
        "ending_equity": cash,
    }
