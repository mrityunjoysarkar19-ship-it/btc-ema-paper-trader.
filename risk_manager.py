from dataclasses import dataclass
@dataclass
class RiskState:
    daily_pnl:float=0; day_start_equity:float=0; trades_today:int=0
    consecutive_losses:int=0; open_positions:int=0
class RiskManager:
    def __init__(self,cfg):self.cfg=cfg
    def validate(self,s):
        if s.day_start_equity<=0:return False,"Daily starting equity unavailable"
        if s.daily_pnl<=-s.day_start_equity*self.cfg.max_daily_loss:return False,"Daily loss limit reached"
        if s.trades_today>=self.cfg.max_daily_trades:return False,"Daily trade limit reached"
        if s.consecutive_losses>=self.cfg.max_consecutive_losses:return False,"Consecutive loss limit reached"
        if s.open_positions>=self.cfg.max_open_positions:return False,"Maximum open positions reached"
        return True,"Risk checks passed"
