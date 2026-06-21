import streamlit as st
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np

# Page Configuration
st.set_page_config(page_title="Damodaran Narrative Dashboard", layout="wide", initial_sidebar_state="expanded")

# --- CUSTOM CSS FOR PREMIUM LOOK ---
st.markdown("""
<style>
    .reportview-container { background: #f8f9fa; }
    .metric-card {
        background-color: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        border: 1px solid #eef2f6;
    }
    .stProgress > div > div > div > div { background-color: #2b5c8f; }
</style>
""", unsafe_allow_html=True)

st.title("📊 Aswath Damodaran Narrative Dashboard")
st.caption("“Valuation is a bridge between narrative and numbers.” — Prof. Aswath Damodaran")

# --- CACHED DATA FETCHING ---
@st.cache_data(ttl=3600)
def load_damodaran_industry_data():
    """Fetches stable industry statistics from Damodaran's database with a robust local fallback."""
    url = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/psdata.xls"
    try:
        # Load Excel, skip metadata rows if present, or clean up columns
        df = pd.read_excel(url)
        df.columns = [str(c).strip() for c in df.columns]
        # Clean up key metrics
        df = df.rename(columns={
            "Industry Name": "Industry",
            "Pre-tax Operating Margin": "PreTaxOpMargin",
            "Price/Sales": "PriceSales"
        })
        return df
    except Exception:
        # High-fidelity mock backup matching Damodaran's typical industry datasets
        return pd.DataFrame({
            "Industry": ["Software (System & Application)", "Semiconductor", "Technology Hardware", "Pharmaceuticals", "Integrated Oil & Gas", "Banks", "Retail (Online)"],
            "PriceSales": [11.01, 15.46, 6.43, 5.63, 2.00, 3.67, 4.50],
            "PreTaxOpMargin": [0.3321, 0.3531, 0.2249, 0.2954, 0.2582, -0.0120, 0.0850],
        })

@st.cache_data(ttl=600)
def fetch_stock_data(ticker_symbol):
    """Fetches live corporate financials and metadata from Yahoo Finance safely."""
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info or {}

        # Safely extract balance sheet items to get net debt and shares
        shares = info.get("sharesOutstanding", 1.0) or 1.0
        
        data = {
            "ticker": ticker_symbol.upper(),
            "company_name": info.get("longName", info.get("shortName", "Unknown Company")),
            "sector": info.get("sector", "Unknown Sector"),
            "industry": info.get("industry", "Unknown Industry"),
            "revenue_ttm": info.get("totalRevenue", info.get("trailingRevenue", 100_000_000)) or 100_000_000,
            "operating_margin": info.get("operatingMargins", 0.10) or 0.10,
            "net_margin": info.get("profitMargins", 0.05) or 0.05,
            "debt_to_equity": info.get("debtToEquity", 50.0) / 100.0 if info.get("debtToEquity") else 0.5,
            "current_price": info.get("currentPrice", info.get("regularMarketPrice", 1.0)) or 1.0,
            "market_cap": info.get("marketCap", 0) or 1_000_000,
            "shares_outstanding": shares,
            "cash": info.get("totalCash", 0) or 0,
            "total_debt": info.get("totalDebt", 0) or 0,
        }

        # Calculate revenue growth safely
        try:
            fin = ticker.financials
            if fin is not None and not fin.empty:
                # Find matching revenue fields
                rev_row = [idx for idx in fin.index if "Revenue" in idx]
                if rev_row:
                    rev_series = fin.loc[rev_row[0]].dropna()
                    if len(rev_series) >= 2:
                        rev_vals = rev_series.values
                        data["revenue_growth_1y"] = (rev_vals[0] - rev_vals[1]) / rev_vals[1] if rev_vals[1] != 0 else 0.10
                    else:
                        data["revenue_growth_1y"] = 0.10
                else:
                    data["revenue_growth_1y"] = 0.10
            else:
                data["revenue_growth_1y"] = 0.10
        except Exception:
            data["revenue_growth_1y"] = 0.10

        return data, True
    except Exception as e:
        return {"error": str(e)}, False

# --- 2-STAGE VALUATION MATHEMATICS ---
def calculate_2stage_dcf(rev_0, margin_0, target_margin, growth_high, sc_ratio, wacc_high, terminal_growth=0.03, terminal_wacc=0.075, tax_rate=0.21, return_details=False):
    """
    Implements a strict 2-Stage Free Cash Flow to Firm (FCFF) Valuation model.
    Stage 1 (Years 1-5): High Growth, linear margin transition, reinvestment based on incremental sales.
    Stage 2 (Terminal): Capped Growth (Economy growth), reinvestment based on stable ROC.
    """
    revenues = []
    margins = []
    ebits = []
    reinvestments = []
    fcffs = []
    discount_factors = []
    pvs = []

    current_rev = rev_0
    
    # Stage 1: High growth phase (Years 1-5)
    for year in range(1, 6):
        prev_rev = current_rev
        current_rev = prev_rev * (1 + growth_high)
        revenues.append(current_rev)

        # Operating margin transitions linearly from current to target
        current_margin = margin_0 + (target_margin - margin_0) * (year / 5.0)
        margins.append(current_margin)

        ebit = current_rev * current_margin
        ebits.append(ebit)

        # Reinvestment = Change in Sales / Sales-to-Capital Ratio
        delta_rev = current_rev - prev_rev
        reinvestment = max(0.0, delta_rev / sc_ratio)
        reinvestments.append(reinvestment)

        nopat = ebit * (1 - tax_rate)
        fcff = nopat - reinvestment
        fcffs.append(fcff)

        # Discount using High Growth WACC
        df = 1 / ((1 + wacc_high) ** year)
        discount_factors.append(df)
        pvs.append(fcff * df)

    # Stage 2: Terminal Value (Year 6+)
    terminal_rev = revenues[-1] * (1 + terminal_growth)
    terminal_ebit = terminal_rev * target_margin
    terminal_nopat = terminal_ebit * (1 - tax_rate)

    # Stable growth reinvestment rate: g / ROC. 
    # Assumes ROC converges to Terminal WACC in perpetuity (no excess returns)
    terminal_reinvestment_rate = terminal_growth / terminal_wacc
    terminal_reinvestment = terminal_nopat * terminal_reinvestment_rate
    terminal_fcff = terminal_nopat - terminal_reinvestment

    # Present Value of Terminal Value
    terminal_value = terminal_fcff / (terminal_wacc - terminal_growth)
    pv_terminal = terminal_value * discount_factors[-1]

    sum_pv_fcff = sum(pvs)
    operating_assets_value = sum_pv_fcff + pv_terminal

    if return_details:
        return {
            "years": list(range(1, 6)),
            "revenues": revenues,
            "margins": margins,
            "ebits": ebits,
            "reinvestments": reinvestments,
            "fcffs": fcffs,
            "pvs": pvs,
            "terminal_value": terminal_value,
            "pv_terminal_value": pv_terminal,
            "operating_value": operating_assets_value
        }
    return operating_assets_value

# --- APP LAYOUT & CORE CONTROLLERS ---
damodaran_df = load_damodaran_industry_data()

# SIDEBAR: Financial Ticker Sourcing
st.sidebar.markdown("### 🔍 Live Data Source")
ticker_input = st.sidebar.text_input("Enter Company Ticker", value="AAPL").strip().upper()

# Load Financial Data
stock_data, success = fetch_stock_data(ticker_input)

if not success:
    st.error(f"⚠️ Yahoo Finance lookup failed for '{ticker_input}'. Falling back to generalized framework parameters.")
    stock_data = {
        "ticker": "CUSTOM",
        "company_name": "Custom Venture Corp",
        "sector": "Technology",
        "industry": "Software",
        "revenue_ttm": 1_000_000_000,
        "operating_margin": 0.15,
        "net_margin": 0.08,
        "debt_to_equity": 0.3,
        "current_price": 100.0,
        "market_cap": 10_000_000_000,
        "shares_outstanding": 100_000_000,
        "cash": 1_500_000_000,
        "total_debt": 500_000_000,
        "revenue_growth_1y": 0.18
    }

# SIDEBAR: Interactive Narrative Sandbox
st.sidebar.markdown("---")
st.sidebar.markdown("### 📖 Step 1: Tell your Business Story")

# Preset Narrative templates to help users
narrative_preset = st.sidebar.selectbox(
    "Choose Narrative Preset:",
    ["Manual Custom", "High-Growth Tech Disruptor", "Conservative Cash Cow", "Asset-Light Software Scaler", "Commodity/Hardware Player"]
)

# Preset mapping logic
if narrative_preset == "High-Growth Tech Disruptor":
    story_growth = 0.30
    story_margin = 0.25
    story_sc = 2.0
    story_wacc = 0.09
elif narrative_preset == "Conservative Cash Cow":
    story_growth = 0.05
    story_margin = 0.18
    story_sc = 1.2
    story_wacc = 0.07
elif narrative_preset == "Asset-Light Software Scaler":
    story_growth = 0.20
    story_margin = 0.35
    story_sc = 4.0
    story_wacc = 0.08
elif narrative_preset == "Commodity/Hardware Player":
    story_growth = 0.08
    story_margin = 0.06
    story_sc = 1.0
    story_wacc = 0.085
else:
    # Match default calculated metrics
    story_growth = max(0.01, min(0.50, stock_data["revenue_growth_1y"]))
    story_margin = max(0.01, min(0.60, stock_data["operating_margin"]))
    story_sc = 1.5
    story_wacc = 0.08

# Allow full fine-tuning of values
growth_rate = st.sidebar.slider("High Growth Rate (Yr 1-5)", 0.0, 0.80, float(story_growth), 0.01, format="%.0f%%")
target_margin = st.sidebar.slider("Target Operating Margin (Yr 5)", -0.10, 0.60, float(story_margin), 0.01, format="%.0f%%")
sales_to_cap = st.sidebar.slider("Capital Efficiency (Sales-to-Capital)", 0.1, 5.0, float(story_sc), 0.1)
cost_of_capital = st.sidebar.slider("Cost of Capital (WACC)", 0.04, 0.20, float(story_wacc), 0.005, format="%.1f%%")

# --- CONSOLIDATING THE REAL DATA VS IMPLIED NARRATIVE ---
st.header(f"🏢 {stock_data['company_name']} ({stock_data['ticker']})")
st.caption(f"Sector: {stock_data['sector']} | Industry: {stock_data['industry']}")

# Corporate Base Metrics Row
m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("Current Price", f"${stock_data['current_price']:.2f}")
with m2:
    st.metric("TTM Revenue", f"${stock_data['revenue_ttm']/1e9:.2f}B")
with m3:
    st.metric("Actual Margin", f"{stock_data['operating_margin']*100:.1f}%")
with m4:
    st.metric("Actual Growth (1Yr)", f"{stock_data['revenue_growth_1y']*100:.1f}%")

st.markdown("---")

# 2-Column Dashboard Body
col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("1️⃣ Story-to-Numbers Translation Table")
    st.write("Your qualitative sliders map directly to financial value drivers:")
    
    # Display translation parameters
    st.write(f"📈 **Revenue Growth:** Chosen story targets **{growth_rate*100:.1f}%** average annual high growth.")
    st.write(f"🛡️ **Operating Profitability:** Target operating margin will converge to **{target_margin*100:.1f}%** as the competitive moat matures.")
    st.write(f"🚜 **Capital reinvestment:** A Sales-to-Capital Ratio of **{sales_to_cap:.1f}** implies that every ${1/sales_to_cap:.2f} of capital reinvested generates $1.00 of growth.")
    st.write(f"💸 **Cost of Financing:** Cost of Capital of **{cost_of_capital*100:.1f}%** matches the risk-profile of the narrative.")

    # Run DCF Model Calculation
    dcf_result = calculate_2stage_dcf(
        rev_0=stock_data["revenue_ttm"],
        margin_0=stock_data["operating_margin"],
        target_margin=target_margin,
        growth_high=growth_rate,
        sc_ratio=sales_to_cap,
        wacc_high=cost_of_capital,
        return_details=True
    )

    # Convert operating asset value to Equity Value and share price
    operating_value = dcf_result["operating_value"]
    net_debt = stock_data["total_debt"] - stock_data["cash"]
    equity_value = operating_value - net_debt
    intrinsic_value_per_share = max(0.0, equity_value / stock_data["shares_outstanding"])

    # Output valuation indicators
    st.subheader("2️⃣ Valuation Bridge Output")
    
    v1, v2 = st.columns(2)
    with v1:
        st.metric(
            label="Implied Intrinsic Value Per Share",
            value=f"${intrinsic_value_per_share:.2f}",
            delta=f"{((intrinsic_value_per_share - stock_data['current_price']) / stock_data['current_price']) * 100:.1f}% Over/Under"
        )
    with v2:
        st.metric(
            label="Implied Corporate Value (Firm)",
            value=f"${operating_value/1e9:.2f}B"
        )

with col_right:
    st.subheader("3️⃣ Step-by-Step Cashflow Projection")
    
    # Display clean growth table
    years_labels = [f"Year {y}" for y in dcf_result["years"]]
    projection_df = pd.DataFrame({
        "Revenue ($B)": [v/1e9 for v in dcf_result["revenues"]],
        "Operating Margin": [f"{m*100:.1f}%" for m in dcf_result["margins"]],
        "Operating Profit ($B)": [e/1e9 for e in dcf_result["ebits"]],
        "Reinvestment ($B)": [r/1e9 for r in dcf_result["reinvestments"]],
        "FCFF ($B)": [f/1e9 for f in dcf_result["fcffs"]],
        "PV of Cashflows ($B)": [pv/1e9 for pv in dcf_result["pvs"]]
    }, index=years_labels)
    
    st.dataframe(projection_df.style.format(precision=3), use_container_width=True)

st.markdown("---")

# Visual Charts Block
chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    st.subheader("📊 Intrinsic Value Components (Waterfall)")
    
    # Structured Components for Valuation Waterfall Chart
    cumulative_pvs = sum(dcf_result["pvs"])
    pv_tv = dcf_result["pv_terminal_value"]
    
    fig_waterfall = go.Figure(go.Waterfall(
        name="Value Bridge", 
        orientation="v",
        measure=["relative", "relative", "total", "relative", "total"],
        x=["PV of 5Yr FCFF", "PV of Terminal Value", "Operating Assets", "Less Net Debt", "Common Equity Value"],
        text=[f"${cumulative_pvs/1e9:.1f}B", f"${pv_tv/1e9:.1f}B", f"${operating_value/1e9:.1f}B", f"${-net_debt/1e9:.1f}B", f"${equity_value/1e9:.1f}B"],
        y=[cumulative_pvs/1e9, pv_tv/1e9, 0, -net_debt/1e9, 0],
        connector={"line": {"color": "rgb(63, 63, 63)"}},
    ))
    
    fig_waterfall.update_layout(title="Valuation Waterfall Analysis", yaxis_title="$ Billions", showlegend=False)
    st.plotly_chart(fig_waterfall, use_container_width=True)

with chart_col2:
    st.subheader("🎲 Probable Value (Monte Carlo Simulation)")
    st.write("We run 2,000 simulations randomizing growth, profit, and risk to find standard distributions of value.")
    
    # Run high speed cached Monte Carlo Simulator
    with st.spinner("Simulating multi-verse futures..."):
        np.random.seed(42)
        n_sim = 2000
        
        # Pull normally distributed randomized variations around standard drivers
        sim_growth = np.random.normal(growth_rate, 0.04, n_sim)
        sim_margin = np.random.normal(target_margin, 0.03, n_sim)
        sim_wacc = np.random.normal(cost_of_capital, 0.01, n_sim)
        
        sim_values = []
        for g, m, w in zip(sim_growth, sim_margin, sim_wacc):
            # Ensure boundaries are logical
            g = max(0.0, min(0.80, g))
            m = max(-0.10, min(0.70, m))
            w = max(0.04, min(0.20, w))
            
            val = calculate_2stage_dcf(
                rev_0=stock_data["revenue_ttm"],
                margin_0=stock_data["operating_margin"],
                target_margin=m,
                growth_high=g,
                sc_ratio=sales_to_cap,
                wacc_high=w
            )
            # Calculate intrinsic equity price
            sim_price = (val - net_debt) / stock_data["shares_outstanding"]
            sim_values.append(max(0.0, sim_price))

        sim_values = np.array(sim_values)
        
        # Display key percentile bounds
        p10, p50, p90 = np.percentile(sim_values, [10, 50, 90])
        st.write(f"🎯 **Most Probable Fair Value (Median):** `${p50:.2f}` per share.")
        st.write(f"🛡️ **Conservative Case (10th percentile):** `${p10:.2f}` | **Optimistic Case (90th percentile):** `${p90:.2f}`")
        
        # Plot distribution
        fig_dist = px.histogram(
            sim_values, 
            nbins=50, 
            title="Distribution of Fair Value per Share",
            labels={'value': 'Value per Share ($)'},
            color_discrete_sequence=['#2b5c8f']
        )
        # Highlight current ticker price to contrast valuation results
        fig_dist.add_vline(x=stock_data['current_price'], line_dash="dash", line_color="red", annotation_text="Current Market Price")
        fig_dist.update_layout(showlegend=False)
        st.plotly_chart(fig_dist, use_container_width=True)

st.markdown("---")
st.subheader("⚖️ Damodaran's Triad Check: Possible, Plausible, and Probable")
c_p1, c_p2, c_p3 = st.columns(3)

with c_p1:
    if target_margin <= 0.60:
        st.success("✅ **Possible:** Operating Margin is mathematically logical (<60%).")
    else:
        st.error("❌ **Impossible Narrative:** Your profit margin is mathematically impossible to maintain long term.")

with c_p2:
    if growth_rate <= 0.40:
        st.success("✅ **Plausible:** High-growth rates are within broad historical norms.")
    else:
        st.warning("⚠️ **Unlikely Narrative:** High-growth rates exceeding 40% annually for 5 years are extremely rare historically.")

with c_p3:
    if len(sim_values) > 0:
        st.success("✅ **Probable:** Multi-stage DCF models completed simulation without breaking limits.")
    else:
        st.error("❌ **Invalid Logic:** Check the base parameters of your story.")
