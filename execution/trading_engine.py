from .live_trading import LiveTradingGate
class TradingEngine:
    def __init__(self,settings,client,db,risk,paper):
        self.settings,self.client,self.db,self.risk,self.paper=settings,client,db,risk,paper
    def reconcile(self,product_id):
        if self.settings.mode=="live":
            positions=self.client.positions(product_id);orders=self.client.open_orders(product_id)
            self.db.set_state("exchange_reconcile",{"positions":positions,"orders":orders})
            return positions,orders
        return [],[]
    def execute_signal(self,sig,qty,sig_id,risk_state,confirmation=""):
        ok,reason=self.risk.validate(risk_state)
        if not ok:raise RuntimeError(reason)
        if self.settings.mode=="paper":return self.paper.open(sig,qty,sig_id)
        LiveTradingGate(self.settings).assert_enabled(confirmation)
        raise NotImplementedError("Live order submission intentionally locked pending India-account integration tests.")
