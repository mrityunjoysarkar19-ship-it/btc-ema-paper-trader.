from dataclasses import dataclass
import math
@dataclass
class SizeResult:
    quantity:float; risk_cash:float; estimated_margin:float

def calculate_position_size(equity,available_margin,entry,stop,risk_fraction,fee_rate,
                            slippage_rate,contract_multiplier=1,max_leverage=2,
                            quantity_step=1,min_quantity=1):
    dist=abs(entry-stop)
    if min(equity,available_margin,entry,dist,contract_multiplier)<=0:raise ValueError("Inputs must be positive")
    unit_risk=dist*contract_multiplier+entry*contract_multiplier*2*(fee_rate+slippage_rate)
    risk_cash=equity*risk_fraction
    raw=min(risk_cash/unit_risk,available_margin*max_leverage/(entry*contract_multiplier))
    qty=math.floor(raw/quantity_step)*quantity_step
    if qty<min_quantity:raise ValueError("Size below exchange minimum")
    margin=qty*entry*contract_multiplier/max_leverage
    return SizeResult(qty,risk_cash,margin)
