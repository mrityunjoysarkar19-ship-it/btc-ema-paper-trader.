import numpy as np
import pandas as pd

def add_indicators(df,fast=9,slow=20,rsi_period=14,atr_period=14,volume_period=20):
    d=df.copy()
    d["ema_fast"]=d.close.ewm(span=fast,adjust=False).mean()
    d["ema_slow"]=d.close.ewm(span=slow,adjust=False).mean()
    delta=d.close.diff(); gain=delta.clip(lower=0); loss=-delta.clip(upper=0)
    ag=gain.ewm(alpha=1/rsi_period,adjust=False,min_periods=rsi_period).mean()
    al=loss.ewm(alpha=1/rsi_period,adjust=False,min_periods=rsi_period).mean()
    d["rsi"]=100-100/(1+ag/al.replace(0,np.nan))
    prev=d.close.shift()
    tr=pd.concat([d.high-d.low,(d.high-prev).abs(),(d.low-prev).abs()],axis=1).max(axis=1)
    d["atr"]=tr.ewm(alpha=1/atr_period,adjust=False,min_periods=atr_period).mean()
    d["volume_sma"]=d.volume.rolling(volume_period).mean()
    d["ema_spread"]=(d.ema_fast-d.ema_slow).abs()/d.close
    d["ema200"]=d.close.ewm(span=200,adjust=False).mean()
    return d

def normalize_candles(rows):
    d=pd.DataFrame(rows)
    if d.empty:return d
    d["time"]=pd.to_datetime(d.time,unit="s",utc=True);d=d.set_index("time")
    for c in ["open","high","low","close","volume"]:d[c]=pd.to_numeric(d[c],errors="coerce")
    return d[["open","high","low","close","volume"]].dropna().sort_index()
