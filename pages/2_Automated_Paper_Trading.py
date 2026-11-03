import time, uuid
from datetime import datetime, timezone
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from config import Settings, StrategyConfig
from exchange.delta_client import DeltaClient
from strategy.indicators import normalize_candles, add_indicators
from strategy.ema_strategy import generate_signal
from database.db_manager import Database
from strategy.news_filter import load_news_events, blackout_reason

st.set_page_config(page_title="Automated Paper Trading | BTC Quant Desk", page_icon="🤖", layout="wide")
st.title("Automated Paper Trading")
st.caption("Independent real-time simulation workspace · browser must remain open for polling")
st.warning("PAPER MODE ONLY · No private API credentials · No live order route exists in this workspace.")
settings=Settings(); db=Database(settings.database_path); client=DeltaClient(settings.base_url)
DEFAULT={"starting_balance":10000.0,"cash":10000.0,"realized":0.0,"fees":0.0}
if db.get_state("rt_wallet") is None: db.set_state("rt_wallet",DEFAULT)
if db.get_state("rt_position") is None: db.set_state("rt_position",None)
if db.get_state("rt_status") is None: db.set_state("rt_status","PAUSED")
if db.get_state("rt_history") is None: db.set_state("rt_history",[])
if db.get_state("rt_last_signal") is None: db.set_state("rt_last_signal",None)

with st.sidebar:
    st.header("Paper engine settings")
    tf=st.selectbox("Signal timeframe",["5m","15m","30m","1h"],index=1)
    htf_tf=st.selectbox("Trend timeframe",["15m","30m","1h","2h","4h"],index=2)
    risk_pct=st.slider("Risk per trade (%)",0.25,2.0,1.0,0.25)
    rr=st.selectbox("Reward / risk",[1.0,1.5,2.0,2.5,3.0],index=2)
    atr_mult=st.selectbox("ATR stop multiplier",[1.0,1.5,2.0],index=1)
    lev=st.selectbox("Paper leverage",[1.0,2.0,3.0,5.0],index=0)
    poll=st.selectbox("Refresh interval",[10,15,30,60],index=1,format_func=lambda x:f"{x} seconds")
    start_balance=st.number_input("Paper starting balance (USD)",min_value=100.0,value=float(db.get_state("rt_wallet")["starting_balance"]),step=500.0)
    if st.button("Reset paper account",use_container_width=True):
        if db.get_state("rt_position") is not None: st.error("Close the open paper position first.")
        else:
            db.set_state("rt_wallet",{"starting_balance":float(start_balance),"cash":float(start_balance),"realized":0.0,"fees":0.0}); db.set_state("rt_history",[]); st.rerun()
    st.subheader("News blackout filter")
    news_file=st.file_uploader("Upload upcoming news calendar CSV",type=["csv"],key="paper_news_csv")
    st.caption("Upload an event calendar to block new paper entries around major releases. Existing positions still follow their SL/TP rules.")
    try:
        news_events, news_blackouts = load_news_events(news_file.getvalue() if news_file else None)
        st.caption(f"News events loaded: {len(news_events)}")
    except Exception as exc:
        news_events, news_blackouts = [], []
        st.error(f"News calendar error: {exc}")
    st.caption("EMA 9/20 · RSI 14 · ATR 14 · volume confirmation · HTF filter")

@st.cache_data(ttl=8,show_spinner=False)
def fetch_candles(timeframe,periods=500):
    seconds={"5m":300,"15m":900,"30m":1800,"1h":3600,"2h":7200,"4h":14400}[timeframe]
    end=int(time.time()); rows=client.candles("BTCUSD",timeframe,end-periods*seconds,end)
    frame=normalize_candles(rows)
    if frame.empty: raise RuntimeError("No candle data returned by Delta public API")
    return frame[~frame.index.duplicated(keep="last")].sort_index()

def close_position(pos,price,reason):
    wallet=db.get_state("rt_wallet"); sign=1 if pos["side"]=="LONG" else -1
    gross=(price-pos["entry"])*pos["qty"]*sign; fee=abs(price*pos["qty"])*pos["fee_rate"]
    net=gross-pos["entry_fee"]-fee
    wallet["cash"]+=pos["margin"]+gross-fee; wallet["realized"]+=net; wallet["fees"]+=fee
    db.set_state("rt_wallet",wallet)
    closed={**pos,"exit":float(price),"gross_pnl":gross,"total_fees":pos["entry_fee"]+fee,"net_pnl":net,"reason":reason,"status":"CLOSED","closed_at":datetime.now(timezone.utc).isoformat()}
    hist=db.get_state("rt_history",[]); hist.append(closed); db.set_state("rt_history",hist[-2000:]); db.set_state("rt_position",None)

def open_position(sig):
    wallet=db.get_state("rt_wallet"); entry=float(sig.entry); sl=float(sig.stop_loss); tp=float(sig.take_profit)
    risk_cash=wallet["starting_balance"]*risk_pct/100; fee_rate=.0005
    qty=risk_cash/(abs(entry-sl)+entry*(2*fee_rate+.0005)); margin=qty*entry/lev
    if margin>wallet["cash"]:
        qty=wallet["cash"]*lev/entry; margin=qty*entry/lev
    if qty<=0 or margin>wallet["cash"]: return False
    entry_fee=qty*entry*fee_rate; wallet["cash"]-=margin+entry_fee; wallet["fees"]+=entry_fee
    pos={"id":str(uuid.uuid4()),"side":sig.side.upper(),"qty":qty,"entry":entry,"stop_loss":sl,"take_profit":tp,"margin":margin,"entry_fee":entry_fee,"fee_rate":fee_rate,"opened_at":datetime.now(timezone.utc).isoformat(),"signal_time":sig.timestamp,"confidence":sig.confidence}
    db.set_state("rt_wallet",wallet); db.set_state("rt_position",pos); return True

@st.fragment(run_every=f"{poll}s")
def live_panel():
    try:
        raw=fetch_candles(tf,500); hraw=fetch_candles(htf_tf,300)
        cfg=StrategyConfig(entry_timeframe=tf,trend_timeframe=htf_tf,fast_ema=9,slow_ema=20,use_rsi=True,use_volume=True,use_htf=True,min_confidence=65,atr_stop_multiplier=atr_mult,reward_risk=rr)
        ind=add_indicators(raw,9,20); hind=add_indicators(hraw,9,20)
        # Last row may still be forming; signal generator receives only closed candles.
        closed=ind.iloc[:-1]; hclosed=hind.iloc[:-1]
        sig=generate_signal(closed,hclosed,cfg) if len(closed)>30 and len(hclosed)>30 else None
        price=float(ind.iloc[-1].close); last_closed=closed.iloc[-1]
        pos=db.get_state("rt_position"); status=db.get_state("rt_status","PAUSED")
        # Conservative intrabar exit check on the latest fully completed candle.
        if pos is not None:
            bar=last_closed
            sl_hit=(bar.low<=pos["stop_loss"]) if pos["side"]=="LONG" else (bar.high>=pos["stop_loss"])
            tp_hit=(bar.high>=pos["take_profit"]) if pos["side"]=="LONG" else (bar.low<=pos["take_profit"])
            if sl_hit or tp_hit:
                close_position(pos,pos["stop_loss"] if sl_hit else pos["take_profit"],"STOP_LOSS" if sl_hit else "TAKE_PROFIT")
                pos=None
        # Prevent duplicate entries from same completed signal candle.
        blocked_reason = blackout_reason(last_closed.name, news_blackouts) if sig is not None else None
        if status=="RUNNING" and pos is None and sig is not None and not blocked_reason:
            key=f"{sig.timestamp}:{sig.side}"
            if db.get_state("rt_last_signal")!=key:
                if open_position(sig): db.set_state("rt_last_signal",key); pos=db.get_state("rt_position")
        wallet=db.get_state("rt_wallet"); pos=db.get_state("rt_position")
        unreal=0.0
        if pos:
            direction=1 if pos["side"]=="LONG" else -1; unreal=(price-pos["entry"])*pos["qty"]*direction
        equity=wallet["cash"]+(pos["margin"] if pos else 0)+unreal
        c=st.columns(6); c[0].metric("BTC / USD",f"${price:,.2f}"); c[1].metric("Engine",status); c[2].metric("Paper equity",f"${equity:,.2f}"); c[3].metric("Available cash",f"${wallet['cash']:,.2f}"); c[4].metric("Realized P&L",f"${wallet['realized']:+,.2f}"); c[5].metric("Unrealized P&L",f"${unreal:+,.2f}")
        left,right=st.columns([1.7,1])
        with left:
            chart=ind.tail(160); fig=go.Figure(); fig.add_trace(go.Candlestick(x=chart.index,open=chart.open,high=chart.high,low=chart.low,close=chart.close,name="BTC")); fig.add_trace(go.Scatter(x=chart.index,y=chart.ema_fast,name="EMA 9")); fig.add_trace(go.Scatter(x=chart.index,y=chart.ema_slow,name="EMA 20"));
            if pos: fig.add_hline(y=pos["entry"],line_dash="dot",annotation_text="Entry"); fig.add_hline(y=pos["stop_loss"],line_dash="dash",annotation_text="SL"); fig.add_hline(y=pos["take_profit"],line_dash="dash",annotation_text="TP")
            fig.update_layout(template="plotly_dark",height=470,xaxis_rangeslider_visible=False,margin=dict(l=5,r=5,t=20,b=5)); st.plotly_chart(fig,use_container_width=True)
        with right:
            st.subheader("Signal monitor")
            if sig: st.success(f"{sig.side.upper()} · confidence {sig.confidence}/100"); st.write({"Signal candle":sig.timestamp,"Entry reference":sig.entry,"Stop loss":sig.stop_loss,"Take profit":sig.take_profit,"Reasons":sig.reasons})
            else: st.info("WAIT · no qualifying confirmed crossover")
            if blocked_reason:
                st.error(f"NEWS BLACKOUT · New entry blocked: {blocked_reason}")
            st.subheader("Open paper position")
            if pos: st.write({"Direction":pos["side"],"Quantity (BTC approx.)":round(pos["qty"],6),"Entry":pos["entry"],"Stop loss":pos["stop_loss"],"Take profit":pos["take_profit"],"Unrealized P&L":round(unreal,2)})
            else: st.write("No open position")
            if st.button("Close open paper position",disabled=not bool(pos),use_container_width=True): close_position(pos,price,"MANUAL"); st.rerun()
        hist=db.get_state("rt_history",[])
        if hist:
            df=pd.DataFrame(hist); wins=(df.net_pnl>0).sum(); m=st.columns(4); m[0].metric("Closed trades",len(df)); m[1].metric("Win rate",f"{wins/len(df):.1%}"); m[2].metric("Net P&L",f"${df.net_pnl.sum():,.2f}"); m[3].metric("Fees",f"${df.total_fees.sum():,.2f}")
            st.subheader("Paper trade audit"); st.dataframe(df.sort_values("closed_at",ascending=False),use_container_width=True,hide_index=True)
            st.download_button("Download paper trade CSV",df.to_csv(index=False).encode(),"btc_paper_trade_audit.csv","text/csv")
        st.caption(f"Last market refresh: {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')} · Candle exit checks use closed OHLC bars.")
    except Exception as e: st.error(f"Market monitor error: {type(e).__name__}: {e}")

controls=st.columns(3)
if controls[0].button("▶ Start automated paper trading",type="primary",use_container_width=True): db.set_state("rt_status","RUNNING"); st.rerun()
if controls[1].button("Ⅱ Pause",use_container_width=True): db.set_state("rt_status","PAUSED"); st.rerun()
if controls[2].button("■ Emergency stop",use_container_width=True): db.set_state("rt_status","STOPPED"); st.rerun()
st.caption("Automation runs only while this page is open and connected; polling is handled by Streamlit fragments. News blackout blocks new entries only; open positions remain managed by SL/TP. It is not a 24/7 server-side daemon. Paper quantities and P&L are linear BTC approximations, not Delta contract-exact settlement. Stop/target evaluation uses closed candles and may differ from actual intrabar fills.")
live_panel()
