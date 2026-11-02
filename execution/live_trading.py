class LiveTradingGate:
    PHRASE="I UNDERSTAND LIVE TRADING RISK"
    def __init__(self,settings):self.settings=settings
    def assert_enabled(self,typed):
        if self.settings.mode!="live" or not self.settings.live_enabled:raise PermissionError("Live trading disabled.")
        if typed!=self.PHRASE or self.settings.live_confirmation!=self.PHRASE:raise PermissionError("Explicit confirmation missing.")
        if not self.settings.api_key or not self.settings.api_secret:raise PermissionError("API credentials missing.")
