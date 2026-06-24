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
    border-left: 
