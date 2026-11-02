from config import RiskConfig
from risk.risk_manager import RiskManager,RiskState
from risk.position_sizing import calculate_position_size
def test_daily_loss_lock():
    ok,msg=RiskManager(RiskConfig()).validate(RiskState(daily_pnl=-300,day_start_equity=10000))
    assert not ok and "Daily loss" in msg
def test_size_bounded_by_margin():
    x=calculate_position_size(10000,5000,50000,49000,.01,.0005,.0005,contract_multiplier=.001,max_leverage=2)
    assert x.quantity>=1 and x.estimated_margin<=5000
