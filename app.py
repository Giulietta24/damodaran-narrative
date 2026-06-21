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
        df = pd.read_excel(BytesIO(url.encode()), header=9)
        df.columns = ['Industry', 'NumFirms', 'PriceSales', 'NetMargin', 'EVSales', 'PreTaxOpMargin']
        return df
    except:
        return pd.DataFrame({
            'Industry': ['Software', 'Semiconductor', 'Computers', 'Pharmaceutical', 'Oil/Gas', 'Banks'],
            'NumFirms': [309, 66, 36, 228, 142, 568],
            'PriceSales': [11.01, 15.46, 6.43, 5.63, 2.00, 3.67],
            'NetMargin': [25.49, 30.45, 17.78, 18.54, 14.63, 27.49],
            'EVSales': [11.41, 15.70, 6.63, 6.24, 2.68, 4.28],
            'PreTaxOpMargin': [33.21, 35.31, 22.49, 29.54, 25.82, -0.12]
        })

def fetch_stock_data(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        data = {
            'ticker': ticker_symbol,
            'company_name': info.get('longName', 'Unknown'),
            'sector': info.get('sector', 'Unknown'),
            'industry': info.get('industry', 'Unknown'),
            'revenue': info.get('totalRevenue', 0),
            'revenue_ttm': info.get('trailingRevenue', 0),
            'operating_margin': info.get('operatingMargins', 0),
            'net_margin': info.get('profitMargins', 0),
            'roe': info.get('returnOnEquity', 0),
            'roic': info.get('returnOnCapital', 0),
            'debt_to_equity': info.get('debtToEquity', 0),
            'current_price': info.get('currentPrice', info.get('regularMarketPrice', 0)),
            'market_cap': info.get('marketCap', 0),
        }
        try:
            FinancialData = ticker.financials
            if FinancialData is not None and len(FinancialData.columns) > 1:
                revenues = FinancialData.loc['Total Revenue'].values
                data['revenue_growth_1y'] = (revenues[0] - revenues[1]) / revenues[1] if len(revenues) >= 2 else 0
            else:
                data['revenue_growth_1y'] = 0
        except:
            data['revenue_growth_1y'] = 0
        return data, True
    except Exception as e:
        return {'error': str(e)}, False

def auto_narrative_from_data(stock_data, damodaran_df):
    if 'error' in stock_data:
        return None
    revenue_growth = stock_data['revenue_growth_1y']
    tam_type = "Massive & Evolving" if revenue_growth > 0.15 else "Fixed & Mature" if revenue_growth < 0.03 else "Moderate Growth"
    moat_options = []
    moat_strength = "Weak"
    if stock_data['operating_margin'] > 0.25:
        moat_options.append("Brand Loyalty")
        moat_strength = "Strong"
    if stock_data['roic'] > 0.20:
        moat_options.append("High Switching Costs")
        moat_strength = "Strong"
    execution_plan = "Asset-light (Software/Licensing)" if stock_data['debt_to_equity'] < 0.5 else "Asset-heavy (CapEx)"
    return {'tam_type': tam_type, 'moat_strength': moat_strength, 'moat_options': moat_options, 
            'execution_plan': execution_plan, 'sector': stock_data['sector'], 'industry': stock_data['industry']}

def auto_map_to_drivers(stock_data, narrative, damodaran_df):
    if 'error' in stock_data:
        return None
    industry_row = damodaran_df[damodaran_df['Industry'] == narrative['industry']]
    industry_margin = industry_row['PreTaxOpMargin'].values[0] / 100 if len(industry_row) > 0 else 0.15
    tam_growth = 0.12 if narrative['tam_type'] == "Massive & Evolving" else 0.03 if narrative['tam_type'] == "Fixed & Mature" else 0.07
    return {
        'revenue_growth': (stock_data['revenue_growth_1y'] + tam_growth) / 2,
        'op_margin': (stock_data['operating_margin'] + industry_margin) / 2,
        'sc_ratio': 8.0 if narrative['execution_plan'] == "Asset-light" else 3.0,
        'wacc': 0.07 + (0.02 if narrative['moat_strength'] == "Strong" else 0.05) + (stock_data['debt_to_equity'] * 0.01),
        'industry_ps': industry_row['PriceSales'].values[0] if len(industry_row) > 0 else 3.0
    }

st.title("📊 Dynamic Damodaran Narrative Dashboard")
st.subheader("Auto-pulls real-time stock data + Damodaran industry baselines")

st.sidebar.header("🔍 Company Selector")
ticker_input = st.sidebar.text_input("Enter Ticker (e.g., AAPL, MSFT, TSLA)", value="AAPL")

damodaran_df = load_damodaran_industry_data()
stock_data, success = fetch_stock_data(ticker_input)

if not success:
    st.error(f"❌ Could not fetch data for {ticker_input}")
    st.stop()

narrative = auto_narrative_from_data(stock_data, damodaran_df)
drivers = auto_map_to_drivers(stock_data, narrative, damodaran_df)

st.header("🏢 Company Overview (Live)")
col1, col2, col3 = st.columns(3)
col1.metric("Company", stock_data['company_name'])
col1.metric("Sector", stock_data['sector'])
col2.metric("Price", f"${stock_data['current_price']:.2f}")
col2.metric("Market Cap", f"${stock_data['market_cap']/1e9:.2f}B")
col3.metric("Revenue", f"${stock_data['revenue_ttm']/1e9:.2f}B")
col3.metric("1Y Growth", f"{stock_data['revenue_growth_1y']*100:.1f}%")

st.header("1️⃣ Auto Narrative")
col1, col2, col3 = st.columns(3)
col1.write(f"**TAM:** {narrative['tam_type']}")
col2.write(f"**Moat:** {narrative['moat_strength']} ({', '.join(narrative['moat_options'])})")
col3.write(f"**Execution:** {narrative['execution_plan']}")

st.header("2️⃣ Value Drivers")
col1, col2 = st.columns(2)
col1.write(f"**Growth:** {drivers['revenue_growth']*100:.1f}%")
col1.progress(drivers['revenue_growth'])
col2.write(f"**Margin:** {drivers['op_margin']*100:.1f}%")
col2.progress(drivers['op_margin'])
col1, col2, col3 = st.columns(3)
col1.metric("S/C Ratio", f"{drivers['sc_ratio']:.1f}")
col2.metric("WACC", f"{drivers['wacc']*100:.1f}%")
col3.metric("P/S", f"{drivers['industry_ps']:.2f}")

st.header("3️⃣ Sanity Check")
st.success("✅ Possible" if drivers['op_margin'] <= 1.0 else "❌ Possible")
st.success("✅ Plausible" if drivers['revenue_growth'] <= 0.5 else "⚠️ Plausible")

n_sim = 10000
np.random.seed(42)
growth_sim = np.random.normal(drivers['revenue_growth'], 0.05, n_sim)
margin_sim = np.random.normal(drivers['op_margin'], 0.02, n_sim)
wacc_sim = np.random.normal(drivers['wacc'], 0.01, n_sim)
value_sim = (stock_data['revenue_ttm'] * margin_sim * (1 - 1/drivers['sc_ratio'])) / (wacc_sim - growth_sim)
value_sim = value_sim[(wacc_sim > growth_sim) & (value_sim > 0)]
prob_60 = np.percentile(value_sim, 20), np.percentile(value_sim, 80)
st.write(f"60% Range: **${prob_60[0]/1e9:.2f}B – ${prob_60[1]/1e9:.2f}B**")

fig_dist = px.histogram(value_sim, nbins=50, title="Monte Carlo Distribution")
fig_dist.update_layout(xaxis_title="Value ($M)", yaxis_title="Frequency", height=400)
st.plotly_chart(fig_dist, use_container_width=True)

st.header("4️⃣ Valuation Waterfall")
op_income = stock_data['revenue_ttm'] * drivers['op_margin']
reinvest = op_income / drivers['sc_ratio']
fcff = op_income - reinvest
value = fcff / (drivers['wacc'] - drivers['revenue_growth'])
fig_water = go.Figure(go.Bar(
    x=["Revenue", "Op Inc", "Reinvest", "FCFF", "Value"],
    y=[stock_data['revenue_ttm']/1e9, op_income/1e9, reinvest/1e9, fcff/1e9, value/1e9],
    text=[f"${v:.2f}B" for v in [stock_data['revenue_ttm']/1e9, op_income/1e9, reinvest/1e9, fcff/1e9, value/1e9]],
    textposition="auto"))
fig_water.update_layout(title="Waterfall", xaxis_title="Stage", yaxis_title="$B", height=400)
st.plotly_chart(fig_water, use_container_width=True)
