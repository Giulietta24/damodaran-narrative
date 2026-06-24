import streamlit as st
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np

st.set_page_config(
    page_title="Damodaran Narrative Valuation Studio",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
.metric-card {
    background-color: white;
    padding: 22px;
    border-radius: 12px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.03);
    border: 1px solid #eef2f6;
}
.metric-title {
    font-size: 13px;
    text-transform: uppercase;
    color: #64748b;
    font-weight: 600;
    letter-spacing: 0.5px;
}
.metric-value {
    font-size: 28px;
    font-weight: 700;
    color: #0f172a;
}
.warning-box {
    background-color: #fef3c7;
    border-left: 4px solid #d97706;
    color: #92400e;
    padding: 14px 16px;
    border-radius: 8px;
    margin: 12px 0;
}
.success-box {
    background-color: #f0fdf4;
    border-left: 4px solid #16a34a;
    color: #166534;
    padding: 14px 16px;
    border-radius: 8px;
    margin: 12px 0;
}
.info-box {
    background-color: #f0f9ff;
    border-left: 4px solid #0284c7;
    color: #075985;
    padding: 14px 16px;
    border-radius: 8px;
    margin: 12px 0;
}
.score-card {
    text-align: center;
    background: linear-gradient(135deg, #1e293b, #0f172a);
    color: white;
    padding: 22px;
    border-radius: 12px;
    box-shadow: 0 4px 20px rgba(15,23,42,0.15);
}
.small-note {
    font-size: 12px;
    color: #64748b;
}
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=3600)
def load_damodaran_industry_data():
    url = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/psdata.xls"
    try:
        df = pd.read_excel(url)
        df.columns = [str(c).strip() for c in df.columns]
        rename_map = {
            "Industry Name": "Industry",
            "Pre-tax Operating Margin": "PreTaxOpMargin",
            "Price/Sales": "PriceSales",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
        if "Industry" not in df.columns:
            raise ValueError("Missing Industry column")
        if "PreTaxOpMargin" not in df.columns:
            raise ValueError("Missing PreTaxOpMargin column")
        if "PriceSales" not in df.columns:
            raise ValueError("Missing PriceSales column")
        df["PreTaxOpMargin"] = pd.to_numeric(df["PreTaxOpMargin"], errors="coerce")
        df["PriceSales"] = pd.to_numeric(df["PriceSales"], errors="coerce")
        return df.dropna(subset=["Industry"])
    except Exception:
        return pd.DataFrame({
            "Industry": [
                "Software (System & Application)",
                "Semiconductor",
                "Technology Hardware",
                "Pharmaceuticals",
                "Integrated Oil & Gas",
                "Banks",
                "Retail (Online)",
                "Automotive",
                "Telecom Services",
                "Healthcare Products",
                "Financial Svcs. (Non-bank)",
                "Insurance",
                "Entertainment",
            ],
            "PriceSales": [11.01, 15.46, 6.43, 5.63, 2.00, 3.67, 4.50, 1.25, 2.10, 4.80, 3.20, 3.50, 5.00],
            "PreTaxOpMargin": [0.3321, 0.3531, 0.2249, 0.2954, 0.2582, 0.1250, 0.0850, 0.0720, 0.1850, 0.2100, 0.2200, 0.1500, 0.1800],
        })


FUNDAMENTAL_OVERRIDE_TICKERS = {"MSTR", "COIN", "HOOD", "SMLR", "BTBT"}


@st.cache_data(ttl=60)
def fetch_stock_data(ticker_symbol):
    ticker_symbol = ticker_symbol.upper().strip()

    profiles = {
        "AAPL": {
            "company_name": "Apple Inc.",
            "sector": "Technology",
            "industry": "Technology Hardware",
            "revenue_ttm": 391_000_000_000,
            "operating_margin": 0.307,
            "net_margin": 0.263,
            "debt_to_equity": 1.45,
            "current_price": 213.0,
            "market_cap": 3_270_000_000_000,
            "shares_outstanding": 15_330_000_000,
            "cash": 73_000_000_000,
            "total_debt": 108_000_000_000,
            "revenue_growth_1y": 0.02,
            "non_operating_assets": 158_000_000_000,
            "price_as_of": "Jun 2025",
            "data_source": "fallback",
            "override_note": "",
        },
        "TSLA": {
            "company_name": "Tesla Inc.",
            "sector": "Automotive",
            "industry": "Automotive",
            "revenue_ttm": 96_000_000_000,
            "operating_margin": 0.075,
            "net_margin": 0.055,
            "debt_to_equity": 0.10,
            "current_price": 248.0,
            "market_cap": 795_000_000_000,
            "shares_outstanding": 3_200_000_000,
            "cash": 26_800_000_000,
            "total_debt": 9_500_000_000,
            "revenue_growth_1y": 0.01,
            "non_operating_assets": 5_400_000_000,
            "price_as_of": "Jun 2025",
            "data_source": "fallback",
            "override_note": "",
        },
        "MSTR": {
            "company_name": "Strategy Inc. (MSTR)",
            "sector": "Technology",
            "industry": "Software (System & Application)",
            "revenue_ttm": 463_000_000,
            "operating_margin": 0.08,
            "net_margin": 0.05,
            "debt_to_equity": 3.2,
            "current_price": 385.0,
            "market_cap": 75_000_000_000,
            "shares_outstanding": 195_000_000,
            "cash": 50_000_000,
            "total_debt": 8_200_000_000,
            "revenue_growth_1y": -0.05,
            "non_operating_assets": 42_000_000_000,
            "price_as_of": "Jun 2025",
            "data_source": "fallback",
            "override_note": "Fundamentals use curated profile; reported P&L is distorted by Bitcoin mark-to-market.",
        },
        "NVDA": {
            "company_name": "NVIDIA Corp.",
            "sector": "Technology",
            "industry": "Semiconductor",
            "revenue_ttm": 130_000_000_000,
            "operating_margin": 0.62,
            "net_margin": 0.55,
            "debt_to_equity": 0.20,
            "current_price": 131.0,
            "market_cap": 3_210_000_000_000,
            "shares_outstanding": 24_500_000_000,
            "cash": 25_000_000_000,
            "total_debt": 11_000_000_000,
            "revenue_growth_1y": 1.22,
            "non_operating_assets": 15_000_000_000,
            "price_as_of": "Jun 2025",
            "data_source": "fallback",
            "override_note": "",
        },
        "COIN": {
            "company_name": "Coinbase Global Inc.",
            "sector": "Financial Services",
            "industry": "Financial Svcs. (Non-bank)",
            "revenue_ttm": 6_600_000_000,
            "operating_margin": 0.22,
            "net_margin": 0.18,
            "debt_to_equity": 0.45,
            "current_price": 260.0,
            "market_cap": 66_000_000_000,
            "shares_outstanding": 254_000_000,
            "cash": 7_200_000_000,
            "total_debt": 4_200_000_000,
            "revenue_growth_1y": 1.10,
            "non_operating_assets": 1_200_000_000,
            "price_as_of": "Jun 2025",
            "data_source": "fallback",
            "override_note": "Fundamentals use curated profile; reported P&L can be distorted by crypto asset gains/losses.",
        },
    }

    def _sanitize_ratio(value, fallback, low=-2.0, high=2.0):
        if isinstance(value, (int, float)) and low <= float(value) <= high:
            return float(value)
        return fallback

    def _sanitize_growth(value, fallback):
        if isinstance(value, (int, float)) and -0.90 <= float(value) <= 3.0:
            return float(value)
        return fallback

    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info or {}
        live_price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
        if live_price is None:
            raise ValueError("No live price available")

        if ticker_symbol in FUNDAMENTAL_OVERRIDE_TICKERS and ticker_symbol in profiles:
            p = profiles[ticker_symbol].copy()
            p["current_price"] = float(live_price)
            p["market_cap"] = p["shares_outstanding"] * float(live_price)
            p["price_as_of"] = "live"
            p["data_source"] = "live_price_fundamental_override"
            return p, True

        shares = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding") or 0
        cash = info.get("totalCash") or 0.0
        debt = info.get("totalDebt") or 0.0
        dtoe = info.get("debtToEquity")

        profile_base = profiles.get(ticker_symbol, {})
        operating_margin = _sanitize_ratio(info.get("operatingMargins"), profile_base.get("operating_margin", 0.12), -0.40, 0.80)
        net_margin = _sanitize_ratio(info.get("profitMargins"), profile_base.get("net_margin", 0.08), -0.60, 0.80)

        rev_growth = None
        try:
            fin = ticker.financials
            if fin is not None and not fin.empty:
                revenue_rows = [idx for idx in fin.index if any(x in str(idx).lower() for x in ["revenue", "sales", "turnover"])]
                if revenue_rows:
                    rev_series = fin.loc[revenue_rows[0]].dropna()
                    if len(rev_series) >= 2 and rev_series.iloc[1] != 0:
                        rev_growth = float((rev_series.iloc[0] - rev_series.iloc[1]) / rev_series.iloc[1])
        except Exception:
            pass

        if rev_growth is None:
            rev_growth = _sanitize_growth(info.get("revenueGrowth"), profile_base.get("revenue_growth_1y", 0.10))
        else:
            rev_growth = _sanitize_growth(rev_growth, profile_base.get("revenue_growth_1y", 0.10))

        non_op = 0.0
        try:
            balance = ticker.balance_sheet
            if balance is not None and not balance.empty:
                for col in ["Long Term Investments", "Other Long Term Assets", "Other Current Assets", "Other Non Current Assets"]:
                    if col in balance.index:
                        series = balance.loc[col].dropna()
                        if not series.empty:
                            non_op = max(non_op, float(series.iloc[0]))
        except Exception:
            pass

        data = {
            "ticker": ticker_symbol,
            "company_name": info.get("longName", info.get("shortName", profile_base.get("company_name", f"{ticker_symbol} Corp"))),
            "sector": info.get("sector", profile_base.get("sector", "Other")),
            "industry": info.get("industry", profile_base.get("industry", "Other")),
            "revenue_ttm": info.get("totalRevenue") or info.get("trailingRevenue") or profile_base.get("revenue_ttm", 1_000_000_000),
            "operating_margin": operating_margin,
            "net_margin": net_margin,
            "debt_to_equity": (float(dtoe) / 100.0) if isinstance(dtoe, (int, float)) else profile_base.get("debt_to_equity", 0.5),
            "current_price": float(live_price),
            "market_cap": info.get("marketCap") or (shares * float(live_price) if shares else profile_base.get("market_cap", 0)),
            "shares_outstanding": shares if shares else profile_base.get("shares_outstanding", 10_000_000),
            "cash": cash if cash > 0 else profile_base.get("cash", 0.0),
            "total_debt": debt if debt > 0 else profile_base.get("total_debt", 0.0),
            "revenue_growth_1y": rev_growth,
            "non_operating_assets": non_op if non_op > 0 else profile_base.get("non_operating_assets", 0.0),
            "price_as_of": "live",
            "data_source": "live",
            "override_note": profile_base.get("override_note", ""),
        }
        return data, True

    except Exception:
        if ticker_symbol in profiles:
            p = profiles[ticker_symbol].copy()
            p["ticker"] = ticker_symbol
            p["market_cap"] = p["shares_outstanding"] * p["current_price"]
            return p, True

        generic = {
            "ticker": ticker_symbol,
            "company_name": f"{ticker_symbol} Enterprise",
            "sector": "Industrial Tech",
            "industry": "Software (System & Application)",
            "revenue_ttm": 1_200_000_000,
            "operating_margin": 0.14,
            "net_margin": 0.09,
            "debt_to_equity": 0.40,
            "current_price": 50.0,
            "market_cap": 5_000_000_000,
            "shares_outstanding": 100_000_000,
            "cash": 300_000_000,
            "total_debt": 150_000_000,
            "revenue_growth_1y": 0.12,
            "non_operating_assets": 50_000_000,
            "price_as_of": "demo",
            "data_source": "demo",
            "override_note": "",
        }
        return generic, False


def classify_narrative_defaults(stock_data, ind_avg_margin):
    g = float(stock_data["revenue_growth_1y"])
    m = float(stock_data["operating_margin"])
    ind = str(stock_data["industry"]).lower()
    mcap = float(stock_data["market_cap"])
    de = float(stock_data["debt_to_equity"])

    tam_idx = 0 if g > 0.25 else 1 if g >= 0.06 else 2
    moat_idx = 0 if (m > 0.25 or m > (ind_avg_margin + 0.05)) else 1 if m >= 0.10 else 2
    reinvest_idx = 0 if ("software" in ind or "internet" in ind or "service" in ind) else 2 if any(x in ind for x in ["automotive", "hardware", "manufacturing", "oil"]) else 1
    risk_idx = 2 if (mcap > 100e9 and de < 0.5) else 0 if (mcap < 5e9 or de > 1.5) else 1
    return tam_idx, moat_idx, reinvest_idx, risk_idx


def calculate_3stage_dcf(rev_0, margin_0, target_margin, growth_high, sc_ratio, wacc_high, terminal_growth=0.025, tax_rate=0.21, return_details=False):
    margin_0 = float(np.clip(margin_0, -0.40, 0.80))
    target_margin = float(np.clip(target_margin, -0.40, 0.80))
    growth_high = float(np.clip(growth_high, -0.50, 0.80))
    sc_ratio = max(float(sc_ratio), 0.1)
    wacc_high = float(np.clip(wacc_high, 0.04, 0.25))
    terminal_growth = float(np.clip(terminal_growth, -0.02, 0.06))
    terminal_wacc = max(wacc_high, 0.075)

    records = []
    current_rev = float(max(rev_0, 0.0))
    prev_df = 1.0

    # Stage 1: Years 1-5
    for year in range(1, 6):
        prev_rev = current_rev
        current_rev = prev_rev * (1 + growth_high)
        margin = margin_0 + (target_margin - margin_0) * (year / 5.0)
        margin = float(np.clip(margin, -0.40, 0.80))
        ebit = current_rev * margin
        reinvest = max(0.0, (current_rev - prev_rev) / sc_ratio)
        nopat = ebit * (1 - tax_rate)
        fcff = nopat - reinvest
        df = 1 / ((1 + wacc_high) ** year)
        records.append({
            "year": year,
            "stage": "Stage 1",
            "revenue": current_rev,
            "growth": growth_high,
            "margin": margin,
            "ebit": ebit,
            "reinvestment": reinvest,
            "fcff": fcff,
            "wacc": wacc_high,
            "df": df,
            "pv": fcff * df,
        })
        prev_df = df

    # Stage 2: Years 6-10
    growth_10 = terminal_growth
    for step in range(1, 6):
        year = 5 + step
        frac = step / 5.0
        growth_y = growth_high + (growth_10 - growth_high) * frac
        wacc_y = wacc_high + (terminal_wacc - wacc_high) * frac
        prev_rev = current_rev
        current_rev = prev_rev * (1 + growth_y)
        margin = target_margin
        ebit = current_rev * margin
        reinvest = max(0.0, (current_rev - prev_rev) / sc_ratio)
        nopat = ebit * (1 - tax_rate)
        fcff = nopat - reinvest
        df = prev_df / (1 + wacc_y)
        records.append({
            "year": year,
            "stage": "Stage 2",
            "revenue": current_rev,
            "growth": growth_y,
            "margin": margin,
            "ebit": ebit,
            "reinvestment": reinvest,
            "fcff": fcff,
            "wacc": wacc_y,
            "df": df,
            "pv": fcff * df,
        })
        prev_df = df

    # Stage 3: Terminal value
    terminal_rev = current_rev * (1 + terminal_growth)
    terminal_ebit = terminal_rev * target_margin
    terminal_nopat = terminal_ebit * (1 - tax_rate)
    terminal_reinvestment_rate = terminal_growth / terminal_wacc if terminal_wacc > 0 else 0.0
    terminal_reinvestment = terminal_nopat * terminal_reinvestment_rate
    terminal_fcff = terminal_nopat - terminal_reinvestment
    denom = terminal_wacc - terminal_growth
    terminal_value = terminal_fcff / denom if denom > 0.005 else np.nan
    pv_terminal = terminal_value * prev_df if np.isfinite(terminal_value) else np.nan

    operating_value = float(np.nansum([r["pv"] for r in records]) + (pv_terminal if np.isfinite(pv_terminal) else 0.0))

    if return_details:
        return {
            "records": records,
            "terminal_value": terminal_value,
            "pv_terminal_value": pv_terminal,
            "operating_value": operating_value,
            "terminal_wacc": terminal_wacc,
            "terminal_growth": terminal_growth,
        }

    return operating_value


def run_vectorized_monte_carlo(rev_0, margin_0, target_margin_base, growth_base, sc_ratio, wacc_base, shares, net_debt, non_op, terminal_growth_base=0.025, tax_rate=0.21, n_sim=2000):
    np.random.seed(42)

    rev_0 = float(max(rev_0, 0.0))
    margin_0 = float(np.clip(margin_0, -0.40, 0.80))
    target_m = float(np.clip(target_margin_base, -0.40, 0.80))
    g_base = float(np.clip(growth_base, -0.50, 0.80))
    sc = max(float(sc_ratio), 0.1)
    w_base = float(np.clip(wacc_base, 0.04, 0.25))
    shares = max(float(shares), 1.0)
    tgrowth = float(np.clip(terminal_growth_base, -0.02, 0.06))

    sim_growth = np.random.normal(g_base, 0.04, n_sim).clip(0.00, 0.80)
    sim_margin = np.random.normal(target_m, 0.03, n_sim).clip(-0.10, 0.60)
    sim_wacc = np.random.normal(w_base, 0.01, n_sim).clip(0.04, 0.25)
    sim_term_wacc = np.maximum(sim_wacc, 0.075)

    years1 = np.arange(1, 6)
    years2 = np.arange(1, 6)

    sg = sim_growth[:, np.newaxis]
    sm = sim_margin[:, np.newaxis]
    sw = sim_wacc[:, np.newaxis]
    stw = sim_term_wacc[:, np.newaxis]

    # Stage 1
    revs1 = rev_0 * (1 + sg) ** years1
    prevs1 = np.zeros_like(revs1)
    prevs1[:, 0] = rev_0
    prevs1[:, 1:] = revs1[:, :-1]
    margins1 = margin_0 + (sm - margin_0) * (years1 / 5.0)
    nopats1 = revs1 * margins1 * (1 - tax_rate)
    reinvests1 = np.maximum(0.0, (revs1 - prevs1) / sc)
    fcffs1 = nopats1 - reinvests1
    dfs1 = 1 / ((1 + sw) ** years1)
    pv1 = fcffs1 * dfs1
    sum_pv1 = np.sum(pv1, axis=1)

    # Stage 2
    frac2 = years2 / 5.0
    g2 = sg + (tgrowth - sg) * frac2
    w2 = sw + (stw - sw) * frac2
    revs2 = np.zeros((n_sim, 5))
    revs2[:, 0] = revs1[:, -1] * (1 + g2[:, 0])
    for i in range(1, 5):
        revs2[:, i] = revs2[:, i - 1] * (1 + g2[:, i])
    prevs2 = np.zeros_like(revs2)
    prevs2[:, 0] = revs1[:, -1]
    prevs2[:, 1:] = revs2[:, :-1]
    margins2 = sm
    nopats2 = revs2 * margins2 * (1 - tax_rate)
    reinvests2 = np.maximum(0.0, (revs2 - prevs2) / sc)
    fcffs2 = nopats2 - reinvests2

    dfs2 = np.zeros_like(revs2)
    dfs2[:, 0] = dfs1[:, -1] / (1 + w2[:, 0])
    for i in range(1, 5):
        dfs2[:, i] = dfs2[:, i - 1] / (1 + w2[:, i])
    pv2 = fcffs2 * dfs2
    sum_pv2 = np.sum(pv2, axis=1)

    # Terminal
    rev_term = revs2[:, -1] * (1 + tgrowth)
    nopat_term = rev_term * sm[:, 0] * (1 - tax_rate)
    rr = tgrowth / sim_term_wacc[:, 0]
    fcff_term = nopat_term - nopat_term * rr
    denom = sim_term_wacc[:, 0] - tgrowth
    tv = np.where(denom > 0.005, fcff_term / denom, np.nan)
    pv_tv = tv * dfs2[:, -1]

    op_value = sum_pv1 + sum_pv2 + np.where(np.isfinite(pv_tv), pv_tv, 0.0)
    eq_value = op_value - float(net_debt) + float(non_op)
    sim_prices = np.maximum(0.0, eq_value / shares)
    sim_prices = sim_prices[np.isfinite(sim_prices)]
    return sim_prices


def calculate_story_consistency(story_tam, story_moat, story_reinvestment, story_risk, growth_rate, target_margin, sales_to_cap, cost_of_capital):
    score = 100
    critiques = []

    if "Disruptor" in story_tam and sales_to_cap < 1.0:
        score -= 20
        critiques.append("High-growth disruptor story but capital efficiency is very low.")
    if "Monopoly" in story_moat and target_margin < 0.15:
        score -= 15
        critiques.append("Monopoly / network-effect moat claimed but target margin is below 15%.")
    elif "Commodity" in story_moat and target_margin > 0.18:
        score -= 20
        critiques.append("Commodity player narrative but target margin exceeds 18%.")
    if "High Risk" in story_risk and cost_of_capital < 0.08:
        score -= 15
        critiques.append("High-risk story but WACC is below 8%.")
    elif "Low Risk" in story_risk and cost_of_capital > 0.12:
        score -= 10
        critiques.append("Low-risk story but WACC exceeds 12%.")
    if "Asset-Light" in story_reinvestment and sales_to_cap < 1.2:
        score -= 15
        critiques.append("Asset-light model selected but sales-to-capital ratio is below 1.2.")

    return max(10, score), critiques


def confidence_label(source, consistency_score):
    if source == "live" and consistency_score >= 80:
        return "High confidence"
    if consistency_score >= 60:
        return "Medium confidence"
    return "Low confidence"


st.title("📊 Aswath Damodaran Narrative Valuation Studio")
st.caption("Valuation is a bridge between narrative and numbers.")

st.sidebar.markdown("### 🔍 Live Data Sourcing")
ticker_input = st.sidebar.text_input("Enter Company Ticker", value="MSTR").strip().upper()

stock_data, api_success = fetch_stock_data(ticker_input)
damodaran_df = load_damodaran_industry_data()

if not api_success:
    st.sidebar.warning(f"Yahoo Finance lookup failed. Using fallback profile for {ticker_input}.")

ind_str = str(stock_data["industry"])
industry_match = damodaran_df[damodaran_df["Industry"].astype(str).str.contains(ind_str, case=False, na=False, regex=False)]
if not industry_match.empty:
    ind_avg_margin = float(industry_match["PreTaxOpMargin"].iloc[0])
    ind_avg_ps = float(industry_match["PriceSales"].iloc[0])
else:
    ind_avg_margin = 0.15
    ind_avg_ps = 3.0

default_tam, default_moat, default_reinvestment, default_risk = classify_narrative_defaults(stock_data, ind_avg_margin)

st.sidebar.markdown("---")
st.sidebar.markdown("### 📖 Step 1: Tell your Business Story")

story_tam = st.sidebar.selectbox(
    "Market TAM & Growth Narrative",
    [
        "Market Disruptor (High growth, rapid scale, capturing massive TAM)",
        "Healthy Competitor (Steady expansion, solid regional market share)",
        "Niche Player (Slow defensive play, mature market segments)",
    ],
    index=default_tam,
    key=f"tam_{stock_data['ticker']}",
)

story_moat = st.sidebar.selectbox(
    "Moat & Pricing Power",
    [
        "Monopoly / High Network Effects (Premium pricing, protected high margins)",
        "Sustainable Advantage (Strong brand loyalty, reasonable protection)",
        "Commodity Player (No protection, severe pricing competition)",
    ],
    index=default_moat,
    key=f"moat_{stock_data['ticker']}",
)

story_reinvestment = st.sidebar.selectbox(
    "Reinvestment & Asset Intensity",
    [
        "Asset-Light (High efficiency, digital or licensing models)",
        "Balanced Reinvestment (Industry standard shared asset structure)",
        "Capital Intensive (Low efficiency, massive factories and CapEx)",
    ],
    index=default_reinvestment,
    key=f"reinvest_{stock_data['ticker']}",
)

story_risk = st.sidebar.selectbox(
    "Risk Profile & WACC Anchor",
    [
        "High Risk (Emerging technology, high debt, volatile market)",
        "Average Risk (Established player, standard corporate leverage)",
        "Low Risk (Strong balance sheet, resilient recurring cash flow)",
    ],
    index=default_risk,
    key=f"risk_{stock_data['ticker']}",
)

st.sidebar.markdown("---")
st.sidebar.markdown("### 🔢 Step 2: Fine-Tune the Drivers")

historical_growth = float(stock_data["revenue_growth_1y"])
growth_anchor = max(0.01, min(0.35, historical_growth))

if "Disruptor" in story_tam:
    calc_growth = max(growth_anchor * 1.5, 0.25)
elif "Competitor" in story_tam:
    calc_growth = max(growth_anchor, 0.08)
else:
    calc_growth = min(growth_anchor * 0.4, 0.05)

actual_margin = float(np.clip(stock_data["operating_margin"], -0.40, 0.80))
if "Monopoly" in story_moat:
    calc_margin = max(actual_margin + 0.05, ind_avg_margin + 0.08)
elif "Sustainable" in story_moat:
    calc_margin = max(actual_margin, ind_avg_margin)
else:
    calc_margin = max(0.02, min(actual_margin * 0.4, ind_avg_margin * 0.4))

calc_sc = 3.0 if "Asset-Light" in story_reinvestment else 1.5 if "Balanced" in story_reinvestment else 0.7
base_wacc = 0.08 + (float(stock_data["debt_to_equity"]) * 0.005)
calc_wacc = base_wacc + 0.03 if "High Risk" in story_risk else base_wacc if "Average" in story_risk else base_wacc - 0.015
calc_wacc = float(np.clip(calc_wacc, 0.04, 0.18))

slider_key = f"{story_tam}_{story_moat}_{story_reinvestment}_{story_risk}_{stock_data['ticker']}"

growth_rate = st.sidebar.slider(
    "High Growth Rate (Yr 1-5)",
    0.0, 0.80, float(calc_growth), 0.01,
    format="%.0f%%",
    key=f"growth_s_{slider_key}",
)

target_margin = st.sidebar.slider(
    "Target Operating Margin (Yr 5)",
    -0.10, 0.60, float(calc_margin), 0.01,
    format="%.0f%%",
    key=f"margin_s_{slider_key}",
)

sales_to_cap = st.sidebar.slider(
    "Capital Efficiency (Sales-to-Capital)",
    0.1, 5.0, float(calc_sc), 0.1,
    key=f"cap_s_{slider_key}",
)

cost_of_capital = st.sidebar.slider(
    "Cost of Capital (WACC)",
    0.04, 0.20, float(calc_wacc), 0.005,
    format="%.1f%%",
    key=f"wacc_s_{slider_key}",
)

st.sidebar.markdown("---")
st.sidebar.markdown("### ⚙️ Advanced Model Settings")

tax_rate_input = st.sidebar.slider(
    "Corporate Tax Rate",
    min_value=0.05,
    max_value=0.35,
    value=0.21,
    step=0.01,
    format="%.0f%%",
    help="Default 21% in the US. Adjust for non-US companies.",
)

terminal_growth_input = st.sidebar.slider(
    "Terminal Growth Rate",
    min_value=0.00,
    max_value=0.05,
    value=0.025,
    step=0.005,
    format="%.1f%%",
    help="Long-run nominal growth. Lower for mature or smaller economies.",
)

st.sidebar.markdown("---")
st.sidebar.markdown("### 🪙 Step 3: Non-Operating Strategic Holdings")

fetched_non_op_value = float(stock_data.get("non_operating_assets", 0.0)) / 1e9
strategic_treasury = st.sidebar.slider(
    "Strategic Treasury Holdings ($B)",
    0.0,
    max(50.0, fetched_non_op_value * 2.5 + 5.0),
    float(fetched_non_op_value),
    0.1,
    help="Use for strategic holdings such as Bitcoin treasury, equity portfolios, or excess non-operating assets.",
)
non_operating_assets = strategic_treasury * 1e9

if stock_data.get("override_note"):
    st.sidebar.info(stock_data["override_note"])

st.header(f"🏢 {stock_data['company_name']} ({stock_data['ticker']})")
st.caption(
    f"Sector: {stock_data['sector']} | Industry: {stock_data['industry']} | "
    f"Data source: {stock_data.get('data_source', 'live')} | Price as of: {stock_data.get('price_as_of', 'live')}"
)

m1, m2, m3, m4 = st.columns(4)
with m1:
    st.markdown(
        f"<div class='metric-card'><div class='metric-title'>Current Price</div><div class='metric-value'>${stock_data['current_price']:.2f}</div></div>",
        unsafe_allow_html=True,
    )
with m2:
    st.markdown(
        f"<div class='metric-card'><div class='metric-title'>TTM Revenue</div><div class='metric-value'>${stock_data['revenue_ttm']/1e9:.2f}B</div></div>",
        unsafe_allow_html=True,
    )
with m3:
    st.markdown(
        f"<div class='metric-card'><div class='metric-title'>Actual Margin</div><div class='metric-value'>{float(stock_data['operating_margin'])*100:.1f}%</div></div>",
        unsafe_allow_html=True,
    )
with m4:
    st.markdown(
        f"<div class='metric-card'><div class='metric-title'>Historical Growth</div><div class='metric-value'>{float(stock_data['revenue_growth_1y'])*100:.1f}%</div></div>",
        unsafe_allow_html=True,
    )

st.markdown(
    "<div class='small-note'>Margins and growth rates are stored as decimals internally, and converted to percentages only for display.</div>",
    unsafe_allow_html=True,
)

st.markdown("---")

dcf_result = calculate_3stage_dcf(
    rev_0=stock_data["revenue_ttm"],
    margin_0=stock_data["operating_margin"],
    target_margin=target_margin,
    growth_high=growth_rate,
    sc_ratio=sales_to_cap,
    wacc_high=cost_of_capital,
    terminal_growth=terminal_growth_input,
    tax_rate=tax_rate_input,
    return_details=True,
)

operating_value = float(dcf_result["operating_value"]) if np.isfinite(dcf_result["operating_value"]) else np.nan
net_debt = float(stock_data["total_debt"]) - float(stock_data["cash"])
equity_value = operating_value - net_debt + non_operating_assets if np.isfinite(operating_value) else np.nan
shares_out = max(float(stock_data["shares_outstanding"]), 1.0)
intrinsic_value_per_share = max(0.0, equity_value / shares_out) if np.isfinite(equity_value) else np.nan

pv_terminal = dcf_result["pv_terminal_value"]
tv_contribution = (pv_terminal / operating_value) * 100 if np.isfinite(operating_value) and operating_value > 0 and np.isfinite(pv_terminal) else np.nan

consistency_score, critiques = calculate_story_consistency(
    story_tam, story_moat, story_reinvestment, story_risk,
    growth_rate, target_margin, sales_to_cap, cost_of_capital
)
confidence = confidence_label(stock_data.get("data_source", "demo"), consistency_score)

margin_variance = abs(float(target_margin) - float(stock_data["operating_margin"]))
growth_variance = abs(float(growth_rate) - float(stock_data["revenue_growth_1y"]))
alignment_index = max(10, 100 - int((margin_variance * 150) + (growth_variance * 150)))

col_left, col_right = st.columns([1.1, 0.9])

with col_left:
    st.subheader("📖 Narrative Alignment & Story Consistency")
    c_score_col, c_align_col = st.columns(2)

    with c_score_col:
        st.markdown(
            f"""
            <div class='score-card'>
                <div style='font-size: 11px; text-transform: uppercase; opacity: 0.8;'>Story Coherence Index</div>
                <div style='font-size: 42px; font-weight: 800; color: #38bdf8;'>{consistency_score}%</div>
                <div style='font-size: 11px; opacity: 0.8; margin-top: 4px;'>Narrative logical consistency</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c_align_col:
        st.markdown(
            f"""
            <div class='score-card' style='background: linear-gradient(135deg, #334155, #1e293b);'>
                <div style='font-size: 11px; text-transform: uppercase; opacity: 0.8;'>Assumption Alignment Index</div>
                <div style='font-size: 42px; font-weight: 800; color: #34d399;'>{alignment_index}%</div>
                <div style='font-size: 11px; opacity: 0.8; margin-top: 4px;'>Proximity to current fundamentals</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(f"<div class='small-note'>Confidence: <strong>{confidence}</strong>.</div>", unsafe_allow_html=True)

    if consistency_score >= 85:
        st.markdown("<div class='success-box'>✅ Strong narrative support. The selected story is broadly consistent with the numbers.</div>", unsafe_allow_html=True)
    elif consistency_score >= 60:
        st.markdown("<div class='info-box'>ℹ️ Mixed support. The story mostly works, but one or two assumptions deserve caution.</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='warning-box'>⚠️ Weak support. The story and the numbers are pulling in different directions.</div>", unsafe_allow_html=True)

    for critique in critiques:
        st.markdown(f"<div class='warning-box'>{critique}</div>", unsafe_allow_html=True)

    st.markdown("### 📊 Story vs. Implied Financial Inputs")
    comparison_df = pd.DataFrame({
        "Narrative Component": ["TAM / Growth", "Moat / Pricing", "Reinvestment / CapEx", "Risk Profile"],
        "Selected Story Option": [
            story_tam.split(" (")[0],
            story_moat.split(" (")[0],
            story_reinvestment.split(" (")[0],
            story_risk.split(" (")[0],
        ],
        "Implied Financial Preset": [
            f"{calc_growth*100:.1f}% Growth",
            f"{calc_margin*100:.1f}% Margin",
            f"{calc_sc:.1f} Sales-to-Capital",
            f"{cost_of_capital*100:.1f}% WACC",
        ],
        "Your Fine-Tuned Value": [
            f"{growth_rate*100:.1f}% Growth",
            f"{target_margin*100:.1f}% Margin",
            f"{sales_to_cap:.1f} Sales-to-Capital",
            f"{cost_of_capital*100:.1f}% WACC",
        ],
    })
    st.table(comparison_df)

with col_right:
    st.subheader("⚖️ Valuation Bridge & Outputs")

    cp = float(stock_data["current_price"])
    price_pct_diff = ((intrinsic_value_per_share - cp) / cp) * 100 if cp and np.isfinite(intrinsic_value_per_share) else np.nan
    delta_color = "#16a34a" if np.isfinite(price_pct_diff) and price_pct_diff >= 0 else "#dc2626"
    delta_symbol = "➕" if np.isfinite(price_pct_diff) and price_pct_diff >= 0 else "➖"
    iv_display = f"${intrinsic_value_per_share:.2f}" if np.isfinite(intrinsic_value_per_share) else "N/A"
    pdiff_display = f"{abs(price_pct_diff):.1f}%" if np.isfinite(price_pct_diff) else "N/A"

    st.markdown(
        f"""
        <div style='background-color: white; padding: 24px; border-radius: 12px; border: 1px solid #eef2f6; text-align: center; box-shadow: 0 4px 12px rgba(0,0,0,0.02);'>
            <div style='font-size: 14px; text-transform: uppercase; color: #64748b; font-weight: 600;'>Implied Intrinsic Value Per Share</div>
            <div style='font-size: 48px; font-weight: 800; color: #0f172a; margin: 8px 0;'>{iv_display}</div>
            <div style='font-size: 16px; font-weight: 600; color: {delta_color};'>{delta_symbol} {pdiff_display} over / under current price of ${cp:.2f}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.write("")

    if np.isfinite(tv_contribution):
        if tv_contribution > 80.0:
            st.markdown(
                f"<div class='warning-box'>🚨 <strong>Terminal Value Domination Warning:</strong> Present value of terminal value is <strong>{tv_contribution:.1f}%</strong> of operating assets.</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"<div class='info-box'>ℹ️ <strong>Stable Valuation Mix:</strong> Terminal value is <strong>{tv_contribution:.1f}%</strong> of operating assets.</div>",
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            "<div class='warning-box'>🚨 Terminal value could not be computed safely because growth and discount assumptions are too close.</div>",
            unsafe_allow_html=True,
        )

    b_col1, b_col2 = st.columns(2)
    with b_col1:
        st.metric("Total Operating Assets", f"${operating_value/1e9:.2f}B" if np.isfinite(operating_value) else "N/A")
    with b_col2:
        st.metric("Strategic Treasury Holdings", f"${non_operating_assets/1e9:.2f}B")

st.markdown("---")
st.subheader("🗓️ Multi-Stage Cashflow Projection")

projection_df = pd.DataFrame({
    "Revenue ($B)": [r["revenue"] / 1e9 for r in dcf_result["records"]],
    "Margin": [f"{r['margin']*100:.1f}%" for r in dcf_result["records"]],
    "EBIT ($B)": [r["ebit"] / 1e9 for r in dcf_result["records"]],
    "Reinvestment ($B)": [r["reinvestment"] / 1e9 for r in dcf_result["records"]],
    "FCFF ($B)": [r["fcff"] / 1e9 for r in dcf_result["records"]],
    "PV ($B)": [r["pv"] / 1e9 for r in dcf_result["records"]],
}, index=[f"Year {r['year']}" for r in dcf_result["records"]])

st.dataframe(projection_df.style.format(precision=3), use_container_width=True)

st.markdown("---")
chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    st.subheader("📊 Intrinsic Value Bridge")
    cumulative_pvs = float(np.nansum([r["pv"] for r in dcf_result["records"]]))
    pv_tv = float(pv_terminal) if np.isfinite(pv_terminal) else 0.0

    fig_waterfall = go.Figure(go.Waterfall(
        name="Value Bridge",
        orientation="v",
        measure=["relative", "relative", "total", "relative", "relative", "total"],
        x=["PV of 10Yr FCFF", "PV of Terminal Value", "Operating Assets", "Non-Operating Assets", "Less Net Debt", "Common Equity Value"],
        text=[
            f"${cumulative_pvs/1e9:.2f}B",
            f"${pv_tv/1e9:.2f}B",
            f"${operating_value/1e9:.2f}B" if np.isfinite(operating_value) else "N/A",
            f"${non_operating_assets/1e9:.2f}B",
            f"${-net_debt/1e9:.2f}B",
            f"${equity_value/1e9:.2f}B" if np.isfinite(equity_value) else "N/A",
        ],
        y=[cumulative_pvs/1e9, pv_tv/1e9, 0, non_operating_assets/1e9, -net_debt/1e9, 0],
        connector={"line": {"color": "rgb(63, 63, 63)"}},
    ))
    fig_waterfall.update_layout(showlegend=False, yaxis_title="$ Billions")
    st.plotly_chart(fig_waterfall, use_container_width=True)
    st.caption("This bridge shows how the story becomes operating value, then equity value.")

with chart_col2:
    st.subheader("🎲 Probable Value (Instant Monte Carlo)")
    sim_prices = run_vectorized_monte_carlo(
        rev_0=stock_data["revenue_ttm"],
        margin_0=stock_data["operating_margin"],
        target_margin_base=target_margin,
        growth_base=growth_rate,
        sc_ratio=sales_to_cap,
        wacc_base=cost_of_capital,
        shares=shares_out,
        net_debt=net_debt,
        non_op=non_operating_assets,
        terminal_growth_base=terminal_growth_input,
        tax_rate=tax_rate_input,
        n_sim=2000,
    )

    if len(sim_prices) > 0:
        p10, p50, p90 = np.percentile(sim_prices, [10, 50, 90])
        undervalued_prob = (sim_prices > cp).mean() * 100 if cp else 0

        st.markdown(f"🎯 **Median Simulated Value:** `${p50:.2f}` per share")
        st.markdown(f"🛡️ **Conservative case (10th percentile):** `${p10:.2f}` | **Optimistic case (90th percentile):** `${p90:.2f}`")

        fig_dist = px.histogram(sim_prices, nbins=50, color_discrete_sequence=["#0284c7"])
        fig_dist.add_vline(x=cp, line_dash="dash", line_color="red", annotation_text="Current Market Price")
        fig_dist.update_layout(showlegend=False)
        st.plotly_chart(fig_dist, use_container_width=True)
        st.caption("This distribution shows the range of likely values if the story changes a little.")
    else:
        undervalued_prob = 0
        st.warning("Monte Carlo simulation could not produce valid outputs.")

st.markdown("---")
st.subheader("⚖️ Damodaran's Triad Check: Possible, Plausible, and Probable")
st.caption("A good story should be mathematically possible, economically plausible, and probabilistically supportable.")

t_col1, t_col2, t_col3 = st.columns(3)

with t_col1:
    st.markdown("### 🛠️ Possible")
    if target_margin < 0.80 and cost_of_capital > 0.035:
        st.success("✅ Passed mathematical feasibility")
        st.markdown("* Target margin is below 80% and WACC is above a practical lower bound.")
    else:
        st.error("❌ Mathematical boundary breach")
        st.markdown("* Assumptions may violate corporate finance bounds.")

with t_col2:
    st.markdown("### ⚖️ Plausible")
    warnings = []
    if abs(growth_rate - stock_data["revenue_growth_1y"]) > 0.25:
        warnings.append(
            f"• Target growth ({growth_rate*100:.0f}%) is far from historical growth ({float(stock_data['revenue_growth_1y'])*100:.0f}%)."
        )
    if target_margin > (ind_avg_margin + 0.15):
        warnings.append(f"• Target margin is far above industry average ({ind_avg_margin*100:.0f}%).")
    if not warnings:
        st.success("✅ Passed operational plausibility")
        st.markdown("* Inputs remain within plausible benchmark ranges.")
    else:
        st.warning("⚠️ Ambitious narrative alerts:")
        for w in warnings:
            st.markdown(w)

with t_col3:
    st.markdown("### 🎲 Probable")
    if len(sim_prices) > 0:
        if undervalued_prob > 75:
            st.success(f"🎯 High likelihood of undervaluation: {undervalued_prob:.1f}%")
        elif undervalued_prob >= 35:
            st.info(f"⚖️ Balanced / fairly valued: {undervalued_prob:.1f}%")
        else:
            st.error(f"🚨 High likelihood of overvaluation: {undervalued_prob:.1f}%")
