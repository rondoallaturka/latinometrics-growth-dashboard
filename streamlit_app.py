"""Latinometrics Growth KPIs dashboard.

Reads data/growth-metrics.csv (refreshed weekly from the latinometrics-website
private repo's scripts/growth_dashboard.py) and renders a lightweight visual
dashboard for internal use.

Deployed on Streamlit Community Cloud.
"""

from pathlib import Path

import pandas as pd
import streamlit as st

CSV = Path(__file__).resolve().parent / "data" / "growth-metrics.csv"

st.set_page_config(page_title="Latinometrics Growth KPIs", layout="wide")
st.title("Latinometrics Growth KPIs")
st.caption(
    "Tracks the holy-grail metrics from the Growth Initiative §8.3. "
    "Refreshed weekly."
)


@st.cache_data(ttl=3600)
def load_data():
    df = pd.read_csv(CSV, parse_dates=["date"])
    return df.set_index("date").sort_index()


df = load_data()
totals = df.sum(numeric_only=True)
recent = df.tail(7).sum(numeric_only=True)

st.markdown(f"**Window:** {df.index.min().date()} → {df.index.max().date()}  ·  {len(df)} days")

col_es, col_sc, col_disc = st.columns(3)
col_es.metric(
    "Engaged sessions (90d)",
    f"{int(totals.engaged_sessions):,}",
    f"{int(recent.engaged_sessions):,} last 7d",
)
col_sc.metric(
    "Search clicks (90d)",
    f"{int(totals.search_clicks):,}",
    f"{int(totals.search_impressions):,} impressions",
)

discover_clicks = int(totals.discover_clicks)
discover_imp = int(totals.discover_impressions)
if discover_clicks == 0 and discover_imp == 0:
    col_disc.metric("Discover (90d)", "0 / 0", "Not in Discover yet", delta_color="off")
else:
    col_disc.metric(
        "Discover clicks/imp (90d)",
        f"{discover_clicks:,} / {discover_imp:,}",
        f"{int(recent.discover_clicks):,} clicks last 7d",
    )

st.divider()

st.subheader("Engaged sessions")
st.line_chart(df["engaged_sessions"], height=250)

st.subheader("Search")
col1, col2 = st.columns(2)
with col1:
    st.caption("Clicks")
    st.line_chart(df["search_clicks"], height=220)
with col2:
    st.caption("Impressions")
    st.line_chart(df["search_impressions"], height=220)

st.subheader("Discover (the binary KPI)")
col1, col2 = st.columns(2)
with col1:
    st.caption("Clicks")
    st.line_chart(df["discover_clicks"], height=220)
with col2:
    st.caption("Impressions")
    st.line_chart(df["discover_impressions"], height=220)

st.subheader("Avg session duration (seconds)")
st.line_chart(df["avg_session_duration_s"], height=220)

with st.expander("Raw data"):
    st.dataframe(df, use_container_width=True)
