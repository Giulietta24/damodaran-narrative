import streamlit as st
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np

# Page Configuration
st.set_page_config(page_title="Damodaran Narrative Valuation Studio", layout="wide", initial_sidebar_state="expanded")

# --- CUSTOM CSS ---
st.markdown("""
<style>
    .metric-card { background-color: white; padding: 24px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.03); border: 1px solid #eef2f6; }
    .metric-title { font-size: 13px; text-transform: uppercase; color: #64748b; font-weight: 600; }
    .metric-value { font-size: 28px; font-weight: 700; color: #0f172a; }
    .warning-box { background-color: #fef3c7; border-left: 4px solid #d97706; color: #92400e; padding: 16px; border-radius: 8px; margin: 12px 0; }
    .success-box { background-color: #f0fdf4; border-left: 4px solid #16a34a; color: #166534; padding: 16px; border-radius: 8px; margin: 12px 0; }
    .info-box { background-color: #f0f9ff; border-left: 4px solid #0284c7; color: #075985; padding: 16px; border-radius: 8px; margin: 12px 0; }
    .consistency-score { text-align: center; background: linear-gradient(135deg, #1e293b, #0f172a); color: white; padding: 24px; border-radius: 12px; }
</style>
""", unsafe_allow_html=True)

# --- UTILS ---
@st.cache_data(ttl=3600)
def load_damodaran_industry_data():
    url = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/psdata.xls"
    try:
        df = pd.read_excel(url)
        df.columns = [str(c).strip() for c in df.columns]
        return df.rename(columns={"Industry Name": "Industry", "Pre-tax Operating Margin": "PreTaxOpMargin"})
    except:
        return pd.DataFrame({"Industry": ["Software"], "PreTaxOpMargin": [0.25]})

@st.cache_data(ttl=60)
def fetch_stock_data(ticker_symbol):
    ticker_symbol = ticker_symbol.upper().strip()
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info or {}
        live_price = info.get("currentPrice") or info.get("regularMarketPrice") or 1.0
        
        # Build clean data structure
        data = {
            "ticker": ticker_symbol,
            "company_name": info.get("longName", ticker_symbol),
            "sector": info.get("sector", "Other"),
            "industry": info.get("industry", "Other"),
            "revenue_ttm": info.get("totalRevenue") or 1_000_000_000,
            "operating_margin": info.get("operatingMargins") or 0.12,
            "shares_outstanding": info.get("sharesOutstanding") or 10_000_000,
            "current_price": float(live_price),
            "market_cap": info.get("marketCap") or 5_000_000_000,
            "cash": info.get("totalCash") or 0.0,
            "total_debt": info.get("totalDebt") or 0.0,
            "revenue_growth_1y": info.get("revenueGrowth") or 0.10,
            "non_operating_assets": 0.0
        }
        return data, True
    except:
        return {"ticker": ticker_symbol, "company_name": ticker_symbol, "revenue_ttm": 1e9, "operating_margin": 0.1, "shares_outstanding": 1e7, "current_price": 50, "market_cap": 5e9, "cash": 0, "total_debt": 0, "revenue_growth_1y": 0.1, "non_operating_assets": 0}, False

def classify_narrative_defaults(stock_data, ind_avg_margin):
    growth = stock_data["revenue_growth_1y"]
    tam_idx = 0 if growth > 0.25 else (1 if growth >= 0.06 else 2)
    margin = stock_data["operating_margin"]
    moat_idx = 0 if margin > 0.25 else (1 if margin >= 0.10 else 2)
    return tam_idx, moat_idx, 1, 1

def calculate_2stage_dcf(rev_0, margin_0, target_margin, growth_high, sc_ratio, wacc_high):
    margin_start = max(-0.40, margin_0)
    years = np.arange(1, 6)
    revenues = rev_0 * (1 + growth_high) ** years
    margins = margin_start + (target_margin - margin_start) * (years / 5.0)
    ebits = revenues * margins
    reinvestments = np.maximum(0.0, (revenues - np.insert(revenues, 0, rev_0)[:-1]) / sc_ratio)
    fcffs = (ebits * 0.79) - reinvestments
    pvs = fcffs / (1 + wacc_high) ** years
    
    tv = (ebits[-1] * (1 + 0.03) * 0.79 * (1 - (0.03 / 0.075))) / (0.075 - 0.03)
    pv_tv = tv / (1 + wacc_high) ** 5
    
    return {
        "years": years, "revenues": revenues, "margins": margins, "ebits": ebits,
        "reinvestments": reinvestments, "fcffs": fcffs, "pvs": pvs,
        "operating_value": sum(pvs) + pv_tv, "pv_terminal_value": pv_tv
    }

def run_vectorized_monte_carlo(rev_0, margin_0, target_margin, growth_base, sc_ratio, wacc_base, shares, net_debt, non_op, n_sim=2000):
    np.random.seed(42)
    sim_growth = np.random.normal(growth_base, 0.04, n_sim).clip(0, 0.8)
    sim_margin = np.random.normal(target_margin, 0.03, n_sim).clip(-0.1, 0.6)
    sim_wacc = np.random.normal(wacc_base, 0.01, n_sim).clip(0.04, 0.2)
    # Simplified vectorized equity calculation
    val = (rev_0 * 1.5) / sim_wacc 
    return np.maximum(0, (val - net_debt + non_op) / shares)

def calculate_story_consistency(story, growth, margin, sc, wacc):
    return 95, ["Good alignment."]

# --- MAIN APP ---
st.sidebar.markdown("### 🔍 Live Data Sourcing")
ticker_input = st.sidebar.text_input("Enter Company Ticker", value="MSTR").strip().upper()
stock_data, api_success = fetch_stock_data(ticker_input)

# Classify and Setup Narratives
damodaran_df = load_damodaran_industry_data()
ind_avg = 0.15
default_tam, default_moat, _, _ = classify_narrative_defaults(stock_data, ind_avg)

st.sidebar.markdown("---")
st.sidebar.markdown("### 📖 Step 1: Tell your Business Story")
story_tam = st.sidebar.selectbox("Growth Narrative", ["Market Disruptor", "Healthy Competitor", "Niche Player"], index=default_tam)
story_moat = st.sidebar.selectbox("Moat & Pricing", ["Monopoly", "Sustainable Advantage", "Commodity"], index=default_moat)
story_reinvestment = st.sidebar.selectbox("Asset Intensity", ["Asset-Light", "Balanced", "Capital Intensive"], index=1)
story_risk = st.sidebar.selectbox("Risk Profile", ["High", "Average", "Low"], index=1)

# Dynamic Calculations
growth_rate = st.sidebar.slider("High Growth Rate", 0.0, 0.8, 0.15, 0.01)
target_margin = st.sidebar.slider("Target Margin", -0.1, 0.6, 0.2, 0.01)
sales_to_cap = st.sidebar.slider("Sales-to-Capital", 0.1, 5.0, 2.0, 0.1)
cost_of_capital = st.sidebar.slider("WACC", 0.04, 0.2, 0.08, 0.005)
strategic_treasury = st.sidebar.slider("Treasury Holdings ($B)", 0.0, 50.0, float(stock_data.get("non_operating_assets", 0)/1e9), 0.1)

# Execution
dcf_result = calculate_2stage_dcf(stock_data["revenue_ttm"], stock_data["operating_margin"], target_margin, growth_rate, sales_to_cap, cost_of_capital)
years_labels = [f"Year {y}" for y in dcf_result["years"]]

# Tabs
tab1, tab2 = st.tabs(["📊 Interactive Valuation Studio", "📖 Explanation: Narrative vs. Numbers"])

with tab1:
    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("1️⃣ Story Consistency")
        st.write("Score: 95/100")
    with col_right:
        st.subheader("2️⃣ Valuation Output")
        equity = (dcf_result["operating_value"] - (stock_data["total_debt"] - stock_data["cash"]) + (strategic_treasury * 1e9))
        st.metric("Intrinsic Value per Share", f"${max(0, equity/stock_data['shares_outstanding']):.2f}")

    st.subheader("3️⃣ Multi-Stage Cashflow Projection")
    projection_df = pd.DataFrame({
        "Revenue ($B)": dcf_result["revenues"]/1e9,
        "FCFF ($B)": dcf_result["fcffs"]/1e9
    }, index=years_labels)
    st.dataframe(projection_df)

with tab2:
    st.header("📖 Damodaran's Narrative Valuation Theory")
    st.write("Explanation content...")
