import json, logging
from urllib.parse import urlencode
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from .authentication import auth_headers

log = logging.getLogger(__name__)

class DeltaAPIError(RuntimeError): pass

class DeltaClient:
    def __init__(self, base_url, api_key="", api_secret="", timeout=(3, 15)):
        self.base_url, self.api_key, self.api_secret = base_url.rstrip("/"), api_key, api_secret
        self.timeout = timeout
        self.session = requests.Session()
        retry = Retry(total=2, backoff_factor=.4, status_forcelist=[429,500,502,503,504],
                      allowed_methods=["GET"], respect_retry_after_header=True)
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def request(self, method, path, params=None, payload=None, private=False):
        params = params or {}
        query = urlencode(sorted(params.items()), doseq=True)
        query_part = f"?{query}" if query else ""
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False) if payload is not None else ""
        headers = {"User-Agent":"btc-ema-trading-bot/0.1","Accept":"application/json"}
        if private:
            if not self.api_key or not self.api_secret:
                raise DeltaAPIError("Private API call requested without credentials.")
            headers.update(auth_headers(self.api_key,self.api_secret,method,path,query_part,body))
        if payload is not None: headers["Content-Type"]="application/json"
        try:
            r = self.session.request(method,self.base_url+path+query_part,
                data=body or None,headers=headers,timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
        except requests.RequestException as e:
            log.error("Delta transport error: %s",type(e).__name__)
            raise DeltaAPIError(f"Delta transport error: {type(e).__name__}") from e
        except ValueError as e:
            raise DeltaAPIError("Delta returned non-JSON response.") from e
        if isinstance(data,dict) and data.get("success") is False:
            err=data.get("error",{})
            code=err.get("code","api_error") if isinstance(err,dict) else "api_error"
            raise DeltaAPIError(f"Delta rejected request: {code}")
        return data.get("result",data) if isinstance(data,dict) else data

    def products(self): return self.request("GET","/v2/products",{"page_size":200})
    def ticker(self,symbol): return self.request("GET",f"/v2/tickers/{symbol}")
    def candles(self,symbol,resolution,start,end):
        return self.request("GET","/v2/history/candles",{"resolution":resolution,"symbol":symbol,"start":int(start),"end":int(end)})
    def wallet_balances(self): return self.request("GET","/v2/wallet/balances",private=True)
    def positions(self,product_id=None):
        return self.request("GET","/v2/positions",{"product_id":product_id} if product_id else {},private=True)
    def open_orders(self,product_id=None):
        p={"states":"open,pending"}
        if product_id: p["product_id"]=product_id
        return self.request("GET","/v2/orders",p,private=True)
    def create_order(self,payload): return self.request("POST","/v2/orders",payload=payload,private=True)
    def create_bracket(self,payload): return self.request("POST","/v2/orders/bracket",payload=payload,private=True)
    def order(self,oid): return self.request("GET",f"/v2/orders/{oid}",private=True)
    def cancel_order(self,oid): return self.request("DELETE",f"/v2/orders/{oid}",private=True)
