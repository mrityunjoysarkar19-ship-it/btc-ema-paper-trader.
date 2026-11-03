import time
from datetime import date, timedelta
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from config import Settings
from exchange.delta_client import DeltaClient
from strategy.indicators import normalize_candles, add_indicators
from backtesting.backtest_engine import run_backtest
from backtesting.performance import summarize
from strategy.news_filter import load_news_events

st.set_page_config(page_title="Strategy Research | BTC Quant Desk", page_icon="📊", layout="wide")
st.title("Strategy Research & Backtesting")
st.caption("Historical research workspace · isolated from the paper-trading ledger")
settings=Settings(); client=DeltaClient(settings.base_url)
with st.sidebar:
    st.header("Backtest configuration")
    tf=st.selectbox("Timeframe",["5m","15m","30m","1h"],index=1)
    lookback=st.selectbox("Historical period",[30,60,90,180,365],index=2,format_func=lambda x:f"{x} days")
    fast=st.number_input("Fast EMA",min_value=2,max_value=50,value=9)
    slow=st.number_input("Slow EMA",min_value=3,max_value=200,value=20)
    rr=st.selectbox("Reward / risk",[0.8,1.0,1.5,2.0,2.5,3.0],index=3)
    atr_mult=st.selectbox("ATR stop multiplier",[1.0,1.2,1.5,2.0],index=2)
    fee=st.number_input("Fee per side (%)",min_value=0.0,max_value=1.0,value=0.05,step=0.01)/100
    slip=st.number_input("Slippage per side (%)",min_value=0.0,max_value=1.0,value=0.05,step=0.01)/100
    initial=st.number_input("Starting equity (USD)",min_value=100.0,value=10000.0,step=500.0)
    variants=st.multiselect("Compare filters",["EMA crossover only","EMA + RSI","EMA + RSI + volume","EMA + RSI + volume + HTF","Trend + EMA crossover (candidate)"],default=["EMA crossover only","EMA + RSI + volume + HTF","Trend + EMA crossover (candidate)"])
    st.subheader("News blackout filter")
    news_file=st.file_uploader("Upload historical news calendar CSV",type=["csv"],key="research_news_csv")
    st.caption("CSV timestamps must be ISO-8601 UTC (for example 2026-11-03T18:30:00Z). No new entries are opened inside event blackout windows; existing trades remain managed.")
    run=st.button("Run backtest",type="primary",use_container_width=True)

@st.cache_data(ttl=300,show_spinner=False)
def load_data(timeframe,days):
    end=int(time.time()); start=end-days*86400
    # Chunk requests to avoid oversized candle windows.
    seconds={"5m":300,"15m":900,"30m":1800,"1h":3600,"2h":7200,"4h":14400}[timeframe]
    max_window=180*seconds
    chunks=[]; cursor=start
    while cursor<end:
        chunk_end=min(end,cursor+max_window)
        rows=client.candles("BTCUSD",timeframe,cursor,chunk_end)
        if isinstance(rows,list) and rows: chunks.extend(rows)
        cursor=chunk_end
    frame=normalize_candles(chunks)
    if frame.empty: raise RuntimeError("Delta returned no historical candles")
    return frame[~frame.index.duplicated(keep="last")].sort_index()

if "research_results" not in st.session_state: st.session_state.research_results=None
if run:
    try:
        with st.spinner("Downloading historical candles and running simulations..."):
            raw=load_data(tf,lookback)
            if len(raw)<max(100,slow+20): raise RuntimeError(f"Insufficient history: only {len(raw)} candles received")
            htf_map={"5m":"1h","15m":"1h","30m":"1h","1h":"4h"}
            htf=None
            try:
                hraw=load_data(htf_map[tf],lookback)
                htf=add_indicators(hraw,fast,slow)
            except Exception: htf=None
            news_events, news_blackouts = load_news_events(news_file.getvalue() if news_file else None)
            st.info(f"News filter: {len(news_events)} events loaded · {sum(1 for _ in news_blackouts)} blackout windows")
            names={"EMA crossover only":"ema","EMA + RSI":"ema_rsi","EMA + RSI + volume":"ema_rsi_volume","EMA + RSI + volume + HTF":"ema_rsi_volume_htf","Trend + EMA crossover (candidate)":"trend_pullback"}
            results={}
            for label in variants:
                res=run_backtest(raw,htf=htf,fast=int(fast),slow=int(slow),fee=fee,slippage=slip,rr=rr,variant=names[label],atr_mult=(1.2 if label=="Trend + EMA crossover (candidate)" else atr_mult),news_blackouts=news_blackouts)
                metrics=summarize(res)
                metrics["ending_equity_usd"]=initial*res["ending_equity"]
                metrics["net_pnl_usd"]=metrics["ending_equity_usd"]-initial
                results[label]=(res,metrics)
            st.session_state.research_results=(raw,results,tf,lookback,initial)
    except Exception as e: st.error(f"Backtest failed: {type(e).__name__}: {e}")

if st.session_state.research_results:
    raw,results,used_tf,days,capital=st.session_state.research_results
    st.success(f"Loaded {len(raw):,} candles · {used_tf} · {days} days · {raw.index.min()} to {raw.index.max()}")
    if not results: st.info("Select at least one strategy filter and run the backtest.")
    else:
        summary=[]
        for label,(res,m) in results.items(): summary.append({"Strategy":label,"Trades":m["total_trades"],"Win rate":m["win_rate"],"Net P&L":m["net_pnl_usd"],"Profit factor":m["profit_factor"],"Max drawdown":m["max_drawdown"],"Profit trades":m.get("winning_trades",0),"Ending equity":m["ending_equity_usd"]})
        sdf=pd.DataFrame(summary)
        best=sdf.sort_values("Net P&L",ascending=False).iloc[0]
        cols=st.columns(5)
        cols[0].metric("Candles",f"{len(raw):,}"); cols[1].metric("Best net P&L",f"${best['Net P&L']:,.2f}"); cols[2].metric("Best win rate",f"{best['Win rate']:.1%}"); cols[3].metric("Profit factor",f"{best['Profit factor']:.2f}" if pd.notna(best['Profit factor']) else "—"); cols[4].metric("Max drawdown",f"{best['Max drawdown']:.1%}")
        st.subheader("Strategy comparison")
        st.dataframe(sdf.style.format({"Win rate":"{:.1%}","Net P&L":"${:,.2f}","Profit factor":"{:.2f}","Max drawdown":"{:.1%}","Ending equity":"${:,.2f}"}),use_container_width=True,hide_index=True)
        tabs=st.tabs(list(results.keys()))
        for tab,(label,(res,metrics)) in zip(tabs,results.items()):
            with tab:
                trades=res["trades"].copy(); eq=res["equity"]
                st.subheader(label)
                fig=go.Figure(); curve=capital*eq
                fig.add_trace(go.Scatter(y=curve,name="Equity",mode="lines",line={"width":2}))
                fig.update_layout(template="plotly_dark",height=330,margin=dict(l=10,r=10,t=25,b=10),yaxis_title="Equity (USD)")
                st.plotly_chart(fig,use_container_width=True)
                if not trades.empty:
                    trades["net_pnl_usd"]=trades["return"]*capital
                    trades["trade_number"]=range(1,len(trades)+1)
                    st.caption("Research assumptions: confirmed-candle signal, next-candle-open entry, news blackout blocks new entries only, stop-first if SL and TP both touch in one bar, end-of-test liquidation, marked-to-market equity. This is a comparative signal study, not Delta contract-exact sizing. The Trend + EMA candidate uses 1h EMA200 regime, rising/falling 1h EMA20, 15m EMA9/20 cross, RSI band and above-average volume; SL=1.2 ATR and target uses selected R:R.")
                    st.dataframe(trades,use_container_width=True,hide_index=True)
                    st.download_button("Download trade audit CSV",trades.to_csv(index=False).encode(),file_name=f"btc_{label.lower().replace(' ','_')}_trades.csv",mime="text/csv")
                else: st.info("No trades triggered for this configuration.")
else:
    st.info("Choose your settings in the sidebar and tap **Run backtest**. Historical performance is research only and does not predict future results.")
