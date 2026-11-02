import requests
class TelegramNotifier:
    def __init__(self,token="",chat_id=""):self.token,self.chat_id=token,chat_id
    def send(self,message):
        if not self.token or not self.chat_id:return False
        r=requests.post(f"https://api.telegram.org/bot{self.token}/sendMessage",
            json={"chat_id":self.chat_id,"text":message},timeout=10);r.raise_for_status();return True
