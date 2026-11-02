class PaperBroker:
    def __init__(self,db,fee=.0005,slippage=.0005):self.db,self.fee,self.slippage=db,fee,slippage
    def open(self,sig,qty,sig_id):
        px=sig.entry*(1+self.slippage if sig.side=="long" else 1-self.slippage)
        t={"signal_id":sig_id,"mode":"paper","side":sig.side,"quantity":qty,"entry":px,
           "stop_loss":sig.stop_loss,"take_profit":sig.take_profit,"fees":px*qty*self.fee,"status":"open"}
        self.db.save_trade(t);return t
    def close_if_hit(self,t,candle):
        if t["side"]=="long": sl=candle["low"]<=t["stop_loss"];tp=candle["high"]>=t["take_profit"]
        else: sl=candle["high"]>=t["stop_loss"];tp=candle["low"]<=t["take_profit"]
        if not(sl or tp):return None
        px=t["stop_loss"] if sl else t["take_profit"]
        direction=1 if t["side"]=="long" else -1
        fee=px*t["quantity"]*self.fee
        return {"exit":px,"pnl":(px-t["entry"])*t["quantity"]*direction-t["fees"]-fee,
                "fees":t["fees"]+fee,"status":"closed","exit_reason":"stop_loss" if sl else "take_profit"}
