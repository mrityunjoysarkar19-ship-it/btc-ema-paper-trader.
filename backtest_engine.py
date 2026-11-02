import pandas as pd
from strategy.indicators import add_indicators

def run_backtest(df,htf=None,fast=9,slow=20,fee=.0005,slippage=.0005,rr=2,variant="ema_rsi_volume_htf"):
    d=add_indicators(df,fast,slow);trades=[];equity=[1.0];cash=1.0;pos=None
    for i in range(2,len(d)):
        row=d.iloc[i]          # current bar is execution/position-management bar
        sig_prev=d.iloc[i-2]    # previous completed bar before signal candle
        sig=d.iloc[i-1]         # signal candle is fully closed at this point
        if pos:
            sl=row.low<=pos["sl"] if pos["side"]=="long" else row.high>=pos["sl"]
            tp=row.high>=pos["tp"] if pos["side"]=="long" else row.low<=pos["tp"]
            if sl or tp:
                px=pos["sl"] if sl else pos["tp"]  # conservative stop-first
                direction=1 if pos["side"]=="long" else -1
                ret=(px-pos["entry"])*direction/pos["entry"]-2*fee-2*slippage
                cash*=1+ret
                trades.append({"side":pos["side"],"entry":pos["entry"],"exit":px,"return":ret,
                               "reason":"stop" if sl else "target"})
                pos=None
        up=sig_prev.ema_fast<=sig_prev.ema_slow and sig.ema_fast>sig.ema_slow
        dn=sig_prev.ema_fast>=sig_prev.ema_slow and sig.ema_fast<sig.ema_slow
        if pos is None and (up or dn):
            side="long" if up else "short";ok=True
            if variant in ("ema_rsi","ema_rsi_volume","ema_rsi_volume_htf"):
                ok &= (50<sig.rsi<75) if side=="long" else (25<sig.rsi<50)
            if variant in ("ema_rsi_volume","ema_rsi_volume_htf"):ok &= sig.volume>sig.volume_sma
            if variant=="ema_rsi_volume_htf" and htf is not None:
                hs=htf.loc[htf.index<=sig.name]
                if len(hs):ok &= hs.iloc[-1].close>hs.iloc[-1].ema_slow if side=="long" else hs.iloc[-1].close<hs.iloc[-1].ema_slow
            if ok and pd.notna(sig.atr):
                entry=float(row.open)*(1+slippage if side=="long" else 1-slippage)
                dist=float(sig.atr)*1.5
                pos={"side":side,"entry":entry,"sl":entry-dist if side=="long" else entry+dist,
                     "tp":entry+dist*rr if side=="long" else entry-dist*rr}
        equity.append(cash)
    return {"trades":pd.DataFrame(trades),"equity":pd.Series(equity),"ending_equity":cash}
