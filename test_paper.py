from execution.paper_trading import PaperBroker
class DB:
    def save_trade(self,t):self.trade=t
def test_stop_first_when_both_hit():
    b=PaperBroker(DB());t={"side":"long","entry":100,"quantity":1,"stop_loss":95,"take_profit":110,"fees":0}
    out=b.close_if_hit(t,{"low":94,"high":111})
    assert out["exit"]==95 and out["exit_reason"]=="stop_loss"
