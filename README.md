# BTC EMA 9/20 Trading Desk — Delta Exchange India

Paper-first modular Python baseline. This is **not production-ready or certified live trading software**.

## Included
- Delta India REST client with HMAC-SHA256 signing, environment credentials, timeouts and GET retries.
- Public product/candle/ticker methods and private wallet/position/order reads.
- EMA 9/20, RSI 14, ATR 14, volume average and EMA 200 calculations.
- Confirmed closed-candle crossover signals, higher-timeframe filter and confidence score.
- Risk sizing with fee/slippage reserve and leverage/margin cap; daily risk gates.
- SQLite ledger, paper fills, stop-first intrabar assumption, backtest baseline and metrics.
- Streamlit market dashboard, Telegram helper and pytest tests.

## Install and run
Python 3.11+:
```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```
Run tests with `pytest -q`. Add credentials only to `.env`; never commit it or share secrets in chat.

## Verified Delta India API
- Production REST: `https://api.india.delta.exchange`
- India Demo/testnet: `https://cdn-ind.testnet.deltaex.org`
- Candles: `GET /v2/history/candles`; products: `GET /v2/products`; orders: `/v2/orders`; positions: `/v2/positions`; wallet: `/v2/wallet/balances`.
- Auth signature: `METHOD + timestamp + path + query string + exact JSON body`, HMAC-SHA256 hex. Required headers include api-key, timestamp, signature and User-Agent. Sign immediately before sending; docs specify a five-second validity window.
- Orders require product IDs. Resolve product metadata from the India environment instead of assuming an ID.
- Current docs expose `stop_loss_order`, `take_profit_order`, stop price, reduce-only and bracket-order request fields. Verify bracket endpoint behavior, product-specific size rules and order state against the intended India account before use.
- Trading API keys require trading permission and IP whitelisting. Prefer read-only access during initial validation.

## Strategy
- Discard the currently forming candle on entry and HTF timeframes.
- Long: previous EMA9 <= EMA20 and latest closed EMA9 > EMA20. Short: inverse.
- RSI long 50–75; short 25–50. Volume must exceed rolling mean. HTF close must agree with HTF EMA20.
- SL = 1.5 ATR; TP = 2R. Confidence is an agreement score, not a win probability.
- Reject flat EMAs, low ATR, unusually large candle and abnormal volume.

## Important limitations before live trading
- `TRADING_MODE=paper` is the default. Live execution intentionally raises `NotImplementedError` even after the gate, until order lifecycle, partial fills, exchange-side bracket verification and restart recovery are integration-tested.
- Contract multiplier, minimum size, lot increment, tick size, margin and fees are product/account-specific. The sizing module requires verified values; do not infer them from BTCUSD.
- The backtest baseline is not a full six-to-twelve-month walk-forward research report. It currently excludes funding, exchange-specific contract P&L conversion, partial fills and detailed fee tiers. OHLC intrabar ambiguity is conservatively stop-first.
- Websocket reconnection, private stream state machine, trailing-stop edits, emergency close/dead-man heartbeat, complete daily P&L accounting and robust restart reconciliation remain integration tasks.
- No performance or profitability claims. Do not enable live trading based on unit tests alone.

## Next validation phases
1. Read-only India API smoke tests and product metadata inspection.
2. Candle-window chunking and data-quality checks for 5m/15m/30m/1h.
3. Unit tests and backtest verification against independent calculations.
4. Paper engine lifecycle, duplicate prevention and restart reconciliation.
5. Streamlit controls and Telegram delivery.
6. Demo/testnet order and bracket tests, including partial fill/rejection/timeout.
7. Independent review before any live execution release.

Leveraged derivatives can cause rapid losses. This is experimental software, not investment advice.


## Browser dashboard and paper trading
The Streamlit web dashboard is launched locally with `streamlit run app.py`.
It provides public BTC candle/indicator panels, signal view, a paper wallet, manual and signal-triggered simulated trades, position close controls, trade history, and paper bot state controls. It does not send private or live orders. Paper ledger state is persisted in SQLite.
The current paper simulator uses a linear BTC quantity approximation and a configurable USD-denominated paper wallet. It is not contract-exact for Delta's BTCUSD derivatives and does not model funding or exchange-specific liquidation.
