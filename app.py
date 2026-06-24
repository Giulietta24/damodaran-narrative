import streamlit as st
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np

# ─────────────────────────────────────────────
# 1. PAGE SETUP
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Damodaran Narrative Valuation Studio",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
.metric-card {
    background-color: var(--background-color, white);
    padding: 22px;
    border-radius: 12px;
    border: 1px solid #eef2f6;
    box-shadow: 0 4px 6px rgba(0,0,0,0.02);
}
.metric-title {font-size: 13px; text-transform: uppercase; color: #64748b; font-weight: 600; letter-spacing: 0.5px;}
.metric-value {font-size: 28px; font-weight: 700; color: inherit;}
.warning-box  {background-color: #fef3c7; border-left: 4px solid #d97706; color: #92400e; padding: 14px 16px; border-radius: 0 8px 8px 0; margin: 10px 0;}
.success-box  {background-color: #f0fdf4; border-left: 4px solid #16a34a; color: #166534; padding: 14px 16px; border-radius: 0 8px 8px 0; margin: 10px 0;}
.info-box     {background-color: #f0f9ff; border-left: 4px solid #0284c7; color: #075985; padding: 14px 16px; border-radius: 0 8px 8px 0; margin: 10px 0;}
.score-card   {text-align: center; background: #1e293b; color: white; padding: 22px; border-radius: 12px;}
.small-note   {font-size: 12px; color: #64748b; margin: 4px 0;}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# 2. DISCLAIMER
# ─────────────────────────────────────────────
st.warning(
    "⚠️ For educational and research purposes only. "
    "This tool produces illustrative valuation estimates, not investment recommendations. "
    "Not financial, legal, or tax advice."
)

st.title("📊 Aswath Damodaran Narrative Valuation Studio")
st.caption(
    '"Valuation is a bridge between narrative and numbers. '
    'If you have numbers without a narrative, you have no soul. '
    'If you have a narrative without numbers, you have a fairy tale." — Prof. Aswath Damodaran'
)

# ─────────────────────────────────────────────
# 3. DAMODARAN INDUSTRY DATA
# ─────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_damodaran_industry_data():
    url = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/psdata.xls"
    try:
        df = pd.read_excel(url, header=None)
        # Find the actual header row by scanning for "Industry"
        header_row = 0
        for i, row in df.iterrows():
            if any("industry" in str(v).lower() for v in row.values):
                header_row = i
                break
        df = pd.read_excel(url, header=header_row)
        df.columns = [str(c).strip() for c in df.columns]
        # Fuzzy column matching
        col_map = {}
        for c in df.columns:
            cl = c.lower()
            if "industry" in cl and "name" in cl:
                col_map[c] = "Industry"
            elif "pre-tax" in cl and "margin" in cl:
                col_map[c] = "PreTaxOpMargin"
            elif "price" in cl and "sale" in cl:
                col_map[c] = "PriceSales"
        df = df.rename(columns=col_map)
        required = {"Industry", "PreTaxOpMargin", "PriceSales"}
        if not required.issubset(df.columns):
            raise ValueError(f"Column mismatch. Found: {list(df.columns[:8])}")
        df["PreTaxOpMargin"] = pd.to_numeric(df["PreTaxOpMargin"], errors="coerce")
        df["PriceSales"] = pd.to_numeric(df["PriceSales"], errors="coerce")
        return df.dropna(subset=["Industry"])
    except Exception as e:
        st.sidebar.caption(f"ℹ️ Damodaran data fetch failed ({e}). Using curated fallback.")
        return pd.DataFrame({
            "Industry": [
                "Software (System & Application)", "Semiconductor",
                "Technology Hardware", "Pharmaceuticals",
                "Integrated Oil & Gas", "Banks",
                "Retail (Online)", "Automotive",
                "Telecom Services", "Healthcare Products",
                "Financial Svcs. (Non-bank & Insurance)", "Entertainment"
            ],
            "PriceSales":      [11.01, 15.46, 6.43, 5.63, 2.00, 3.67, 4.50, 1.25, 2.10, 4.80, 3.20, 3.50],
            "PreTaxOpMargin":  [0.3321, 0.3531, 0.2249, 0.2954, 0.2582, 0.1250, 0.0850, 0.0720, 0.1850, 0.2100, 0.2200, 0.1500],
        })

# ─────────────────────────────────────────────
# 4. STOCK DATA FETCH & CRYPTO TREASURY ENGINES
# ─────────────────────────────────────────────
FUNDAMENTAL_OVERRIDE_TICKERS = {"MSTR"}

CRYPTO_BALANCE_SHEET_LABELS = [
    "Digital Assets", "Cryptocurrencies", "Bitcoin", "Ethereum",
    "Other Long Term Assets", "Other Non Current Assets",
    "Long Term Investments", "Other Current Assets",
]

def is_crypto_treasury(info: dict, balance_sheet) -> tuple:
    crypto_value = 0.0
    crypto_label = "unknown"

    op_margin = info.get("operatingMargins")
    margin_distorted = isinstance(op_margin, (int, float)) and not (-0.40 <= float(op_margin) <= 0.80)

    bs_has_crypto = False
    try:
        if balance_sheet is not None and not balance_sheet.empty:
            total_assets_row = [i for i in balance_sheet.index if "total assets" in str(i).lower()]
            total_assets = float(balance_sheet.loc[total_assets_row[0]].iloc[0]) if total_assets_row else 0.0

            for label in CRYPTO_BALANCE_SHEET_LABELS:
                if label in balance_sheet.index:
                    val = balance_sheet.loc[label].dropna()
                    if not val.empty:
                        v = float(val.iloc[0])
                        if v > 500_000_000:
                            if total_assets > 0 and (v / total_assets) > 0.20:
                                bs_has_crypto = True
                                crypto_value = v
                                crypto_label = label
                                break
                            elif total_assets == 0 and v > 1_000_000_000:
                                bs_has_crypto = True
                                crypto_value = v
                                crypto_label = label
                                break
    except Exception:
        pass

    industry = str(info.get("industry", "")).lower()
    long_biz = str(info.get("longBusinessSummary", "")).lower()
    keyword_match = any(
        kw in industry or kw in long_biz[:500]
        for kw in ["bitcoin", "ethereum", "crypto", "digital asset", "blockchain treasury"]
    )

    is_treasury = margin_distorted or bs_has_crypto or keyword_match
    return is_treasury, crypto_value, crypto_label

@st.cache_data(ttl=60)
def fetch_live_crypto_prices():
    prices = {"BTC": None, "ETH": None}
    for symbol, key in [("BTC-USD", "BTC"), ("ETH-USD", "ETH")]:
        try:
            t = yf.Ticker(symbol)
            price = t.fast_info.get("last_price")
            if price and float(price) > 1:
                prices[key] = float(price)
            else:
                hist = t.history(period="1d")
                if not hist.empty:
                    prices[key] = float(hist["Close"].iloc[-1])
        except Exception:
            pass
    return prices

@st.cache_data(ttl=60)
def fetch_stock_data(ticker_symbol):
    ticker_symbol = ticker_symbol.upper().strip()

    profiles = {
        "AAPL": {"company_name": "Apple Inc.", "sector": "Technology", "industry": "Technology Hardware",
                 "revenue_ttm": 391_000_000_000, "operating_margin": 0.307, "net_margin": 0.263,
                 "debt_to_equity": 1.45, "current_price": 213.0, "market_cap": 3_270_000_000_000,
                 "shares_outstanding": 15_330_000_000, "cash": 73_000_000_000, "total_debt": 108_000_000_000,
                 "revenue_growth_1y": 0.02, "non_operating_assets": 158_000_000_000,
                 "price_as_of": "Jun 2026", "data_source": "fallback"},
        "TSLA": {"company_name": "Tesla Inc.", "sector": "Automotive", "industry": "Automotive",
                 "revenue_ttm": 96_000_000_000, "operating_margin": 0.075, "net_margin": 0.055,
                 "debt_to_equity": 0.10, "current_price": 248.0, "market_cap": 795_000_000_000,
                 "shares_outstanding": 3_200_000_000, "cash": 26_800_000_000, "total_debt": 9_500_000_000,
                 "revenue_growth_1y": 0.01, "non_operating_assets": 5_400_000_000,
                 "price_as_of": "Jun 2026", "data_source": "fallback"},
        "MSTR": {"company_name": "MicroStrategy Inc. (MSTR)", "sector": "Technology",
                 "industry": "Software (System & Application)",
                 "revenue_ttm": 463_000_000, "operating_margin": 0.08, "net_margin": 0.05,
                 "debt_to_equity": 3.2, "current_price": 385.0, "market_cap": 75_000_000_000,
                 "shares_outstanding": 294_000_000,
                 "cash": 50_000_000, "total_debt": 8_200_000_000,
                 "revenue_growth_1y": -0.05,
                 "non_operating_assets": 44_200_000_000,
                 "btc_holdings": 713_502,
                 "price_as_of": "Jun 2026", "data_source": "fallback",
                 "override_note": "Fundamentals use curated profile — P&L distorted by Bitcoin mark-to-market. Bitcoin treasury value computed live from BTC-USD price × 713,502 BTC held."},
        "NVDA": {"company_name": "NVIDIA Corp.", "sector": "Technology", "industry": "Semiconductor",
                 "revenue_ttm": 130_000_000_000, "operating_margin": 0.62, "net_margin": 0.55,
                 "debt_to_equity": 0.20, "current_price": 131.0, "market_cap": 3_210_000_000_000,
                 "shares_outstanding": 24_500_000_000, "cash": 25_000_000_000, "total_debt": 11_000_000_000,
                 "revenue_growth_1y": 1.22, "non_operating_assets": 15_000_000_000,
                 "price_as_of": "Jun 2026", "data_source": "fallback"},
        "COIN": {"company_name": "Coinbase Global Inc.", "sector": "Financial Services",
                 "industry": "Financial Svcs. (Non-bank & Insurance)",
                 "revenue_ttm": 6_600_000_000, "operating_margin": 0.22, "net_margin": 0.18,
                 "debt_to_equity": 0.45, "current_price": 260.0, "market_cap": 66_000_000_000,
                 "shares_outstanding": 254_000_000, "cash": 7_200_000_000, "total_debt": 4_200_000_000,
                 "revenue_growth_1y": 1.10, "non_operating_assets": 1_200_000_000,
                 "price_as_of": "Jun 2026", "data_source": "fallback", "override_note": ""},
        "BMNR": {"company_name": "Bitmine Immersion Technologies (BMNR)",
                 "sector": "Technology", "industry": "Financial Svcs. (Non-bank)",
                 "revenue_ttm": 150_000_000, "operating_margin": 0.05, "net_margin": 0.03,
                 "debt_to_equity": 0.30, "current_price": 14.25, "market_cap": 7_700_000_000,
                 "shares_outstanding": 537_630_000,
                 "cash": 500_000_000, "total_debt": 800_000_000,
                 "revenue_growth_1y": 2.0,
                 "non_operating_assets": 9_657_455_172,
                 "eth_holdings": 5_620_754,
                 "btc_holdings": 204,
                 "price_as_of": "Jun 2026",
                 "data_source": "fallback",
                 "override_note": "Largest ETH treasury globally. P&L distorted by ETH mark-to-market. Treasury value computed live from ETH price x 5,620,754 ETH + BTC holdings."},
    }

    try:
        ticker = yf.Ticker(ticker_symbol)
        info   = ticker.info or {}
        if not info:
            raise ValueError("No info returned")

        live_price = (info.get("currentPrice") or info.get("regularMarketPrice")
                      or info.get("previousClose"))
        if live_price is None:
            raise ValueError("No live price available")

        # Step 1: Fetch balance sheet early — needed for auto-detection
        try:
            bs = ticker.balance_sheet
        except Exception:
            bs = None

        # Step 2: Auto-detect crypto treasury companies
        live_shares = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")
        is_treasury, bs_crypto_value, bs_crypto_label = is_crypto_treasury(info, bs)

        if is_treasury:
            # Use curated profile if available, otherwise build a generic shell
            if ticker_symbol in profiles:
                p = profiles[ticker_symbol].copy()
            else:
                p = {
                    "company_name":        info.get("longName", info.get("shortName", f"{ticker_symbol} Corp")),
                    "sector":              info.get("sector", "Technology"),
                    "industry":            info.get("industry", "Financial Svcs. (Non-bank)"),
                    "revenue_ttm":          info.get("totalRevenue") or 100_000_000,
                    "operating_margin":     0.05,
                    "net_margin":           0.03,
                    "debt_to_equity":       (float(info.get("debtToEquity", 50)) / 100.0),
                    "current_price":        float(live_price),
                    "market_cap":           info.get("marketCap") or 0,
                    "shares_outstanding":   float(live_shares) if live_shares else 100_000_000,
                    "cash":                 info.get("totalCash") or 0.0,
                    "total_debt":           info.get("totalDebt") or 0.0,
                    "revenue_growth_1y":    0.10,
                    "non_operating_assets": 0.0,
                    "price_as_of":          "live",
                    "data_source":          "auto_detected_crypto_treasury",
                    "override_note":        "Auto-detected as crypto treasury company. P&L margins are unreliable due to crypto mark-to-market accounting. Crypto asset value computed from balance sheet or live prices.",
                }

            p["ticker"]        = ticker_symbol
            p["current_price"] = float(live_price)
            p["price_as_of"]   = "live"
            p["data_source"]   = p.get("data_source", "auto_detected_crypto_treasury")

            if live_shares and float(live_shares) > 1_000_000:
                p["shares_outstanding"] = float(live_shares)
            p["market_cap"] = p["shares_outstanding"] * float(live_price)

            crypto_prices = fetch_live_crypto_prices()
            crypto_treasury = None
            crypto_source   = "unknown"

            if bs_crypto_value > 500_000_000:
                crypto_treasury = bs_crypto_value
                crypto_source   = f"balance sheet ({bs_crypto_label})"

            if crypto_treasury is None and "btc_holdings" in p and crypto_prices["BTC"]:
                crypto_treasury = p["btc_holdings"] * crypto_prices["BTC"]
                crypto_source   = f"profile: {p['btc_holdings']:,} BTC x ${crypto_prices['BTC']:,.0f}"

            if crypto_treasury is None and "eth_holdings" in p and crypto_prices["ETH"]:
                crypto_treasury = p["eth_holdings"] * crypto_prices["ETH"]
                crypto_source   = f"profile: {p['eth_holdings']:,} ETH x ${crypto_prices['ETH']:,.0f}"

            if crypto_treasury is None:
                crypto_treasury = p.get("non_operating_assets", 0.0)
                crypto_source   = "stale profile value — update holdings count manually"

            p["non_operating_assets"] = crypto_treasury
            prices_str = f"BTC=${crypto_prices['BTC']:,.0f}" if crypto_prices["BTC"] else ""
            if crypto_prices["ETH"]:
                prices_str += f" | ETH=${crypto_prices['ETH']:,.0f}"
            p["override_note"] = (
                f"Crypto treasury detected. P&L margins use {'curated profile' if ticker_symbol in profiles else 'auto-generated shell'}. "
                f"Treasury value: ${crypto_treasury/1e9:.2f}B (source: {crypto_source}). "
                f"Live prices: {prices_str}."
            )
            return p, True

        def _sanitize_ratio(value, fallback, low=-2.0, high=2.0):
            if isinstance(value, (int, float)) and low <= float(value) <= high:
                return float(value)
            return fallback

        def _sanitize_growth(value, fallback, low=-0.90, high=3.0):
            if isinstance(value, (int, float)) and low <= float(value) <= high:
                return float(value)
            return fallback

        shares = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding") or 0
        cash   = info.get("totalCash") or 0.0
        debt   = info.get("totalDebt") or 0.0
        profile_base = profiles.get(ticker_symbol, {})

        raw_op_margin = info.get("operatingMargins")
        operating_margin = _sanitize_ratio(
            raw_op_margin,
            fallback=profile_base.get("operating_margin", 0.10),
            low=-0.40, high=0.80
        )
        if raw_op_margin is not None and not isinstance(raw_op_margin, (int, float)) or \
           (isinstance(raw_op_margin, (int, float)) and not (-0.40 <= float(raw_op_margin) <= 0.80)):
            st.sidebar.caption(
                f"ℹ️ Reported operating margin looked distorted. Using fallback: {operating_margin*100:.1f}%"
            )

        net_margin = _sanitize_ratio(
            info.get("profitMargins"),
            fallback=profile_base.get("net_margin", 0.08),
            low=-0.60, high=0.80
        )

        rev_growth = None
        try:
            fin = ticker.financials
            if fin is not None and not fin.empty:
                revenue_rows = [
                    idx for idx in fin.index
                    if any(x in str(idx).lower() for x in ["revenue", "sales", "turnover"])
                ]
                if revenue_rows:
                    rev_series = fin.loc[revenue_rows[0]].dropna()
                    if len(rev_series) >= 2 and rev_series.iloc[1] != 0:
                        calc = float((rev_series.iloc[0] - rev_series.iloc[1]) / rev_series.iloc[1])
                        rev_growth = _sanitize_growth(calc, None)
        except Exception:
            pass

        if rev_growth is None:
            rev_growth = _sanitize_growth(
                info.get("revenueGrowth"),
                fallback=profile_base.get("revenue_growth_1y", 0.10)
            )
        elif not (-0.90 <= rev_growth <= 3.0):
            rev_growth = profile_base.get("revenue_growth_1y", 0.10)

        non_op = 0.0
        try:
            balance = ticker.balance_sheet
            if balance is not None and not balance.empty:
                for col in ["Long Term Investments", "Other Long Term Assets",
                            "Other Current Assets", "Other Non Current Assets"]:
                    if col in balance.index:
                        series = balance.loc[col].dropna()
                        if not series.empty:
                            non_op = max(non_op, float(series.iloc[0]))
        except Exception:
            pass

        d_to_e = info.get("debtToEquity")
        data = {
            "ticker":               ticker_symbol,
            "company_name":         info.get("longName", info.get("shortName", profile_base.get("company_name", f"{ticker_symbol} Corp"))),
            "sector":               info.get("sector",   profile_base.get("sector", "Other")),
            "industry":             info.get("industry", profile_base.get("industry", "Other")),
            "revenue_ttm":          info.get("totalRevenue") or profile_base.get("revenue_ttm", 1_000_000_000),
            "operating_margin":     operating_margin,
            "net_margin":           net_margin,
            "debt_to_equity":       (float(d_to_e) / 100.0) if isinstance(d_to_e, (int, float)) else profile_base.get("debt_to_equity", 0.5),
            "current_price":        float(live_price),
            "market_cap":           info.get("marketCap") or (shares * float(live_price) if shares else profile_base.get("market_cap", 0)),
            "shares_outstanding":   shares if shares else profile_base.get("shares_outstanding", 10_000_000),
            "cash":                 cash if cash > 0 else profile_base.get("cash", 0.0),
            "total_debt":           debt if debt > 0 else profile_base.get("total_debt", 0.0),
            "revenue_growth_1y":    rev_growth,
            "non_operating_assets": non_op if non_op > 0 else profile_base.get("non_operating_assets", 0.0),
            "price_as_of":          "live",
            "data_source":          "live",
            "override_note":        "",
        }
        return data, True

    except Exception:
        if ticker_symbol in profiles:
            p = profiles[ticker_symbol].copy()
            p["ticker"]     = ticker_symbol
            p["market_cap"] = p["shares_outstanding"] * p["current_price"]
            if "override_note" not in p:
                p["override_note"] = ""
            return p, True

        generic = {
            "ticker": ticker_symbol, "company_name": f"{ticker_symbol} Enterprise",
            "sector": "Industrial Tech", "industry": "Software (System & Application)",
            "revenue_ttm": 1_200_000_000, "operating_margin": 0.14, "net_margin": 0.09,
            "debt_to_equity": 0.40, "current_price": 50.0, "market_cap": 5_000_000_000,
            "shares_outstanding": 100_000_000, "cash": 300_000_000, "total_debt": 150_000_000,
            "revenue_growth_1y": 0.12, "non_operating_assets": 50_000_000,
            "price_as_of": "demo", "data_source": "demo", "override_note": "",
        }
        return generic, False

# ─────────────────────────────────────────────
# 5. NARRATIVE DEFAULTS CLASSIFIER
# ─────────────────────────────────────────────
def classify_narrative_defaults(stock_data, ind_avg_margin):
    g = stock_data["revenue_growth_1y"]
    tam_idx  = 0 if g > 0.25 else 1 if g >= 0.06 else 2
    m = stock_data["operating_margin"]
    moat_idx = 0 if (m > 0.25 or m > ind_avg_margin + 0.05) else 1 if m >= 0.10 else 2
    ind = str(stock_data["industry"]).lower()
    if any(x in ind for x in ["software", "internet", "service"]):
        ri = 0
    elif any(x in ind for x in ["automotive", "hardware", "manufactur", "oil"]):
        ri = 2
    else:
        ri = 1
    mc = stock_data["market_cap"]
    de = stock_data["debt_to_equity"]
    risk_idx = 2 if (mc > 100e9 and de < 0.5) else 0 if (mc < 5e9 or de > 1.5) else 1
    return tam_idx, moat_idx, ri, risk_idx

# ─────────────────────────────────────────────
# 6. FULL 3-STAGE DCF (Damodaran Standard)
# ─────────────────────────────────────────────
def calculate_3stage_dcf(
    rev_0, margin_0, target_margin, growth_high,
    sc_ratio, wacc_high,
    terminal_growth=0.025, tax_rate=0.21,
    return_details=False
):
    margin_start   = float(np.clip(margin_0,      -0.40, 0.80))
    target_margin  = float(np.clip(target_margin, -0.40, 0.80))
    growth_high    = float(np.clip(growth_high,   -0.50, 0.80))
    sc_ratio       = max(float(sc_ratio), 0.1)
    wacc_high      = float(np.clip(wacc_high,      0.04, 0.25))
    terminal_growth = float(np.clip(terminal_growth, -0.02, 0.06))

    terminal_wacc = max(wacc_high, 0.075)
    stable_growth = terminal_growth  

    records = []
    current_rev = float(max(rev_0, 0.0))

    # Stage 1: Years 1-5
    for year in range(1, 6):
        prev_rev = current_rev
        current_rev = prev_rev * (1 + growth_high)
        margin   = margin_start + (target_margin - margin_start) * (year / 5.0)
        margin   = float(np.clip(margin, -0.40, 0.80))
        ebit     = current_rev * margin
        nopat    = ebit * (1 - tax_rate)
        reinvest = max(0.0, (current_rev - prev_rev) / sc_ratio)
        fcff     = nopat - reinvest
        wacc_y   = wacc_high
        df       = 1 / (1 + wacc_y) ** year
        records.append(dict(year=year, stage=1, revenue=current_rev, growth=growth_high,
                            margin=margin, ebit=ebit, reinvestment=reinvest,
                            fcff=fcff, wacc=wacc_y, df=df, pv=fcff * df))

    # Stage 2: Years 6-10 deceleration
    for step in range(1, 6):
        year = 5 + step
        frac = step / 5.0 
        growth_y = growth_high + (stable_growth - growth_high) * frac
        wacc_y   = wacc_high   + (terminal_wacc - wacc_high)   * frac

        prev_rev = current_rev
        current_rev = prev_rev * (1 + growth_y)
        margin   = target_margin
        ebit     = current_rev * margin
        nopat    = ebit * (1 - tax_rate)
        reinvest = max(0.0, (current_rev - prev_rev) / sc_ratio)
        fcff     = nopat - reinvest

        prev_df = records[-1]["df"]
        df_y    = prev_df / (1 + wacc_y)
        records.append(dict(year=year, stage=2, revenue=current_rev, growth=growth_y,
                            margin=margin, ebit=ebit, reinvestment=reinvest,
                            fcff=fcff, wacc=wacc_y, df=df_y, pv=fcff * df_y))

    # Stage 3: Terminal Value
    terminal_rev     = current_rev * (1 + terminal_growth)
    terminal_ebit    = terminal_rev * target_margin
    terminal_nopat   = terminal_ebit * (1 - tax_rate)
    rr               = terminal_growth / terminal_wacc if terminal_wacc > 0 else 0.0
    terminal_reinvest = terminal_nopat * rr
    terminal_fcff    = terminal_nopat - terminal_reinvest

    denom = terminal_wacc - terminal_growth
    terminal_value   = terminal_fcff / denom if denom > 0.005 else np.nan
    last_df          = records[-1]["df"]
    pv_terminal      = terminal_value * last_df if np.isfinite(terminal_value) else np.nan

    sum_pv_fcff = sum(r["pv"] for r in records)
    operating_value = float(np.nansum([sum_pv_fcff,
                                       pv_terminal if np.isfinite(pv_terminal) else 0.0]))

    if return_details:
        return {
            "records":          records,
            "terminal_value":   terminal_value,
            "pv_terminal_value": pv_terminal,
            "operating_value":  operating_value,
            "terminal_wacc":    terminal_wacc,
            "terminal_growth":  terminal_growth,
        }
    return operating_value

# ─────────────────────────────────────────────
# 7. VECTORIZED 3-STAGE MONTE CARLO (Assembled)
# ─────────────────────────────────────────────
def run_vectorized_monte_carlo(
    rev_0, margin_0, target_margin_base, growth_base,
    sc_ratio, wacc_base, shares, net_debt, non_op,
    terminal_growth_base=0.025, tax_rate=0.21, n_sim=2000
):
    np.random.seed(42)
    rev_0    = float(max(rev_0, 0.0))
    margin_0 = float(np.clip(margin_0, -0.40, 0.80))
    target_m = float(np.clip(target_margin_base, -0.40, 0.80))
    g_base   = float(np.clip(growth_base, -0.50, 0.80))
    sc       = max(float(sc_ratio), 0.1)
    w_base   = float(np.clip(wacc_base, 0.04, 0.25))
    shares   = max(float(shares), 1.0)
    t_growth = float(np.clip(terminal_growth_base, -0.02, 0.06))

    sim_growth  = np.random.normal(g_base,   0.04, n_sim).clip(0.00, 0.80)
    sim_margin  = np.random.normal(target_m, 0.03, n_sim).clip(-0.10, 0.60)
    sim_wacc    = np.random.normal(w_base,   0.01, n_sim).clip(0.04, 0.25)

    sim_term_wacc = np.maximum(sim_wacc, 0.075)

    years1 = np.arange(1, 6)    
    years2 = np.arange(1, 6)    

    sg = sim_growth[:, np.newaxis]
    sm = sim_margin[:, np.newaxis]
    sw = sim_wacc[:, np.newaxis]

    # Stage 1
    revenues_s1 = rev_0 * (1 + sg) ** years1
    prev_s1 = np.zeros_like(revenues_s1)
    prev_s1[:, 0] = rev_0
    prev_s1[:, 1:] = revenues_s1[:, :-1]
    margins_s1  = margin_0 + (sm - margin_0) * (years1 / 5.0)
    nopats_s1   = revenues_s1 * margins_s1 * (1 - tax_rate)
    reinvest_s1 = np.maximum(0.0, (revenues_s1 - prev_s1) / sc)
    fcff_s1     = nopats_s1 - reinvest_s1
    df_s1       = (1 + sw) ** years1
    pv_s1       = fcff_s1 / df_s1
    sum_pv_s1   = pv_s1.sum(axis=1)

    # Stage 2
    fracs    = years2 / 5.0                                      
    g_s2     = sg + (t_growth - sg) * fracs             
    w_s2     = sw + (sim_term_wacc[:, np.newaxis] - sw) * fracs

    rev_end_s1 = revenues_s1[:, -1:]                    
    rev_s2 = np.zeros((n_sim, 5))
    rev_s2[:, 0] = (rev_end_s1 * (1 + g_s2[:, :1])).squeeze()
    for i in range(1, 5):
        rev_s2[:, i] = rev_s2[:, i-1] * (1 + g_s2[:, i])

    prev_s2 = np.zeros_like(rev_s2)
    prev_s2[:, 0] = revenues_s1[:, -1]
    prev_s2[:, 1:] = rev_s2[:, :-1]

    nopats_s2   = rev_s2 * sm * (1 - tax_rate)          
    reinvest_s2 = np.maximum(0.0, (rev_s2 - prev_s2) / sc)
    fcff_s2     = nopats_s2 - reinvest_s2

    cum_df_s1  = df_s1[:, -1:]                          
    df_s2_incr = (1 + w_s2) ** years2
    df_s2      = cum_df_s1 * df_s2_incr
    pv_s2      = fcff_s2 / df_s2
    sum_pv_s2  = pv_s2.sum(axis=1)

    # Stage 3
    rev_term    = rev_s2[:, -1] * (1 + t_growth)
    nopat_term  = rev_term * sim_margin * (1 - tax_rate)
    rr          = t_growth / sim_term_wacc
    fcff_term   = nopat_term * (1 - rr)
    denom       = sim_term_wacc - t_growth
    tv          = np.where(denom > 0.005, fcff_term / denom, np.nan)
    last_df     = df_s2[:, -1]
    pv_tv       = tv / last_df

    op_value    = sum_pv_s1 + sum_pv_s2 + np.nan_to_num(pv_tv, nan=0.0)
    eq_value    = op_value - float(net_debt) + float(non_op)
    sim_prices  = np.maximum(0.0, eq_value / shares)
    sim_prices  = sim_prices[np.isfinite(sim_prices)]
    return sim_prices

# ─────────────────────────────────────────────
# 8. STORY CONSISTENCY CHECKER
# ─────────────────────────────────────────────
def calculate_story_consistency(
    story_tam, story_moat, story_reinvestment, story_risk,
    growth_rate, target_margin, sales_to_cap, cost_of_capital
):
    score = 100
    critiques = []
    
    # Safe protection parameters to prevent Division by Zero on zero configurations
    sales_to_cap_safe = max(0.01, sales_to_cap)
    
    if "Disruptor" in story_tam and sales_to_cap_safe < 1.0:
        score -= 20
        critiques.append("High-growth disruptor story but capital efficiency is very low. Fast growth with poor efficiency requires excessive capital.")
    if "Monopoly" in story_moat and target_margin < 0.15:
        score -= 15
        critiques.append("Monopoly / network-effect moat claimed but target margin is below 15%. Genuine moats command stronger margins.")
    elif "Commodity" in story_moat and target_margin > 0.18:
        score -= 20
        critiques.append("Commodity player narrative but target margin exceeds 18%. Price competition will erode this without a moat.")
    if "High Risk" in story_risk and cost_of_capital < 0.08:
        score -= 15
        critiques.append("High-risk story but WACC is below 8%. This understates the hurdle rate investors require.")
    elif "Low Risk" in story_risk and cost_of_capital > 0.12:
        score -= 10
        critiques.append("Low-risk story but WACC exceeds 12%. This over-penalises a defensive company's cash flows.")
    if "Asset-Light" in story_reinvestment and sales_to_cap_safe < 1.2:
        score -= 15
        critiques.append("Asset-light model selected but sales-to-capital ratio is below 1.2. Digital models should convert capital efficiently.")
    return max(10, score), critiques

def confidence_label(source, consistency_score):
    if source == "live" and consistency_score >= 80:
        return "High confidence"
    if consistency_score >= 60:
        return "Medium confidence"
    return "Low confidence"

# ─────────────────────────────────────────────
# 9. SIDEBAR INPUTS
# ─────────────────────────────────────────────
st.sidebar.markdown("### 🔍 Live Data Sourcing")
ticker_input = st.sidebar.text_input("Enter Company Ticker", value="MSTR").strip().upper()

stock_data, api_success = fetch_stock_data(ticker_input)
damodaran_df = load_damodaran_industry_data()

if not api_success:
    st.sidebar.warning(f"⚠️ Yahoo Finance lookup failed. Using generic fallback for '{ticker_input}'.")

ind_str = str(stock_data["industry"])
industry_match = damodaran_df[
    damodaran_df["Industry"].astype(str).str.contains(ind_str, case=False, na=False, regex=False)
]
if not industry_match.empty:
    ind_avg_margin = float(industry_match["PreTaxOpMargin"].iloc[0])
    ind_avg_ps     = float(industry_match["PriceSales"].iloc[0])
else:
    ind_avg_margin = 0.15
    ind_avg_ps     = 3.0

default_tam, default_moat, default_reinvestment, default_risk = classify_narrative_defaults(
    stock_data, ind_avg_margin
)

st.sidebar.markdown("---")
st.sidebar.markdown("### 📖 Step 1: Tell your Business Story")

story_tam = st.sidebar.selectbox(
    "Market TAM & Growth Narrative",
    ["Market Disruptor (High growth, rapid scale, capturing massive TAM)",
     "Healthy Competitor (Steady expansion, solid regional market share)",
     "Niche Player (Slow defensive play, mature market segments)"],
    index=default_tam, key=f"tam_{stock_data['ticker']}"
)
story_moat = st.sidebar.selectbox(
    "Moat & Pricing Power",
    ["Monopoly / High Network Effects (Premium pricing, protected high margins)",
     "Sustainable Advantage (Strong brand loyalty, reasonable protection)",
     "Commodity Player (No protection, severe pricing competition)"],
    index=default_moat, key=f"moat_{stock_data['ticker']}"
)
story_reinvestment = st.sidebar.selectbox(
    "Reinvestment & Asset Intensity",
    ["Asset-Light (High efficiency, digital or licensing models)",
     "Balanced Reinvestment (Industry standard shared asset structure)",
     "Capital Intensive (Low efficiency, massive factories and CapEx)"],
    index=default_reinvestment, key=f"reinvest_{stock_data['ticker']}"
)
story_risk = st.sidebar.selectbox(
    "Risk Profile & WACC Anchor",
    ["High Risk (Emerging technology, high debt, volatile market)",
     "Average Risk (Established player, standard corporate leverage)",
     "Low Risk (Strong balance sheet, resilient recurring cash flow)"],
    index=default_risk, key=f"risk_{stock_data['ticker']}"
)

# Narrative-to-number mapping
g_anchor = max(0.01, min(0.35, float(stock_data["revenue_growth_1y"])))
calc_growth = (max(g_anchor * 1.5, 0.25) if "Disruptor" in story_tam
               else max(g_anchor, 0.08) if "Competitor" in story_tam
               else min(g_anchor * 0.4, 0.05))

a_margin = float(np.clip(stock_data["operating_margin"], -0.40, 0.80))
calc_margin = (max(a_margin + 0.05, ind_avg_margin + 0.08) if "Monopoly" in story_moat
               else max(a_margin, ind_avg_margin) if "Sustainable" in story_moat
               else max(0.02, min(a_margin * 0.4, ind_avg_margin * 0.4)))

calc_sc   = 3.0 if "Asset-Light" in story_reinvestment else 1.5 if "Balanced" in story_reinvestment else 0.7
base_wacc = 0.08 + float(stock_data["debt_to_equity"]) * 0.005
calc_wacc = float(np.clip(
    base_wacc + 0.03 if "High Risk" in story_risk
    else base_wacc - 0.015 if "Low Risk" in story_risk
    else base_wacc,
    0.04, 0.18
))

st.sidebar.markdown("---")
st.sidebar.markdown("### 🔢 Step 2: Fine-Tune the Drivers")
slider_key = f"{story_tam[:6]}_{story_moat[:6]}_{story_reinvestment[:6]}_{story_risk[:6]}_{stock_data['ticker']}"

growth_rate    = st.sidebar.slider("High Growth Rate (Yr 1-5)",             0.0, 0.80, float(calc_growth), 0.01, format="%.0f%%", key=f"g_{slider_key}")
target_margin  = st.sidebar.slider("Target Operating Margin (Yr 5)",       -0.10, 0.60, float(calc_margin), 0.01, format="%.0f%%", key=f"m_{slider_key}")
sales_to_cap   = st.sidebar.slider("Capital Efficiency (Sales-to-Capital)", 0.1, 5.0,  float(calc_sc),     0.1,  key=f"sc_{slider_key}")
cost_of_capital = st.sidebar.slider("Cost of Capital (WACC)",              0.04, 0.20, float(calc_wacc),   0.005, format="%.1f%%", key=f"w_{slider_key}")

st.sidebar.markdown("---")
st.sidebar.markdown("### 🌍 Advanced Model Settings")

tax_rate_input = st.sidebar.slider(
    "Corporate Tax Rate",
    min_value=0.05, max_value=0.35, value=0.21, step=0.01,
    format="%.0f%%",
    help="Default 21% (US). Adjust for non-US: UK=25%, Ireland=12.5%, Singapore=17%, Germany=30%"
)
terminal_growth_input = st.sidebar.slider(
    "Terminal Growth Rate",
    min_value=0.00, max_value=0.05, value=0.025, step=0.005,
    format="%.1f%%",
    help="Long-run nominal GDP growth. Damodaran typically uses 2.5% for US, lower for mature economies."
)

st.sidebar.markdown("---")
st.sidebar.markdown("### 🪙 Step 3: Non-Operating Strategic Holdings")
fetched_non_op = float(stock_data.get("non_operating_assets", 0.0)) / 1e9
strategic_treasury = st.sidebar.slider(
    "Strategic Treasury Holdings ($B)",
    0.0, max(50.0, fetched_non_op * 2.5 + 5.0), float(fetched_non_op), 0.1,
    help="Explicitly isolate strategic long-term holdings (e.g. MicroStrategy Bitcoin, Tencent equity portfolio) from operating assets."
)
non_operating_assets = strategic_treasury * 1e9

# ─────────────────────────────────────────────
# 10. MAIN DISPLAY
# ─────────────────────────────────────────────
price_tag = f" *(price as of {stock_data['price_as_of']})*" if stock_data.get("price_as_of") != "live" else " *(live)*"
st.header(f"🏢 {stock_data['company_name']} ({stock_data['ticker']})")
st.caption(
    f"Sector: {stock_data['sector']}  |  Industry: {stock_data['industry']}  |  "
    f"Data: {stock_data.get('data_source','live')}{price_tag}"
)

# Render Override Alerts dynamically to warn about GAAP mark-to-market distortions (like MSTR/BMNR)
if stock_data.get("override_note"):
    st.info(f"💡 **Corporate Advisory:** {stock_data['override_note']}")

# Tabs setup to provide elegant contextual Switching
tab1, tab2 = st.tabs(["📊 Interactive Valuation Studio", "📖 Explanation: Narrative vs. Numbers"])

with tab1:
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(f"<div class='metric-card'><div class='metric-title'>Current Price</div><div class='metric-value'>${stock_data['current_price']:.2f}</div></div>", unsafe_allow_html=True)
    with m2:
        st.markdown(f"<div class='metric-card'><div class='metric-title'>TTM Revenue</div><div class='metric-value'>${stock_data['revenue_ttm']/1e9:.2f}B</div></div>", unsafe_allow_html=True)
    with m3:
        st.markdown(f"<div class='metric-card'><div class='metric-title'>Actual Operating Margin</div><div class='metric-value'>{float(stock_data['operating_margin'])*100:.1f}%</div></div>", unsafe_allow_html=True)
    with m4:
        st.markdown(f"<div class='metric-card'><div class='metric-title'>Historical Growth</div><div class='metric-value'>{float(stock_data['revenue_growth_1y'])*100:.1f}%</div></div>", unsafe_allow_html=True)

    st.markdown("---")

    # ─────────────────────────────────────────────
    # 11. RUN 3-STAGE DCF
    # ─────────────────────────────────────────────
    dcf_result = calculate_3stage_dcf(
        rev_0=stock_data["revenue_ttm"],
        margin_0=stock_data["operating_margin"],
        target_margin=target_margin,
        growth_high=growth_rate,
        sc_ratio=sales_to_cap,
        wacc_high=cost_of_capital,
        terminal_growth=terminal_growth_input,
        tax_rate=tax_rate_input,
        return_details=True
    )

    operating_value = float(dcf_result["operating_value"]) if np.isfinite(dcf_result["operating_value"]) else np.nan
    net_debt        = float(stock_data["total_debt"]) - float(stock_data["cash"])
    equity_value    = (operating_value - net_debt + non_operating_assets) if np.isfinite(operating_value) else np.nan
    shares_out      = max(float(stock_data["shares_outstanding"]), 1.0)
    intrinsic_ps    = max(0.0, equity_value / shares_out) if np.isfinite(equity_value) else np.nan

    pv_tv           = dcf_result["pv_terminal_value"]
    tv_contribution = ((pv_tv / operating_value) * 100
                       if np.isfinite(operating_value) and operating_value > 0 and np.isfinite(pv_tv)
                       else np.nan)

    consistency_score, critiques = calculate_story_consistency(
        story_tam, story_moat, story_reinvestment, story_risk,
        growth_rate, target_margin, sales_to_cap, cost_of_capital
    )
    confidence = confidence_label(stock_data.get("data_source", "demo"), consistency_score)
    margin_var  = abs(float(target_margin) - float(stock_data["operating_margin"]))
    growth_var  = abs(float(growth_rate)   - float(stock_data["revenue_growth_1y"]))
    alignment_index = max(10, 100 - int((margin_var * 150) + (growth_var * 150)))

    # ─────────────────────────────────────────────
    # 12. NARRATIVE ALIGNMENT PANEL & OUTPUTS
    # ─────────────────────────────────────────────
    col_left, col_right = st.columns([1.1, 0.9])

    with col_left:
        st.subheader("📖 Narrative Alignment & Story Consistency")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"""
            <div class='score-card'>
                <div class='metric-title' style='color:#94a3b8;'>Coherence Score</div>
                <div class='metric-value' style='color:#38bdf8;'>{consistency_score}%</div>
                <div class='small-note'>Narrative Logical Consistency</div>
            </div>
            """, unsafe_allow_html=True)
        with c2:
            st.markdown(f"""
            <div class='score-card' style='background: linear-gradient(135deg, #334155, #1e293b);'>
                <div class='metric-title' style='color:#94a3b8;'>Alignment Index</div>
                <div class='metric-value' style='color:#34d399;'>{alignment_index}%</div>
                <div class='small-note'>Proximity to Current Fundamentals</div>
            </div>
            """, unsafe_allow_html=True)

        st.write("")
        if consistency_score == 100:
            st.markdown("<div class='success-box'>✅ **Flawless Narrative Cohesion:** All qualitative business parameters align perfectly with your implied mathematical drivers. This represents a robust scenario structure.</div>", unsafe_allow_html=True)
        else:
            for critique in critiques:
                st.markdown(f"<div class='warning-box'>{critique}</div>", unsafe_allow_html=True)

        st.markdown("### 📊 Story vs. Implied Financial Inputs")
        comparison_df = pd.DataFrame({
            "Narrative Component": ["TAM / Growth", "Moat / Pricing", "Reinvestment / CapEx", "Risk Profile"],
            "Selected Story Option": [story_tam.split(" (")[0], story_moat.split(" (")[0], story_reinvestment.split(" (")[0], story_risk.split(" (")[0]],
            "Implied Financial Preset": [f"{calc_growth*100:.1f}% Growth", f"{calc_margin*100:.1f}% Margin", f"{calc_sc:.1f} Sales-to-Capital", f"{calc_wacc*100:.1f}% WACC"],
            "Your Fine-Tuned Value": [f"{growth_rate*100:.1f}% Growth", f"{target_margin*100:.1f}% Margin", f"{sales_to_cap:.1f} Sales-to-Capital", f"{cost_of_capital*100:.1f}% WACC"]
        })
        st.table(comparison_df)

    with col_right:
        st.subheader("⚖️ Valuation Bridge & Outputs")
        
        price_pct_diff = ((intrinsic_ps - stock_data['current_price']) / stock_data['current_price']) * 100
        delta_color = "#16a34a" if price_pct_diff >= 0 else "#dc2626"
        delta_symbol = "➕" if price_pct_diff >= 0 else "➖"
        
        st.markdown(f"""
        <div style='background-color: white; padding: 24px; border-radius: 12px; border: 1px solid #eef2f6; text-align: center; box-shadow: 0 4px 12px rgba(0,0,0,0.02);'>
            <div style='font-size: 14px; text-transform: uppercase; color: #64748b; font-weight: 600;'>Implied Intrinsic Value Per Share</div>
            <div style='font-size: 48px; font-weight: 800; color: #0f172a; margin: 8px 0;'>${intrinsic_ps:.2f}</div>
            <div style='font-size: 16px; font-weight: 600; color: {delta_color};'>
                {delta_symbol} {abs(price_pct_diff):.1f}% over / under current price of ${stock_data['current_price']:.2f}
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        st.write("")
        if tv_contribution > 80.0:
            st.markdown(f"<div class='warning-box'>🚨 <strong>Terminal Value Domination:</strong> Terminal Value is <strong>{tv_contribution:.1f}%</strong> of total operating assets. Valuation is highly sensitive to terminal inputs.</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='info-box'>ℹ️ <strong>Stable Valuation Mix:</strong> Terminal Value is <strong>{tv_contribution:.1f}%</strong> of operating assets. Good balance.</div>", unsafe_allow_html=True)

        b_col1, b_col2 = st.columns(2)
        with b_col1:
            st.metric("Total Operating Assets", f"${operating_value/1e9:.2f}B")
        with b_col2:
            st.metric("Strategic Treasury Holdings", f"${non_operating_assets/1e9:.2f}B")

    st.markdown("---")
    st.subheader("🗓️ 10-Year Multi-Stage Cashflow Projection")

    records = dcf_result["records"]
    years_labels = [f"Year {r['year']} (Stage {r['stage']})" for r in records]
    projection_df = pd.DataFrame({
        "Revenue ($B)": [r["revenue"]/1e9 for r in records],
        "Operating Margin": [f"{r['margin']*100:.1f}%" for r in records],
        "Operating Profit ($B)": [r["ebit"]/1e9 for r in records],
        "Reinvestment ($B)": [r["reinvestment"]/1e9 for r in records],
        "FCFF ($B)": [r["fcff"]/1e9 for r in records],
        "PV of Cashflow ($B)": [r["pv"]/1e9 for r in records]
    }, index=years_labels)

    st.dataframe(projection_df.style.format(precision=3), use_container_width=True)

    st.markdown("---")
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.subheader("📊 Intrinsic Value Bridge")
        cumulative_pvs = sum(r["pv"] for r in records)
        
        fig_waterfall = go.Figure(go.Waterfall(
            name="Value Bridge", orientation="v",
            measure=["relative", "relative", "total", "relative", "relative", "total"],
            x=["PV of 10Yr FCFF", "PV of Terminal Value", "Operating Assets", "Non-Operating Assets", "Less Net Debt", "Common Equity Value"],
            text=[
                f"${cumulative_pvs/1e9:.2f}B", f"${pv_tv/1e9:.2f}B", f"${operating_value/1e9:.2f}B", 
                f"${non_operating_assets/1e9:.2f}B", f"${-net_debt/1e9:.2f}B", f"${equity_value/1e9:.2f}B"
            ],
            y=[cumulative_pvs/1e9, pv_tv/1e9, 0, non_operating_assets/1e9, -net_debt/1e9, 0],
            connector={"line": {"color": "rgb(63, 63, 63)"}},
        ))
        fig_waterfall.update_layout(margin=dict(t=20, b=20, l=20, r=20), yaxis_title="$ Billions", showlegend=False)
        st.plotly_chart(fig_waterfall, use_container_width=True)

    with chart_col2:
        st.subheader("🎲 Probable Value (Monte Carlo)")
        with st.spinner("Running 2,000 deep simulations..."):
            sim_prices = run_vectorized_monte_carlo(
                rev_0=stock_data["revenue_ttm"], margin_0=stock_data["operating_margin"],
                target_margin_base=target_margin, growth_base=growth_rate,
                sc_ratio=sales_to_cap, wacc_base=cost_of_capital,
                shares=stock_data["shares_outstanding"], net_debt=net_debt,
                non_op=non_operating_assets, terminal_growth_base=terminal_growth_input,
                tax_rate=tax_rate_input, n_sim=2000
            )
            
            if len(sim_prices) > 0:
                p10, p50, p90 = np.percentile(sim_prices, [10, 50, 90])
                undervalued_prob = (sim_prices > stock_data["current_price"]).mean() * 100

                st.markdown(f"🎯 **Median Simulated Value:** `${p50:.2f}` per share")
                st.markdown(f"🛡️ **Conservative (10th %):** `${p10:.2f}` | **Optimistic (90th %):** `${p90:.2f}`")

                fig_dist = px.histogram(sim_prices, nbins=50, color_discrete_sequence=['#0284c7'])
                fig_dist.add_vline(x=stock_data['current_price'], line_dash="dash", line_color="red", annotation_text="Current Market Price")
                fig_dist.update_layout(margin=dict(t=20, b=20, l=20, r=20), showlegend=False, xaxis_title="Intrinsic Value Per Share ($)")
                st.plotly_chart(fig_dist, use_container_width=True)
            else:
                st.error("Simulation failed to produce valid prices.")

    st.markdown("---")
    st.subheader("⚖️ Damodaran's Triad Check: Possible, Plausible, and Probable")
    t_col1, t_col2, t_col3 = st.columns(3)

    with t_col1:
        st.markdown("### 🛠️ Possible")
        if target_margin < 0.80 and cost_of_capital > 0.035:
            st.success("✅ **Passed Mathematical Feasibility**")
        else:
            st.error("❌ **Mathematical Boundary Breach**")

    with t_col2:
        st.markdown("### ⚖️ Plausible")
        warnings = []
        if abs(growth_rate - stock_data["revenue_growth_1y"]) > 0.25:
            warnings.append(f"• Targeted growth ({growth_rate*100:.0f}%) is far from historical ({stock_data['revenue_growth_1y']*100:.0f}%).")
        if target_margin > (ind_avg_margin + 0.15):
            warnings.append(f"• Targeted margin is exceptionally high compared to industry ({ind_avg_margin*100:.0f}%).")

        if not warnings:
            st.success("✅ **Passed Operational Plausibility**")
        else:
            st.warning("⚠️ **Ambitious Narrative Alerts:**")
            for w in warnings:
                st.markdown(w)

    with t_col3:
        st.markdown("### 🎲 Probable")
        if len(sim_prices) > 0:
            if undervalued_prob > 75:
                st.success(f"🎯 **High Likelihood of Undervaluation: {undervalued_prob:.1f}%**")
            elif undervalued_prob >= 35:
                st.info(f"⚖️ **Balanced / Fairly Valued: {undervalued_prob:.1f}%**")
            else:
                st.error(f"🚨 **High Likelihood of Overvaluation: {undervalued_prob:.1f}%**")
        else:
            st.error("Simulation failed.")

with tab2:
    st.header("📖 Aswath Damodaran's Narrative Valuation Theory")
    st.write("Valuation is not a dry exercise of typing formulas. It is a creative bridge connecting storytellers with quantitative model builders.")
    
    st.markdown("""
    ### 1. The Core Philosophy
    Many analysts fall into two separate mental traps:
    * **The Left-Brain Number Cruncher:** Builds flawless spreadsheets with 100 tabs of inputs but lacks any narrative context for *why* revenues or margins will change. Damodaran says this model has *no soul*.
    * **The Right-Brain Visionary Storyteller:** Weaves romantic, grand corporate stories (e.g. *'Our market size is infinite and we have no competitors'*) without checking if the numbers are mathematically realistic. This is a *fairy tale*.
    
    ### 2. The Four Valuation Drivers
    Every corporate narrative must map explicitly into the four engine blocks of intrinsic value:
    1. **TAM / Revenue Growth Rate:** Dictated by your story on market size, industry speed, and market share capture.
    2. **Target Operating Margin:** Dictated by your story on the company's competitive **Moat** and pricing power (defending profit from competitor erosion).
    3. **Capital Reinvestment Efficiency (Sales-to-Capital):** Dictated by your story on the business model. (e.g. asset-light software licensing scales much more efficiently than physical automotive factories).
    4. **Cost of Capital (WACC):** The discount rate reflecting market risk, currency exposure, operational stability, and leverage profiles.
    
    ### 3. Possible, Plausible, and Probable
    To audit any investment, Damodaran implements the **Triad Sanity Filter**:
    * **Possible:** Does the story break math? (e.g., target operating margins cannot physically exceed 100%).
    * **Plausible:** Is this narrative realistic relative to industrial norms and history? (e.g., if a company has historically grown at 3%, modeling 60% growth is highly implausible unless a massive structural pivot is proven).
    * **Probable:** What are the actual odds? We run **2,000 parallel Monte Carlo universes** to see the exact probability distribution of your inputs, plotting current market pricing against the resulting distribution.
    """)
