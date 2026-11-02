import os
from dataclasses import dataclass
from dotenv import load_dotenv
load_dotenv()

@dataclass(frozen=True)
class Settings:
    base_url: str = os.getenv("DELTA_BASE_URL", "https://api.india.delta.exchange").rstrip("/")
    api_key: str = os.getenv("DELTA_API_KEY", "")
    api_secret: str = os.getenv("DELTA_API_SECRET", "")
    product_symbol: str = os.getenv("DELTA_PRODUCT_SYMBOL", "BTCUSD")
    mode: str = os.getenv("TRADING_MODE", "paper").lower()
    live_enabled: bool = os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true"
    live_confirmation: str = os.getenv("LIVE_TRADING_CONFIRMATION", "")
    database_path: str = os.getenv("DATABASE_PATH", "data/trading.db")

@dataclass(frozen=True)
class StrategyConfig:
    entry_timeframe: str = "15m"
    trend_timeframe: str = "1h"
    fast_ema: int = 9
    slow_ema: int = 20
    rsi_period: int = 14
    atr_period: int = 14
    volume_period: int = 20
    use_rsi: bool = True
    use_volume: bool = True
    use_htf: bool = True
    min_confidence: int = 65
    atr_stop_multiplier: float = 1.5
    reward_risk: float = 2.0
    max_candle_atr: float = 2.5

@dataclass(frozen=True)
class RiskConfig:
    risk_per_trade: float = .01
    max_daily_loss: float = .03
    max_open_positions: int = 1
    max_consecutive_losses: int = 3
    max_daily_trades: int = 5
    fee_rate: float = .0005
    slippage_rate: float = .0005
    max_leverage: float = 2.0
