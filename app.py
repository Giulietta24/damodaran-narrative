# narrative_dashboard_dynamic.py

import streamlit as st
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from io import BytesIO

st.set_page_config(page_title="Dynamic Damodaran Dashboard", layout="wide")

def load_damodaran_industry_data():
    url = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/psdata.xls"
    try:
        df = pd.read_excel(url)
        df.columns = [str(c).strip() for c in df.columns]
        return df
    except Exception:
        return pd.DataFrame({
            "Industry": ["Software", "Semiconductor", "Computers", "Pharmaceutical", "Oil/Gas", "Banks"],
            "PriceSales": [11.01, 15.46, 6.43, 5.63, 2.00, 3.67],
            "PreTaxOpMargin": [33.21, 35.31, 22.49, 29.54, 25.82, -0.12],
        })

def fetch_stock_data(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info or {}

        data = {
            "ticker": ticker_symbol.upper(),
            "company_name": info.get("longName", "Unknown"),
            "sector": info.get("sector", "Unknown"),
            "industry": info.get("industry", "Unknown"),
            "revenue_ttm": info.get("trailingRevenue", info.get("totalRevenue", 0)) or 0,
            "operating_margin": info.get("operatingMargins", 0) or 0,
            "net_margin": info.get("profitMargins", 0) or 0,
            "roe": info.get("returnOnEquity", 0) or 0,
            "roic": info.get("returnOnCapital", 0) or 0,
            "debt_to_equity": info.get("debtToEquity", 0) or 0,
            "current_price": info.get("currentPrice", info.get("regularMarketPrice", 0)) or 0,
            "market_cap": info.get("marketCap", 0) or 0,
        }

        try:
            fin = ticker.financials
            if fin is not None and "Total Revenue" in fin.index and fin.shape[1] >= 2:
                rev = fin.loc["Total Revenue"].dropna().values
                data["revenue_growth_1y"] = ((rev[0] - rev[1]) / rev[1]) if len(rev) >= 2 and rev[1] != 0 else 0
            else:
                data["revenue_growth_1y"] = 0
        except Exception:
            data["revenue_growth_1y"] = 0

        return data, True
    except Exception as e:
        return {"error": str(e)}, False

def auto_narrative_from_data(stock_data):
    revenue_growth = stock_data["revenue_growth_1y"]
    tam_type = "Massive & Evolving" if revenue_growth > 0.15 else "Fixed & Mature" if revenue_growth < 0.03 else "Moderate Growth"

    moat_options = []
    moat_strength = "Weak"
    if stock_data["operating_margin"] > 0.25:
        moat_options.append("Brand Loyalty")
        moat_strength = "Strong"
    if stock_data["roic"] > 0.20:
        moat_options.append("High Switching Costs")
        moat_strength = "Strong"
    if stock_data["net_margin"] > 0.20:
        moat_options.append("Cost Leadership")

    execution_plan = "Asset-light (Software/Licensing)" if stock_data["debt_to_equity"] < 0.5 else "Asset-heavy (CapEx)"

    return {
        "tam_type": tam_type,
        "moat_strength": moat_strength,
        "moat_options": moat_options,
        "execution_plan": execution_plan,
    }

def auto_map_to_drivers(stock_data, narrative, damodaran_df):
    ind = str(stock_data["industry"]).strip()
    industry_row = pd.DataFrame()

    if "Industry" in damodaran_df.columns:
        industry_row = damodaran_df[damodaran_df["Industry"].astype(str).str.contains(ind, case=False, na=False)]

    industry_margin = float(industry_row["PreTaxOpMargin"].iloc[0]) / 100 if len(industry_row) > 0 and "PreTaxOpMargin" in industry_row.columns else 0.15
    industry_ps = float(industry_row["PriceSales"].iloc[0]) if len(industry_row) > 0 and "PriceSales" in industry_row.columns else 3.0

    tam_growth = 0.12 if narrative["tam_type"] == "Massive & Evolving" else 0.03 if narrative["tam_type"] == "Fixed & Mature" else 0.07
    asset_light = "Asset-light" in narrative["execution_plan"]

    return {
        "revenue_growth": max(0.0, min(0.60, (stock_data["revenue_growth_1y"] + tam_growth) / 2)),
        "op_margin": max(-0.20, min(0.80, (stock_data["operating_margin"] + industry_margin) / 2)),
        "sc_ratio": 8.0 if asset_light else 3.0,
        "wacc": max(0.03, min(0.20, 0.07 + (0.02 if narrative["moat_strength"] == "Strong" else 0.05) + (stock_data["debt_to_equity"] * 0.001))),
        "industry_ps": industry_ps,
    }

def monte_carlo_valuation(stock_data, drivers, n_sim=10000, seed=42):
    np.random.seed(seed)

    growth_sim = np.random.normal(drivers["revenue_growth"], 0.03, n_sim)
    margin_sim = np.random.normal(drivers["op_margin"], 0.02, n_sim)
    wacc_sim = np.random.normal(drivers["wacc"], 0.01, n_sim)

    valid = np.isfinite(growth_sim) & np.isfinite(margin_sim) & np.isfinite(wacc_sim)
    valid &= (margin_sim > -0.5) & (margin_sim < 1.0)
    valid &= (growth_sim > -0.5) & (growth_sim < 1.0)
    valid &= (wacc_sim > growth_sim + 0.005)

    growth_sim = growth_sim[valid]
    margin_sim = margin_sim[valid]
    wacc_sim = wacc_sim[valid]

    if len(growth_sim) < 50:
        return np.array([])

    denom = wacc_sim - growth_sim
    denom = np.where(np.abs(denom) < 0.005, np.nan, denom)

    fcff = stock_data["revenue_ttm"] * margin_sim * (1 - 1 / drivers["sc_ratio"])
    value_sim = fcff / denom
    value_sim = value_sim[np.isfinite(value_sim) & (value_sim > 0)]

    return value_sim

st.title("📊 Dynamic Damodaran Narrative Dashboard")
st.subheader("Auto-pulls live company data and industry baselines")

st.sidebar.header("🔍 Company Selector")
ticker_input = st.sidebar.text_input("Enter Ticker", value="AAPL")

damodaran_df = load_damodaran_industry_data()
stock_data, success = fetch_stock_data(ticker_input)

if not success:
    st.error(f"Could not fetch data for {ticker_input}: {stock_data.get('error', 'Unknown error')}")
    st.stop()

narrative = auto_narrative_from_data(stock_data)
drivers = auto_map_to_drivers(stock_data, narrative, damodaran_df)

st.header("🏢 Company Overview")
c1, c2, c3 = st.columns(3)
c1.metric("Company", stock_data["company_name"])
c1.metric("Sector", stock_data["sector"])
c2.metric("Price", f"${stock_data['current_price']:.2f}")
c2.metric("Market Cap", f"${stock_data['market_cap']/1e9:.2f}B")
c3.metric("Revenue TTM", f"${stock_data['revenue_ttm']/1e9:.2f}B")
c3.metric("1Y Revenue Growth", f"{stock_data['revenue_growth_1y']*100:.1f}%")

st.header("1️⃣ Auto Narrative")
c1, c2, c3 = st.columns(3)
c1.write(f"**TAM:** {narrative['tam_type']}")
c2.write(f"**Moat:** {narrative['moat_strength']}")
c2.write(f"Moats: {', '.join(narrative['moat_options']) if narrative['moat_options'] else 'None detected'}")
c3.write(f"**Execution:** {narrative['execution_plan']}")

st.header("2️⃣ Value Drivers")
c1, c2 = st.columns(2)
c1.write(f"**Revenue Growth:** {drivers['revenue_growth']*100:.1f}%")
c1.progress(float(min(max(drivers["revenue_growth"], 0), 1)))
c2.write(f"**Target Operating Margin:** {drivers['op_margin']*100:.1f}%")
c2.progress(float(min(max(drivers["op_margin"], 0), 1)))

c1, c2, c3 = st.columns(3)
c1.metric("Sales-to-Capital", f"{drivers['sc_ratio']:.1f}")
c2.metric("WACC", f"{drivers['wacc']*100:.1f}%")
c3.metric("Industry P/S", f"{drivers['industry_ps']:.2f}")

st.header("3️⃣ Sanity Check")
if drivers["op_margin"] <= 1.0:
    st.success("✅ Possible: margin within bounds")
else:
    st.error("❌ Possible: operating margin cannot exceed 100%")

if drivers["revenue_growth"] <= 0.5:
    st.success("✅ Plausible: growth within broad historical norms")
else:
    st.warning("⚠️ Plausible: very high growth for long periods is rare")

value_sim = monte_carlo_valuation(stock_data, drivers)

st.subheader("Probable: Monte Carlo Valuation")
if len(value_sim) < 10:
    st.warning("Too few valid simulations. Try a different ticker or wider assumption ranges.")
else:
    p20, p80 = np.nanpercentile(value_sim, [20, 80])
    st.write(f"60% Range: **${p20/1e9:.2f}B – ${p80/1e9:.2f}B**")

    fig_dist = px.histogram(value_sim, nbins=50, title="Monte Carlo Valuation Distribution")
    fig_dist.update_xaxes(title_text="Intrinsic Value ($)")
    fig_dist.update_yaxes(title_text="Frequency")
    st.plotly_chart(fig_dist, use_container_width=True)

st.header("4️⃣ Valuation Waterfall")
op_income = stock_data["revenue_ttm"] * drivers["op_margin"]
reinvest = op_income / drivers["sc_ratio"]
fcff = op_income - reinvest

if drivers["wacc"] <= drivers["revenue_growth"] + 0.005:
    st.warning("Discount rate too close to growth. Waterfall valuation is unstable.")
else:
    value = fcff / (drivers["wacc"] - drivers["revenue_growth"])
    fig_water = go.Figure(go.Bar(
        x=["Revenue", "Op Income", "Reinvestment", "FCFF", "Value"],
        y=[stock_data["revenue_ttm"]/1e9, op_income/1e9, reinvest/1e9, fcff/1e9, value/1e9],
        text=[f"${v:.2f}B" for v in [stock_data["revenue_ttm"]/1e9, op_income/1e9, reinvest/1e9, fcff/1e9, value/1e9]],
        textposition="auto"
    ))
    fig_water.update_layout(title="Valuation Waterfall", xaxis_title="Stage", yaxis_title="$B")
    st.plotly_chart(fig_water, use_container_width=True)

st.header("5️⃣ Historical Revenue")
try:
    fin = yf.Ticker(ticker_input).financials
    if fin is not None and "Total Revenue" in fin.index:
        rev = fin.loc["Total Revenue"].dropna().sort_index()
        if len(rev) >= 2:
            growth = rev.pct_change().dropna() * 100
            if len(growth) > 0:
                fig_hist = px.bar(x=growth.index.astype(str), y=growth.values, title="Annual Revenue Growth")
                fig_hist.update_xaxes(title_text="Year")
                fig_hist.update_yaxes(title_text="Growth %")
                st.plotly_chart(fig_hist, use_container_width=True)
            else:
                st.info("Not enough historical revenue points.")
        else:
            st.info("Not enough historical revenue points.")
    else:
        st.info("No historical revenue data available.")
except Exception:
    st.info("Could not fetch historical revenue data.")
