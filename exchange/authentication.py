import hashlib, hmac, time

def sign_request(secret, method, timestamp, path, query_string="", body=""):
    message = f"{method.upper()}{timestamp}{path}{query_string}{body}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()

def auth_headers(api_key, api_secret, method, path, query_string="", body=""):
    ts = str(int(time.time()))
    return {"api-key": api_key, "timestamp": ts,
            "signature": sign_request(api_secret, method, ts, path, query_string, body),
            "User-Agent": "btc-ema-trading-bot/0.1", "Content-Type": "application/json",
            "Accept": "application/json"}
