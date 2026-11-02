from dataclasses import dataclass

@dataclass
class Signal:
    side:str; timestamp:str; entry:float; stop_loss:float; take_profit:float
    rr:float; confidence:int; reasons:list

def generate_signal(df,htf,cfg):
    if len(df)<max(cfg.slow_ema+3,cfg.atr_period+3) or len(htf)<max(cfg.slow_ema+3,cfg.atr_period+3):return None
    p,r=df.iloc[-2],df.iloc[-1]
    up=p.ema_fast<=p.ema_slow and r.ema_fast>r.ema_slow
    dn=p.ema_fast>=p.ema_slow and r.ema_fast<r.ema_slow
    if not(up or dn):return None
    side="long" if up else "short";score=40;why=[]
    aligned=(r.close>r.ema_fast>r.ema_slow) if side=="long" else (r.close<r.ema_fast<r.ema_slow)
    if aligned:score+=10;why.append("Price aligned with EMA stack")
    if cfg.use_rsi:
        ok=(50<r.rsi<75) if side=="long" else (25<r.rsi<50)
        if not ok:return None
        score+=15;why.append("RSI confirms")
    if cfg.use_volume:
        if not(r.volume>r.volume_sma):return None
        score+=10;why.append("Volume above average")
    if cfg.use_htf:
        h=htf.iloc[-1]
        ok=(h.close>h.ema_slow) if side=="long" else (h.close<h.ema_slow)
        if not ok:return None
        score+=15;why.append("Higher timeframe agrees")
    if r.ema_spread<.00015 or r.atr<=0 or r.atr/r.close<.0004:return None
    if abs(r.close-p.close)>cfg.max_candle_atr*r.atr:return None
    if r.volume>r.volume_sma*4:return None
    if score<cfg.min_confidence:return None
    entry=float(r.close);dist=float(r.atr)*cfg.atr_stop_multiplier
    sl=entry-dist if side=="long" else entry+dist
    tp=entry+dist*cfg.reward_risk if side=="long" else entry-dist*cfg.reward_risk
    return Signal(side,str(df.index[-1]),entry,sl,tp,cfg.reward_risk,min(score,100),why)
