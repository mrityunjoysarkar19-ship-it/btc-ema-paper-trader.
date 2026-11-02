import pandas as pd
from strategy.indicators import add_indicators
def test_indicator_columns():
    s=pd.Series(range(100,400),dtype=float)
    d=pd.DataFrame({"open":s,"high":s+1,"low":s-1,"close":s,"volume":100.})
    x=add_indicators(d)
    assert {"ema_fast","ema_slow","rsi","atr","volume_sma","ema200"}<=set(x.columns)
