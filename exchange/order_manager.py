import hashlib
from decimal import Decimal, ROUND_DOWN

class OrderManager:
    def __init__(self,client,product): self.client,self.product=client,product
    def normalize_size(self,quantity):
        # Delta order size is an integer contract count. contract_value is the
        # notional multiplier, NOT the order-size increment.
        minimum=int(self.product.get("minimum_order_size") or 1)
        q=int(Decimal(str(quantity)).to_integral_value(rounding=ROUND_DOWN))
        if q<minimum: raise ValueError(f"Quantity below minimum {minimum}")
        return q
    @staticmethod
    def client_id(key): return hashlib.sha256(key.encode()).hexdigest()[:24]
    def market_entry(self,side,quantity,signal_key):
        return self.client.create_order({"product_id":int(self.product["id"]),
            "size":self.normalize_size(quantity),"side":side,"order_type":"market_order",
            "client_order_id":self.client_id(signal_key)})
    def bracket(self,stop_loss,take_profit):
        return self.client.create_bracket({"product_id":int(self.product["id"]),
            "stop_loss_order":{"order_type":"market_order","stop_price":str(stop_loss)},
            "take_profit_order":{"order_type":"market_order","stop_price":str(take_profit)},
            "bracket_stop_trigger_method":"mark_price"})
