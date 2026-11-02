from .indicators import add_indicators
from .ema_strategy import generate_signal

def evaluate(entry_df,trend_df,cfg):
    a=add_indicators(entry_df,cfg.fast_ema,cfg.slow_ema,cfg.rsi_period,cfg.atr_period,cfg.volume_period)
    h=add_indicators(trend_df,cfg.fast_ema,cfg.slow_ema,cfg.rsi_period,cfg.atr_period,cfg.volume_period)
    # Drop the still-forming candle on both timeframes.
    return a,h,generate_signal(a.iloc[:-1],h.iloc[:-1],cfg)
