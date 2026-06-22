import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(page_title="Damodaran Valuation Studio", layout="wide")

# --- DATA FETCHING (Robust) ---
@st.cache_data(ttl=600)
def get_data(ticker):
    try:
        t = yf.Ticker(ticker)
        i = t.info
        # Use balance sheet to find cash/investments
        bs = t.balance_sheet
        # Fallback for MSTR-like assets
        investments = 0
        if not bs.empty:
            # Look for common labels for non-operating assets
            for label in ['Long Term Investments', 'Other Assets', 'Other Current Assets']:
                if label in bs.index:
                    investments = max(investments, float(bs.loc[label].iloc[0]))
        
        return {
            "name": i.get("longName", ticker),
            "rev": i.get("totalRevenue") or 1e9,
            "margin": i.get("operatingMargins") or 0.1,
            "shares": i.get("sharesOutstanding") or 1e7,
            "price": i.get("currentPrice") or 50.0,
            "debt": i.get("totalDebt") or 0.0,
            "cash": i.get("totalCash") or 0.0,
            "investments": investments,
            "growth": i.get("revenueGrowth") or 0.1
        }
    except:
        return {"name": ticker, "rev": 1e9, "margin": 0.1, "shares": 1e7, "price": 50, "debt": 0, "cash": 0, "investments": 0, "growth": 0.1}

# --- UI ---
st.title("📊 Damodaran Valuation Studio")
ticker = st.sidebar.text_input("Ticker", "MSTR").upper()
data = get_data(ticker)

# Sliders (Centralized)
growth = st.sidebar.slider("Growth Rate", 0.0, 0.5, 0.1)
margin = st.sidebar.slider("Target Margin", -0.2, 0.5, 0.1)
wacc = st.sidebar.slider("WACC", 0.05, 0.2, 0.08)

# --- CALCULATIONS ---
years = np.arange(1, 6)
revs = data["rev"] * (1 + growth) ** years
margins = np.linspace(data["margin"], margin, 5)
ebits = revs * margins
fcffs = (ebits * 0.79) 
pvs = fcffs / (1 + wacc) ** years
tv = (ebits[-1] * 1.03 * 0.79) / (wacc - 0.03)
pv_tv = tv / (1 + wacc) ** 5

# Correct Valuation Bridge: Operating + Non-Op Assets - Debt
op_val = sum(pvs) + pv_tv
equity_val = op_val + data["investments"] + data["cash"] - data["debt"]
price_per_share = max(0, equity_val / data["shares"])

# --- DISPLAY ---
tab1, tab2 = st.tabs(["📊 Studio", "📖 Theory"])
with tab1:
    st.metric("Intrinsic Value per Share", f"${price_per_share:,.2f}")
    st.write(f"Operating Assets: ${op_val/1e9:,.2f}B | Non-Op Assets: ${data['investments']/1e9:,.2f}B | Debt: ${data['debt']/1e9:,.2f}B")
    st.line_chart(pd.DataFrame({"Revs": revs}, index=years))

with tab2:
    st.header("📖 Valuation Theory")
    st.write("Intrinsic value is the sum of discounted cash flows. For companies like MSTR, non-operating assets (Bitcoin) are added back to the operating value before subtracting debt.")
