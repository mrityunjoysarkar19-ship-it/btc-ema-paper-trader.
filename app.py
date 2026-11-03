import streamlit as st

st.set_page_config(page_title="BTC Quant Research Desk", page_icon="₿", layout="wide")
st.markdown("""
<style>
.block-container{max-width:1600px;padding-top:1.4rem}
[data-testid="stMetric"]{background:#111827;border:1px solid #263247;padding:14px 16px;border-radius:12px}
[data-testid="stTabs"] button{font-weight:600}
</style>
""", unsafe_allow_html=True)
st.title("₿ BTC Quant Research Desk")
st.caption("DELTA EXCHANGE INDIA · EMA 9/20 · RESEARCH + PAPER EXECUTION")
st.warning("RESEARCH / PAPER ONLY. Live order execution is intentionally unavailable. Do not add API credentials.")
st.markdown("### Choose your workspace")
a,b=st.columns(2)
with a:
    st.subheader("01 · Strategy Research & Backtesting")
    st.write("Test historical BTC candles, compare strategy variants, inspect every trade, and review equity curve, drawdown, profit factor, fees and slippage.")
    st.page_link("pages/1_Strategy_Research.py", label="Open Strategy Research", icon="📊", use_container_width=True)
with b:
    st.subheader("02 · Automated Paper Trading")
    st.write("Monitor confirmed closed-candle signals, simulate entries and exits automatically, and track open risk and paper-account performance in a separate workspace.")
    st.page_link("pages/2_Automated_Paper_Trading.py", label="Open Paper Trading", icon="🤖", use_container_width=True)
st.divider()
st.markdown("**Safety roadmap:** historical validation → forward paper testing → independent review → Delta demo/testnet verification → explicit live-trading approval. Passing a backtest or unit test does not mean a strategy is 100% safe or profitable.")
