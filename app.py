import time
import uuid
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import Settings, StrategyConfig
from exchange.delta_client import DeltaClient, DeltaAPIError
from strategy.indicators import normalize_candles, add_indicators
from strategy.ema_strategy import generate_signal
from database.db_manager import Database

st.set_page_config(page_title="BTC Quant Desk", page_icon="₿", layout="wide")
st.markdown("""
<style>
.block-container {padding-top:1.4rem; max-width:1500px}
[data-testid="stMetric"] {background:#111827; border:1px solid #253047; padding:14px 16px; border-radius:12px}
[data-testid="stMetricLabel"] {color:#9ca3af}
div.stButton > button {border-radius:9px; min-height:42px}
.small-muted {color:#9ca3af;font-size:12px}
div[data-testid="stTabs"] button {font-weight:600}
</style>
""", unsafe_allow_html=True)

settings = Settings()
db = Database(settings.database_path)
client = DeltaClient(settings.base_url, settings.api_key, settings.api_secret)

# Paper ledger is intentionally independent of Delta private account APIs.
def init_paper_state():
    if db.get_state("paper_wallet") is None:
        db.set_state("paper_wallet", {"starting_balance": 10000.0, "cash": 10000.0,
                                      "realized_pnl": 0.0, "fees_paid": 0.0,
                                      "currency": "USD"})
    if db.get_state("paper_position") is None:
        db.set_state("paper_position", None)
    if db.get_state("paper_settings") is None:
        db.set_state("paper_settings", {"risk_pct": 1.0, "rr": 2.0, "atr_mult": 1.5,
                                        "leverage": 1.0, "timeframe": "15m",
                                        "trend_tf": "1h", "auto_signal": False})
    if db.get_state("paper_bot_status") is None:
        db.set_state("paper_bot_status", "PAUSED")

init_paper_state()
wallet = db.get_state("paper_wallet")
paper_pos = db.get_state("paper_position")
paper_cfg = db.get_state("paper_settings")

st.title("₿ BTC Quant Desk")
st.caption("DELTA EXCHANGE INDIA · EMA 9/20 · PAPER EXECUTION WORKSPACE")
st.warning("PAPER TRADING ONLY — no private API key is required. No live orders can be sent from this dashboard.")

with st.sidebar:
    st.markdown("### Workspace")
    st.markdown("**Connection**")
    st.success("Public market data")
    st.caption("Private account connection: not configured")
    st.divider()
    st.markdown("**Strategy settings**")
    timeframe = st.selectbox("Entry timeframe", ["5m", "15m", "30m", "1h"],
                              index=["5m","15m","30m","1h"].index(paper_cfg["timeframe"]))
    trend_tf = st.selectbox("Trend confirmation", ["15m", "30m", "1h", "2h", "4h"],
                            index=["15m","30m","1h","2h","4h"].index(paper_cfg["trend_tf"]))
    rr = st.selectbox("Take-profit multiple", [2.0, 3.0],
                      index=0 if paper_cfg["rr"] == 2.0 else 1)
    atr_mult = st.selectbox("ATR stop multiplier", [1.0, 1.5, 2.0],
                            index=[1.0,1.5,2.0].index(paper_cfg["atr_mult"]))
    risk_pct = st.slider("Risk per trade (%)", 0.25, 2.0, float(paper_cfg["risk_pct"]), 0.25)
    leverage = st.selectbox("Paper leverage", [1.0, 2.0, 3.0, 5.0],
                            index=[1.0,2.0,3.0,5.0].index(float(paper_cfg["leverage"])))
    if st.button("Save strategy settings", use_container_width=True):
        paper_cfg.update({"timeframe": timeframe, "trend_tf": trend_tf, "rr": rr,
                          "atr_mult": atr_mult, "risk_pct": risk_pct, "leverage": leverage})
        db.set_state("paper_settings", paper_cfg)
        st.rerun()
    st.divider()
    st.markdown("**Paper wallet**")
    new_balance = st.number_input("Reset starting balance (USD)", min_value=100.0,
                                  max_value=1000000.0, value=float(wallet["starting_balance"]), step=500.0)
    if st.button("Reset paper account", use_container_width=True):
        if db.get_state("paper_position") is not None:
            st.error("Close the open paper position before resetting.")
        else:
            db.set_state("paper_wallet", {"starting_balance": float(new_balance),
                "cash": float(new_balance), "realized_pnl": 0.0, "fees_paid": 0.0,
                "currency": "USD"})
            st.rerun()

def fetch_market(tf):
    end = int(time.time())
    rows = client.candles("BTCUSD", tf, end - 60*86400, end)
    frame = normalize_candles(rows)
    if frame.empty:
        raise RuntimeError("No candle data returned.")
    return frame

def build_strategy_config():
    return StrategyConfig(entry_timeframe=paper_cfg["timeframe"],
        trend_timeframe=paper_cfg["trend_tf"], reward_risk=paper_cfg["rr"],
        atr_stop_multiplier=paper_cfg["atr_mult"], use_rsi=True, use_volume=True,
        use_htf=True, min_confidence=65)

def compute_signal(entry_raw, trend_raw):
    cfg = build_strategy_config()
    entry = add_indicators(entry_raw, cfg.fast_ema, cfg.slow_ema,
                           cfg.rsi_period, cfg.atr_period, cfg.volume_period)
    trend = add_indicators(trend_raw, cfg.fast_ema, cfg.slow_ema,
                           cfg.rsi_period, cfg.atr_period, cfg.volume_period)
    # Exclude the currently forming candle on both frames.
    sig = generate_signal(entry.iloc[:-1], trend.iloc[:-1], cfg)
    return entry, trend, sig

def close_paper_position(position, exit_price, reason):
    global wallet
    side_sign = 1 if position["side"] == "LONG" else -1
    qty = float(position["quantity"])
    gross = (exit_price - position["entry"]) * qty * side_sign
    exit_fee = abs(exit_price * qty) * position["fee_rate"]
    total_fees = float(position["entry_fee"]) + exit_fee
    net = gross - total_fees
    wallet["cash"] += float(position["margin"]) + gross - exit_fee
    wallet["realized_pnl"] += net
    wallet["fees_paid"] += exit_fee
    db.set_state("paper_wallet", wallet)
    closed = dict(position)
    closed.update({"exit": float(exit_price), "gross_pnl": gross, "fees": total_fees,
                   "net_pnl": net, "status": "CLOSED", "exit_reason": reason,
                   "closed_at": datetime.now(timezone.utc).isoformat()})
    db.set_state("paper_last_closed", closed)
    db.set_state("paper_position", None)
    db.set_state("paper_history", (db.get_state("paper_history", []) + [closed])[-500:])
    return closed

def open_paper_position(side, entry, sl, tp, confidence, signal_time):
    global wallet
    if db.get_state("paper_position") is not None:
        raise ValueError("Only one open paper position is allowed.")
    risk_cash = wallet["starting_balance"] * (paper_cfg["risk_pct"] / 100.0)
    stop_distance = abs(entry - sl)
    fee_rate = 0.0005
    # Linear BTC quantity approximation; not an exchange contract calculator.
    per_btc_risk = stop_distance + entry * (2 * fee_rate + 0.0005)
    qty = risk_cash / per_btc_risk
    notional = qty * entry
    margin = notional / paper_cfg["leverage"]
    if margin > wallet["cash"]:
        qty = wallet["cash"] * paper_cfg["leverage"] / entry
        notional = qty * entry
        margin = notional / paper_cfg["leverage"]
    if qty <= 0 or margin > wallet["cash"]:
        raise ValueError("Insufficient paper balance for this simulated position.")
    entry_fee = notional * fee_rate
    wallet["cash"] -= margin + entry_fee
    wallet["fees_paid"] += entry_fee
    wallet["cash"] = max(0.0, wallet["cash"])
    pos = {"id": str(uuid.uuid4()), "side": side, "quantity": qty, "entry": entry,
           "stop_loss": sl, "take_profit": tp, "margin": margin,
           "entry_fee": entry_fee, "fee_rate": fee_rate, "confidence": confidence,
           "signal_time": signal_time, "opened_at": datetime.now(timezone.utc).isoformat(),
           "status": "OPEN"}
    db.set_state("paper_wallet", wallet)
    db.set_state("paper_position", pos)
    return pos

# Fetch public data on every rerun; Streamlit reruns on button interactions.
market_error = None
try:
    entry_raw = fetch_market(timeframe)
    trend_raw = fetch_market(trend_tf)
    entry_ind, trend_ind, signal = compute_signal(entry_raw, trend_raw)
    last_closed = entry_ind.iloc[-2]
    last_price = float(last_closed.close)
except Exception as exc:
    market_error = f"{type(exc).__name__}: {exc}"
    entry_raw = pd.DataFrame()
    entry_ind = pd.DataFrame()
    trend_ind = pd.DataFrame()
    signal = None
    last_price = None

if market_error:
    st.error("Unable to load public Delta market data: " + market_error)
    st.info("Check internet connectivity and the public India API endpoint. Paper trades require a valid market price.")

position = db.get_state("paper_position")
wallet = db.get_state("paper_wallet")
unrealized = 0.0
if position and last_price:
    sign = 1 if position["side"] == "LONG" else -1
    unrealized = (last_price - position["entry"]) * position["quantity"] * sign
equity = wallet["cash"] + (position["margin"] if position else 0) + unrealized

# Header metrics
m = st.columns(5)
m[0].metric("BTC / USD", f"${last_price:,.2f}" if last_price else "—")
m[1].metric("Paper equity", f"${equity:,.2f}")
m[2].metric("Available cash", f"${wallet['cash']:,.2f}")
m[3].metric("Realized P&L", f"${wallet['realized_pnl']:,.2f}",
            delta=f"{wallet['realized_pnl']:+,.2f}")
m[4].metric("Unrealized P&L", f"${unrealized:,.2f}",
            delta=f"{unrealized:+,.2f}")

tab_overview, tab_trade, tab_history, tab_controls = st.tabs(
    ["Market overview", "Paper trading", "Trade history", "Bot controls"])

with tab_overview:
    left, right = st.columns([1.7, 1])
    with left:
        st.subheader("BTC market structure")
        if not entry_ind.empty:
            plot = entry_ind.tail(180)
            fig = go.Figure()
            fig.add_trace(go.Candlestick(x=plot.index, open=plot.open, high=plot.high,
                low=plot.low, close=plot.close, name="BTC"))
            fig.add_trace(go.Scatter(x=plot.index, y=plot.ema_fast, name="EMA 9",
                                     line={"width":1.5}))
            fig.add_trace(go.Scatter(x=plot.index, y=plot.ema_slow, name="EMA 20",
                                     line={"width":1.5}))
            fig.update_layout(height=480, template="plotly_dark", xaxis_rangeslider_visible=False,
                              margin=dict(l=10,r=10,t=30,b=10), legend=dict(orientation="h"))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Chart will appear when market data is available.")
    with right:
        st.subheader("Indicator panel")
        if not entry_ind.empty:
            st.metric("EMA 9", f"${last_closed.ema_fast:,.2f}")
            st.metric("EMA 20", f"${last_closed.ema_slow:,.2f}")
            st.metric("RSI (14)", f"{last_closed.rsi:.2f}")
            st.metric("ATR (14)", f"${last_closed.atr:,.2f}")
            st.metric("Volume / average", f"{last_closed.volume / last_closed.volume_sma:.2f}x"
                      if last_closed.volume_sma else "—")
        st.subheader("Latest signal")
        if signal:
            st.success(f"{signal.side.upper()} · confidence {signal.confidence}/100")
            st.write({"Entry reference": round(signal.entry,2), "Stop loss": round(signal.stop_loss,2),
                      "Take profit": round(signal.take_profit,2), "R:R": signal.rr,
                      "Closed candle": signal.timestamp, "Reasons": signal.reasons})
        else:
            st.info("WAIT — no qualifying confirmed crossover.")

with tab_trade:
    st.subheader("Paper order ticket")
    st.caption("Orders below are simulated locally. They are not sent to Delta Exchange.")
    if position:
        st.warning(f"Open {position['side']} paper position · {position['quantity']:.6f} BTC")
        st.write({"Entry": position["entry"], "Stop loss": position["stop_loss"],
                  "Take profit": position["take_profit"], "Margin": position["margin"],
                  "Unrealized P&L": unrealized})
        c1,c2 = st.columns(2)
        if c1.button("Close paper position at latest price", type="primary", use_container_width=True,
                     disabled=not bool(last_price)):
            close_paper_position(position, last_price, "MANUAL")
            st.rerun()
        if c2.button("Close at stop-loss reference", use_container_width=True):
            close_paper_position(position, position["stop_loss"], "MANUAL_SL")
            st.rerun()
    else:
        if signal:
            st.info(f"Strategy setup: {signal.side.upper()} · entry ${signal.entry:,.2f} · "
                    f"SL ${signal.stop_loss:,.2f} · TP ${signal.take_profit:,.2f}")
        c1,c2 = st.columns(2)
        disabled = bool(market_error or not last_price)
        if c1.button("Execute LONG paper trade", type="primary", use_container_width=True,
                     disabled=disabled):
            ref = signal if signal and signal.side=="long" else None
            if ref:
                open_paper_position("LONG", ref.entry, ref.stop_loss, ref.take_profit,
                                    ref.confidence, ref.timestamp)
                st.rerun()
            else: st.error("No qualifying LONG signal. Use the manual ticket below only if you understand the risk.")
        if c2.button("Execute SHORT paper trade", use_container_width=True, disabled=disabled):
            ref = signal if signal and signal.side=="short" else None
            if ref:
                open_paper_position("SHORT", ref.entry, ref.stop_loss, ref.take_profit,
                                    ref.confidence, ref.timestamp)
                st.rerun()
            else: st.error("No qualifying SHORT signal.")
        with st.expander("Manual paper order (testing only)"):
            side = st.radio("Direction", ["LONG","SHORT"], horizontal=True)
            e = st.number_input("Entry price", min_value=1.0, value=float(last_price or 90000.0))
            stop_gap = st.number_input("Stop distance (USD)", min_value=1.0, value=500.0)
            target_r = st.selectbox("Target R multiple", [2.0,3.0])
            sl = e-stop_gap if side=="LONG" else e+stop_gap
            tp = e+stop_gap*target_r if side=="LONG" else e-stop_gap*target_r
            st.caption(f"SL ${sl:,.2f} · TP ${tp:,.2f}")
            if st.button("Place manual paper order", use_container_width=True, disabled=disabled):
                open_paper_position(side,e,sl,tp,0,"MANUAL")
                st.rerun()
    st.divider()
    st.caption("Simulated fee: 0.05% per side. Slippage reserve is used in sizing. P&L is a linear BTC approximation, not a reproduction of Delta's contract settlement.")

with tab_history:
    st.subheader("Closed paper trades")
    history = db.get_state("paper_history", [])
    if history:
        hist = pd.DataFrame(history).sort_values("closed_at", ascending=False)
        cols = [c for c in ["closed_at","side","quantity","entry","exit","stop_loss",
                            "take_profit","net_pnl","fees","exit_reason"] if c in hist]
        st.dataframe(hist[cols], use_container_width=True, hide_index=True)
        total = sum(float(x.get("net_pnl",0)) for x in history)
        wins = sum(1 for x in history if float(x.get("net_pnl",0)) > 0)
        a,b,c = st.columns(3)
        a.metric("Closed trades", len(history))
        b.metric("Win rate", f"{wins/len(history)*100:.1f}%")
        c.metric("Cumulative net P&L", f"${total:,.2f}")
    else:
        st.info("No closed paper trades yet.")

with tab_controls:
    st.subheader("Paper bot controls")
    status = db.get_state("paper_bot_status", "PAUSED")
    st.write(f"Current status: **{status}**")
    a,b,c = st.columns(3)
    if a.button("Start signal monitoring", type="primary", use_container_width=True):
        db.set_state("paper_bot_status","RUNNING")
        st.rerun()
    if b.button("Pause", use_container_width=True):
        db.set_state("paper_bot_status","PAUSED")
        st.rerun()
    if c.button("Emergency stop", use_container_width=True):
        db.set_state("paper_bot_status","STOPPED")
        st.rerun()
    st.info("The current build monitors signals on dashboard refresh; it does not run an unattended background order loop. Start/Pause/Stop are state controls, not a promise of continuous execution.")
    st.subheader("Safety boundaries")
    st.markdown("""
    - This page has no live order submission path.
    - API keys are not required for public price/candle data.
    - No credentials should be pasted into this dashboard or chat yet.
    - Paper account and trade ledger are stored locally in SQLite.
    - The paper P&L model is linear BTC quantity simulation; Delta contract multiplier, settlement, funding and fee tier still need account/product verification.
    """)
st.caption(f"Last dashboard refresh: {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')} · Paper mode")
