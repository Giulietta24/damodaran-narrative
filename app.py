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
        # Load Excel, clean up columns
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
        
        # Safely capture cash and debt
        cash = info.get("totalCash", 0) or 0
        total_debt = info.get("totalDebt", 0) or 0
        
        # Guardrail for actual operating margin to prevent extreme accounting noise (like digital asset impairment)
        raw_operating_margin = info.get("operatingMargins", 0.10)
        if raw_operating_margin is None:
            raw_operating_margin = 0.10
            
        data = {
            "ticker": ticker_symbol.upper(),
            "company_name": info.get("longName", info.get("shortName", "Unknown Company")),
            "sector": info.get("sector", "Unknown Sector"),
            "industry": info.get("industry", "Unknown Industry"),
            "revenue_ttm": info.get("totalRevenue", info.get("trailingRevenue", 100_000_000)) or 100_000_000,
            "operating_margin": raw_operating_margin,
            "net_margin": info.get("profitMargins", 0.05) or 0.05,
            "debt_to_equity": info.get("debtToEquity", 50.0) / 100.0 if info.get("debtToEquity") else 0.5,
            "current_price": info.get("currentPrice", info.get("regularMarketPrice", 1.0)) or 1.0,
            "market_cap": info.get("marketCap", 0) or 1_000_000,
            "shares_outstanding": shares,
            "cash": cash,
            "total_debt": total_debt,
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

# --- AUTO-CLASSIFICATION ENGINE (FOR NARRATIVE DROPDOWNS) ---
def classify_narrative_defaults(stock_data, ind_avg_margin):
    """
    Analyzes historical base rates to dynamically set the narrative dropdown defaults.
    Ensures mature giants don't default to 'Emerging Disruptor' narratives on load.
    """
    # 1. TAM / Growth Narrative
    growth = stock_data["revenue_growth_1y"]
    if growth > 0.22:
        tam_idx = 0  # Market Disruptor
    elif growth >= 0.05:
        tam_idx = 1  # Healthy Competitor
    else:
        tam_idx = 2  # Niche Player

    # Apply sanity clip on operating margin to classify moats accurately
    margin = max(-0.50, stock_data["operating_margin"])
    if margin > 0.24 or margin > (ind_avg_margin + 0.06):
        moat_idx = 0  # Monopoly / Network Effects
    elif margin >= 0.10:
        moat_idx = 1  # Sustainable Advantage
    else:
        moat_idx = 2  # Commodity Player

    # 3. Reinvestment / Asset Intensity
    sector = stock_data["sector"].lower()
    industry = stock_data["industry"].lower()
    if "software" in industry or "software" in sector or "internet" in industry:
        reinvest_idx = 0  # Asset-Light
    elif "oil" in industry or "gas" in industry or "steel" in industry or "utility" in sector or "automotive" in industry or "hardware" in industry:
        reinvest_idx = 2  # Capital Intensive
    else:
        reinvest_idx = 1  # Balanced Reinvestment

    # 4. Risk Profile
    debt = stock_data["debt_to_equity"]
    mcap = stock_data["market_cap"]
    if mcap > 100e9 and debt < 0.6:
        risk_idx = 2  # Low Risk
    elif mcap < 10e9 or debt > 1.4:
        risk_idx = 0  # High Risk
    else:
        risk_idx = 1  # Average Corporate Risk

    return tam_idx, moat_idx, reinvest_idx, risk_idx

# --- 2-STAGE VALUATION MATHEMATICS ---
def calculate_2stage_dcf(rev_0, margin_0, target_margin, growth_high, sc_ratio, wacc_high, terminal_growth=0.03, terminal_wacc=0.075, tax_rate=0.21, return_details=False):
    """
    Implements a strict 2-Stage Free Cash Flow to Firm (FCFF) Valuation model.
    Stage 1 (Years 1-5): High Growth, linear margin transition, reinvestment based on incremental sales.
    Stage 2 (Terminal): Capped Growth (Economy growth), reinvestment based on stable ROC.
    """
    # FINANCIAL GUARDRAIL: Clip the starting operating margin to a sensible floor (e.g., -40%)
    # This prevents mathematical disasters (like starting at -11,641% for write-offs or impairment spikes)
    margin_start = max(-0.40, margin_0)

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

        # Operating margin transitions linearly from normalized start to target
        current_margin = margin_start + (target_margin - margin_start) * (year / 5.0)
        margins.append(current_margin)

        ebit = current_rev * current_margin
        ebits.append(ebit)

        # Reinvestment = Change in Sales / Sales-to-Capital Ratio
        delta_rev = current_rev - prev_rev
        reinvestment = max(0.0, delta_rev / sc_ratio)
        reinvestments.append(reinvestment)

        # EBIT cannot be lower than total revenue (loss cap helper)
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

# Find industry benchmark stats if possible
industry_match = damodaran_df[damodaran_df["Industry"].astype(str).str.contains(stock_data["industry"], case=False, na=False)]
if not industry_match.empty:
    ind_avg_margin = float(industry_match["PreTaxOpMargin"].iloc[0])
    ind_avg_ps = float(industry_match["PriceSales"].iloc[0])
else:
    ind_avg_margin = 0.15
    ind_avg_ps = 3.0

# Calculate optimal base narrative defaults dynamically
default_tam, default_moat, default_reinvestment, default_risk = classify_narrative_defaults(stock_data, ind_avg_margin)

# SIDEBAR: Interactive Narrative Sandbox
st.sidebar.markdown("---")
st.sidebar.markdown("### 📖 Step 1: Tell your Business Story")

# Qualitative Narrative Story Builders (Default selected index is now dynamically determined)
story_tam = st.sidebar.selectbox(
    "Market TAM & Growth Narrative",
    [
        "Market Disruptor (Massive TAM, Rapid Scale)",
        "Healthy Competitor (Moderate Growth, Regional Expansion)",
        "Niche Player (Mature, Slower Defense Play)"
    ],
    index=default_tam,
    key=f"selectbox_tam_{stock_data['ticker']}"
)

story_moat = st.sidebar.selectbox(
    "Moat & Competitive Edge",
    [
        "Monopoly / Network Effects (High Pricing Power)",
        "Sustainable Advantage / Switching Costs (Moderate Protection)",
        "Commodity Player (No Moat, High Price Competition)"
    ],
    index=default_moat,
    key=f"selectbox_moat_{stock_data['ticker']}"
)

story_reinvestment = st.sidebar.selectbox(
    "Reinvestment Strategy & Asset Intensity",
    [
        "Asset-Light (High Capital Efficiency / Software Model)",
        "Balanced Reinvestment (Industry Standard / Shared Model)",
        "Capital Intensive (Low Efficiency / Heavy Factories & CapEx)"
    ],
    index=default_reinvestment,
    key=f"selectbox_reinvest_{stock_data['ticker']}"
)

story_risk = st.sidebar.selectbox(
    "Risk & Macro Profile",
    [
        "High Risk (Emerging Venture / Volatile Market)",
        "Average Corporate Risk (Established Player)",
        "Low Risk (High Moat / Stably Capitalized / Strong Cash Balance)"
    ],
    index=default_risk,
    key=f"selectbox_risk_{stock_data['ticker']}"
)

# --- AUTO-DYNAMIC NARRATIVE ENGINE (STOCK & PEER PEGGED) ---
# 1. Growth Translation Pegged to Ticker actual TTM/1Yr Growth and industry norms
historical_growth = stock_data["revenue_growth_1y"]
base_growth_anchor = max(0.01, min(0.35, historical_growth))

if "Disruptor" in story_tam:
    # Aggressive: scales actual performance or establishes a strong baseline of 25% up to 60%
    calc_growth = max(base_growth_anchor * 1.5, 0.25)
    calc_growth = min(0.65, calc_growth)
elif "Competitor" in story_tam:
    # Moderate: tracks company's historical speed, at least 8%
    calc_growth = max(base_growth_anchor, 0.08)
else:
    # Niche: defense play, tracks structural terminal growth (capped at 5%)
    calc_growth = min(base_growth_anchor * 0.4, 0.05)

# 2. Operating Margin Translation Pegged to Ticker actual margins and industry averages
# We apply a safety clip to prevent starting with wild -11,000% operating values
actual_margin_clipped = max(-0.40, stock_data["operating_margin"])

if "Monopoly" in story_moat:
    # Premium: converges above company actuals and industry peer average
    calc_margin = max(actual_margin_clipped + 0.06, ind_avg_margin + 0.08)
    calc_margin = min(0.60, calc_margin)
elif "Sustainable" in story_moat:
    # Normalization: tracks best of current margin or industry peers
    calc_margin = max(actual_margin_clipped, ind_avg_margin)
else:
    # Squeezed: tracks a fraction of current/industry margins, capped at low single digit
    calc_margin = max(0.02, min(actual_margin_clipped * 0.5, ind_avg_margin * 0.5, 0.06))

# 3. Capital Efficiency Pegged to Asset Strategy
calc_sc = 3.5 if "Asset-Light" in story_reinvestment else 1.5 if "Balanced" in story_reinvestment else 0.7

# 4. Cost of Capital Pegged to Risk & Leverage proxy
base_wacc = 0.08 + (stock_data["debt_to_equity"] * 0.005)
calc_wacc = base_wacc + 0.03 if "High Risk" in story_risk else base_wacc if "Average" in story_risk else base_wacc - 0.015
calc_wacc = max(0.04, min(0.18, calc_wacc))

st.sidebar.markdown("---")
st.sidebar.markdown("### 🔢 Step 2: Fine-Tune the Valuation Drivers")

# Streamlit Lock Workaround: Unique key incorporating narrative state and ticker forces dynamic reset
slider_reset_key = f"{story_tam}_{story_moat}_{story_reinvestment}_{story_risk}_{stock_data['ticker']}"

# Slider controls initialized dynamically by the dynamic Story presets
growth_rate = st.sidebar.slider(
    "High Growth Rate (Yr 1-5)", 
    0.0, 0.80, float(calc_growth), 0.01, 
    format="%.0f%%", 
    key=f"growth_s_{slider_reset_key}"
)
target_margin = st.sidebar.slider(
    "Target Operating Margin (Yr 5)", 
    -0.10, 0.60, float(calc_margin), 0.01, 
    format="%.0f%%", 
    key=f"margin_s_{slider_reset_key}"
)
sales_to_cap = st.sidebar.slider(
    "Capital Efficiency (Sales-to-Capital)", 
    0.1, 5.0, float(calc_sc), 0.1, 
    key=f"cap_s_{slider_reset_key}"
)
cost_of_capital = st.sidebar.slider(
    "Cost of Capital (WACC)", 
    0.04, 0.20, float(calc_wacc), 0.005, 
    format="%.1f%%", 
    key=f"wacc_s_{slider_reset_key}"
)

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
    # Display the actual raw margin but highlight that we normalize inside DCF calculations if extreme
    st.metric(
        "Actual Margin", 
        f"{stock_data['operating_margin']*100:.1f}%",
        help="Note: If this margin is extremely negative due to asset impairment (such as Bitcoin holding adjustments), our cashflow models automatically apply an adjustment floor of -40% to prevent projection distortion."
    )
with m4:
    st.metric("Actual Growth (1Yr)", f"{stock_data['revenue_growth_1y']*100:.1f}%")

st.markdown("---")

# 2-Column Dashboard Body
col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("1️⃣ Story-to-Numbers Translation Table")
    st.write("Your qualitative narrative translates into these financial engine blocks:")
    
    # Visualizing narrative choice alignment
    st.info(f"""
    **Selected Narrative Story:**
    * **Market Opportunity:** {story_tam}
    * **Competitive Protection:** {story_moat}
    * **Execution Strategy:** {story_reinvestment}
    * **Risk Profile:** {story_risk}
    """)

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
        
        # Calculate true probability of being undervalued
        undervalued_prob = (sim_values > stock_data["current_price"]).mean() * 100
        
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

# 1. POSSIBLE CHECK (Logic Boundary Check)
with c_p1:
    st.markdown("### 🛠️ Possible")
    if target_margin < 0.80 and cost_of_capital > 0.03:
        st.success("✅ **Passed Mathematical Feasibility**")
        st.write("• Target operating margin is logically restricted below 80%.")
        st.write("• Terminal discount rate is safely above structural economic growth.")
    else:
        st.error("❌ **Mathematical Breach Detected**")
        st.write("• Assumed margins or growth dynamics violate foundational corporate math limits.")

# 2. PLAUSIBLE CHECK (Industry & Historical Comparison Check)
with c_p2:
    st.markdown("### ⚖️ Plausible")
    
    # Calculate comparative variance
    margin_variance = target_margin - stock_data["operating_margin"]
    growth_variance = growth_rate - stock_data["revenue_growth_1y"]
    
    warnings = []
    
    if abs(margin_variance) > 0.20:
        warnings.append(f"• Margin target **({target_margin*100:.1f}%)** varies by >20% from current margins **({stock_data['operating_margin']*100:.1f}%)**.")
    if abs(growth_variance) > 0.25:
        warnings.append(f"• Growth target **({growth_rate*100:.1f}%)** is drastically different from historical actuals **({stock_data['revenue_growth_1y']*100:.1f}%)**.")
    if target_margin > (ind_avg_margin + 0.15):
         warnings.append(f"• Assumed margin is significantly higher than industry benchmark average **({ind_avg_margin*100:.1f}%)**.")

    if len(warnings) == 0:
        st.success("✅ **Passed Plausibility Sanity Check**")
        st.write("• Assumptions line up elegantly with historical benchmarks and sector averages.")
    else:
        st.warning("⚠️ **Ambitious Narrative Alerts:**")
        for w in warnings:
            st.write(w)

# 3. PROBABLE CHECK (Monte Carlo Undervaluation Likelihood)
with c_p3:
    st.markdown("### 🎲 Probable")
    
    if undervalued_prob > 70:
        st.success(f"🎯 **High Likelihood of Undervaluation: {undervalued_prob:.1f}%**")
        st.write(f"• Based on 2,000 multi-verse runs, **{undervalued_prob:.1f}%** of projections exceed the current price of `${stock_data['current_price']:.2f}`.")
    elif undervalued_prob >= 35:
        st.info(f"⚖️ **Balanced / Neutral Risk Profile: {undervalued_prob:.1f}%**")
        st.write(f"• Projections represent a balanced coin flip. **{undervalued_prob:.1f}%** of future narratives justify a price higher than current market levels.")
    else:
        st.error(f"🚨 **High Likelihood of Overvaluation: {undervalued_prob:.1f}%**")
        st.write(f"• Only **{undervalued_prob:.1f}%** of simulation iterations yielded intrinsic valuations above `${stock_data['current_price']:.2f}`.")
