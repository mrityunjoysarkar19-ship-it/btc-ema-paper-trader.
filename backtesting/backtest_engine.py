import pandas as pd
from strategy.indicators import add_indicators
from strategy.news_filter import blackout_reason


def run_backtest(df, htf=None, fast=9, slow=20, fee=.0005, slippage=.0005,
                 rr=2, variant="ema_rsi_volume_htf", atr_mult=1.5,
                 news_blackouts=None):
    """Close-confirmed, next-open backtest. News blocks new entries only."""
    d = add_indicators(df, fast, slow)
    h = add_indicators(htf, fast, slow) if htf is not None and not htf.empty else None
    blackouts = news_blackouts or []
    trades, equity = [], [1.0]
    cash, pos = 1.0, None

    for i in range(2, len(d)):
        row = d.iloc[i]
        prev, sig = d.iloc[i-2], d.iloc[i-1]

        if pos:
            sl_hit = row.low <= pos["sl"] if pos["side"] == "long" else row.high >= pos["sl"]
            tp_hit = row.high >= pos["tp"] if pos["side"] == "long" else row.low <= pos["tp"]
            if sl_hit or tp_hit:
                px = pos["sl"] if sl_hit else pos["tp"]
                direction = 1 if pos["side"] == "long" else -1
                gross = (px-pos["entry"])*direction/pos["entry"]
                ret = gross - 2*fee - 2*slippage
                cash *= (1+ret)
                trades.append({"side":pos["side"], "signal_time":pos["signal_time"],
                    "entry_time":pos["entry_time"], "exit_time":row.name,
                    "entry":pos["entry"], "exit":px, "stop":pos["sl"], "target":pos["tp"],
                    "gross_return":gross, "return":ret, "reason":"stop" if sl_hit else "target",
                    "news_blocked_entry":False})
                pos = None

        up = prev.ema_fast <= prev.ema_slow and sig.ema_fast > sig.ema_slow
        dn = prev.ema_fast >= prev.ema_slow and sig.ema_fast < sig.ema_slow
        # Entry is planned at this bar's open; skip it if that instant is in a blackout.
        blocked_event = blackout_reason(row.name, blackouts) if (up or dn) else None
        if pos is None and (up or dn) and not blocked_event:
            side = "long" if up else "short"
            ok = True
            if variant in ("ema_rsi", "ema_rsi_volume", "ema_rsi_volume_htf"):
                ok &= (50 < sig.rsi < 75) if side == "long" else (25 < sig.rsi < 50)
            if variant in ("ema_rsi_volume", "ema_rsi_volume_htf", "trend_pullback"):
                ok &= sig.volume > sig.volume_sma
            if variant == "ema_rsi_volume_htf" and h is not None:
                hs = h.loc[h.index <= sig.name]
                if len(hs):
                    last = hs.iloc[-1]
                    ok &= last.close > last.ema_slow if side == "long" else last.close < last.ema_slow
            if variant == "trend_pullback":
                if h is None:
                    ok = False
                else:
                    hs = h.loc[h.index <= sig.name]
                    if len(hs) < 2:
                        ok = False
                    else:
                        ht, hp = hs.iloc[-1], hs.iloc[-2]
                        if side == "long":
                            ok &= ht.close > ht.ema200 and ht.ema_slow > ht.ema200 and ht.ema_slow > hp.ema_slow
                            ok &= 50 < sig.rsi < 65
                        else:
                            ok &= ht.close < ht.ema200 and ht.ema_slow < ht.ema200 and ht.ema_slow < hp.ema_slow
                            ok &= 35 < sig.rsi < 50
            if ok and pd.notna(sig.atr) and sig.atr > 0:
                entry = float(row.open) * (1+slippage if side == "long" else 1-slippage)
                dist = float(sig.atr) * atr_mult
                pos = {"side":side, "entry":entry,
                       "sl":entry-dist if side == "long" else entry+dist,
                       "tp":entry+dist*rr if side == "long" else entry-dist*rr,
                       "signal_time":sig.name, "entry_time":row.name}

        marked = cash
        if pos:
            direction = 1 if pos["side"] == "long" else -1
            marked = cash * (1 + (float(row.close)-pos["entry"])*direction/pos["entry"] - fee - slippage)
        equity.append(marked)

    if pos:
        last = d.iloc[-1]
        px = float(last.close) * (1-slippage if pos["side"] == "long" else 1+slippage)
        direction = 1 if pos["side"] == "long" else -1
        gross = (px-pos["entry"])*direction/pos["entry"]
        ret = gross - 2*fee - 2*slippage
        cash *= (1+ret)
        trades.append({"side":pos["side"], "signal_time":pos["signal_time"],
            "entry_time":pos["entry_time"], "exit_time":last.name,
            "entry":pos["entry"], "exit":px, "stop":pos["sl"], "target":pos["tp"],
            "gross_return":gross, "return":ret, "reason":"end_of_test",
            "news_blocked_entry":False})
        equity[-1] = cash
    return {"trades":pd.DataFrame(trades), "equity":pd.Series(equity), "ending_equity":cash}
