import streamlit as st
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np

# Page Configuration
st.set_page_config(page_title="Damodaran Narrative Valuation Studio", layout="wide")

# --- DATA FETCHING ---
@st.cache_data(ttl=600)
def fetch_stock_data(ticker_symbol):
    ticker_symbol = ticker_symbol.upper().strip()
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info or {}
        data = {
            "ticker": ticker_symbol,
            "company_name": info.get("longName", ticker_symbol),
            "revenue_ttm": info.get("totalRevenue") or 1_000_000_000,
            "operating_margin": info.get("operatingMargins") or 0.12,
            "shares_outstanding": info.get("sharesOutstanding") or 10_000_000,
            "current_price": float(info.get("currentPrice") or info.get("regularMarketPrice") or 50.0),
            "total_debt": info.get("totalDebt") or 0.0,
            "cash": info.get("totalCash") or 0.0,
            "revenue_growth_1y": info.get("revenueGrowth") or 0.10,
        }
        return data, True
    except:
        return {"ticker": ticker_symbol, "company_name": ticker_symbol, "revenue_ttm": 1e9, "operating_margin": 0.1, "shares_outstanding": 1e7, "current_price": 50, "total_debt": 0, "cash": 0, "revenue_growth_1y": 0.1}, False

# --- LOGIC (Global Scope) ---
def calculate_dcf(rev_0, margin_0, target_margin, growth, sc, wacc):
    years = np.arange(1, 6)
    revenues = rev_0 * (1 + growth) ** years
    margins = np.linspace(margin_0, target_margin, 5)
    ebits = revenues * margins
    reinvestments = np.maximum(0.0, (revenues - np.insert(revenues, 0, rev_0)[:-1]) / sc)
    fcffs = (ebits * 0.79) - reinvestments
    pvs = fcffs / (1 + wacc) ** years
    tv = (ebits[-1] * 1.03 * 0.79 * (1 - (0.03 / 0.075))) / (0.075 - 0.03)
    pv_tv = tv / (1 + wacc) ** 5
    return {"years": years, "revenues": revenues, "fcffs": fcffs, "operating_value": sum(pvs) + pv_tv}

# --- UI ---
st.title("📊 Aswath Damodaran Narrative Valuation Studio")

ticker_input = st.sidebar.text_input("Ticker", value="MSTR").strip().upper()
stock_data, _ = fetch_stock_data(ticker_input)

# Sliders
growth = st.sidebar.slider("Growth Rate", 0.0, 0.8, 0.15)
margin = st.sidebar.slider("Target Margin", -0.1, 0.6, 0.2)
sc = st.sidebar.slider("Sales/Capital", 0.1, 5.0, 2.0)
wacc = st.sidebar.slider("WACC", 0.04, 0.2, 0.08)
treasury = st.sidebar.slider("Treasury ($B)", 0.0, 50.0, 0.0)

# Calculations (Global Scope)
dcf = calculate_dcf(stock_data["revenue_ttm"], stock_data["operating_margin"], margin, growth, sc, wacc)
equity = (dcf["operating_value"] - (stock_data["total_debt"] - stock_data["cash"]) + (treasury * 1e9))

# Tabs
tab1, tab2 = st.tabs(["📊 Interactive Valuation Studio", "📖 Theory & Explanation"])

with tab1:
    st.metric("Intrinsic Value per Share", f"${max(0, equity/stock_data['shares_outstanding']):.2f}")
    projection_df = pd.DataFrame({"Revenue ($B)": dcf["revenues"]/1e9, "FCFF ($B)": dcf["fcffs"]/1e9}, index=[f"Yr {y}" for y in dcf["years"]])
    st.dataframe(projection_df)

with tab2:
    st.header("📖 Narrative Valuation Theory")
    st.write("Valuation is a bridge between narrative and numbers. This tab explains how your story inputs determine the valuation outputs.")
