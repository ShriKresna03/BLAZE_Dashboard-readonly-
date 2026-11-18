"""BLAZE read-only ESP32 monitoring and research log dashboard."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from database import (
    BAND_LOW, BAND_HIGH, init_db, latest_esp32_reading, recent_readings,
    active_session, start_session, stop_session, all_sessions,
)

st.set_page_config(page_title="BLAZE | ESP32 Monitor", page_icon="🔥", layout="wide")
init_db()

CREAM = "#FFF3E3"
MUTED = "#B8A898"
EMBER = "#FF5A1F"
LEAF = "#3DDC84"
HOT = "#FF3B4E"
GRID = "rgba(255,243,227,0.10)"

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@500;700;800&family=DM+Sans:wght@400;500;600&display=swap');
.stApp { background:#17120F; color:#FFF3E3; font-family:'DM Sans',sans-serif; }
h1,h2,h3 { color:#FFF3E3; font-family:'Bricolage Grotesque',sans-serif; }
[data-testid="stSidebar"] { background:#110D0A; }
.block-container { max-width:1200px; padding-top:2rem; }
.hero-title {font-family:'Bricolage Grotesque';font-size:3rem;font-weight:800;
background:linear-gradient(90deg,#FFB020,#FF5A1F);-webkit-background-clip:text;color:transparent;}
.notice {background:rgba(255,176,32,.10);border:1px solid rgba(255,176,32,.35);
border-left:4px solid #FFB020;border-radius:10px;padding:12px 15px;color:#FFE2B0;margin:12px 0 20px;}
.metric {background:#231C17;border:1px solid #3D3027;border-radius:13px;padding:15px;min-height:105px;}
.metric-label {color:#B8A898;font-size:.85rem;}
.metric-value {color:#FFB020;font-size:1.8rem;font-weight:800;}
.metric-sub {color:#B8A898;font-size:.8rem;}
</style>
""", unsafe_allow_html=True)

def metric(label, value, sub=""):
    st.markdown(
        f'<div class="metric"><div class="metric-label">{label}</div>'
        f'<div class="metric-value">{value}</div><div class="metric-sub">{sub}</div></div>',
        unsafe_allow_html=True,
    )

def local_times(series):
    return pd.to_datetime(series, utc=True, errors="coerce").dt.tz_convert(
        datetime.now().astimezone().tzinfo
    ).dt.tz_localize(None)

st.sidebar.markdown('<div class="hero-title">BLAZE</div>', unsafe_allow_html=True)
st.sidebar.caption("ESP32 read-only research monitor")
page = st.sidebar.radio("Navigation", ["Dashboard", "Session logging", "History & CSV", "Connection guide"])

st.markdown('<div class="hero-title">BLAZE</div>', unsafe_allow_html=True)
st.caption("Biochar research · ESP32 + MAX6675 · read-only telemetry")
st.markdown(
    '<div class="notice"><b>Bench-test mode only.</b> This software receives sensor '
    'readings and records research data. It has no valve, servo, relay, heater, burner, '
    'or kiln-control functions. Use only supervised, low-voltage sensor checks with '
    'the probe at ambient temperature and all thermal/gas equipment disconnected. '
    'The 300–500 °C band is a display reference, not an operating instruction or safety limit.</div>',
    unsafe_allow_html=True,
)

if page == "Dashboard":
    st.subheader("ESP32 connection")
    latest = latest_esp32_reading()
    if latest is None or not str(latest.get("source", "")).startswith("ESP32:"):
        st.warning("No ESP32 telemetry received yet. Check the API and device connection.")
    else:
        age = (datetime.now(timezone.utc) -
               datetime.fromisoformat(latest["created_at"])).total_seconds()
        if age <= 10:
            st.success(f"ESP32 data received · last update {age:.1f} seconds ago")
        else:
            st.warning(f"ESP32 data is stale · last update {age:.1f} seconds ago")

    @st.fragment(run_every="2s")
    def live_panel():
        latest_now = latest_esp32_reading()
        st.subheader("Live sensor reading")
        if latest_now is None:
            st.info("Waiting for first sensor packet.")
            return

        temp = latest_now["temperature"]
        status = latest_now["sensor_status"]
        state = latest_now["state"]
        stamp = pd.to_datetime(latest_now["created_at"], utc=True).tz_convert(
            datetime.now().astimezone().tzinfo
        )
        age = max(0.0, (datetime.now(timezone.utc) -
                        datetime.fromisoformat(latest_now["created_at"])).total_seconds())

        a, b, c, d = st.columns(4)
        with a:
            metric("Temperature", "—" if temp is None else f"{temp:.2f} °C",
                   "MAX6675 sensor reading")
        with b:
            metric("Sensor status", status, "ESP32-reported")
        with c:
            metric("Monitor state", state, "Read-only label")
        with d:
            metric("Data age", f"{age:.1f} s", "Connection freshness")

        if status == "FAULT" or temp is None:
            st.error("Sensor fault / invalid reading received. Check the low-voltage bench wiring.")
        elif age > 10:
            st.warning("No recent packet. Check Wi-Fi, API process, and ESP32 power.")

        rows = recent_readings(300)
        df = pd.DataFrame(rows)
        if df.empty:
            return
        df = df[df["source"].astype(str).str.startswith("ESP32:")].copy()
        if df.empty:
            st.info("No ESP32 samples in the database yet.")
            return
        df["time"] = local_times(df["created_at"])
        df["temperature"] = pd.to_numeric(df["temperature"], errors="coerce")

        fig = go.Figure()
        fig.add_hrect(y0=BAND_LOW, y1=BAND_HIGH,
                      fillcolor="rgba(61,220,132,0.12)", line_width=0,
                      annotation_text="Research reference band")
        fig.add_trace(go.Scatter(
            x=df["time"], y=df["temperature"], mode="lines+markers",
            connectgaps=False, name="MAX6675",
            line=dict(color=EMBER, width=2),
            marker=dict(size=5),
        ))
        fig.update_layout(
            height=390, paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)", font=dict(color=CREAM),
            margin=dict(l=10, r=10, t=30, b=10),
            xaxis_title="Time", yaxis_title="Temperature (°C)",
        )
        fig.update_xaxes(gridcolor=GRID)
        fig.update_yaxes(gridcolor=GRID)
        st.plotly_chart(fig, use_container_width=True)

        st.caption(f"Latest packet timestamp: {stamp.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        st.dataframe(
            df.tail(10)[["created_at", "temperature", "sensor_status", "state", "source"]]
              .iloc[::-1],
            use_container_width=True, hide_index=True,
        )

    live_panel()

elif page == "Session logging":
    st.subheader("Research batch log")
    st.caption("This records measurements only. It does not start or stop any physical process.")
    current = active_session()
    if current is None:
        with st.form("new_session"):
            batch = st.text_input("Batch ID", placeholder="BLAZE-BENCH-001")
            feedstock = st.selectbox("Feedstock", [
                "Dry leaves", "Rice straw", "Mixed plant residue", "Not applicable — sensor bench test"
            ])
            mass_in = st.number_input("Initial mass (g)", min_value=0.0, value=0.0, step=1.0)
            notes = st.text_area("Notes")
            submit = st.form_submit_button("Start research log")
        if submit:
            if not batch.strip():
                st.error("Enter a batch ID.")
            else:
                start_session(batch.strip(), feedstock, mass_in, notes)
                st.rerun()
    else:
        st.success(f"Active record: {current['batch_name']}")
        st.write(f"Started: {current['started_at']}")
        mass_out = st.number_input("Final biochar mass (g), if measured",
                                   min_value=0.0, value=0.0, step=1.0)
        if st.button("Finish research log"):
            stop_session(current["id"], mass_out)
            st.rerun()

    sessions = pd.DataFrame(all_sessions(100))
    if not sessions.empty:
        st.subheader("Previous records")
        st.dataframe(sessions, use_container_width=True, hide_index=True)

elif page == "History & CSV":
    st.subheader("ESP32 telemetry history")
    raw = pd.DataFrame(recent_readings(10000))
    if raw.empty:
        st.info("No telemetry stored yet.")
    else:
        esp = raw[raw["source"].astype(str).str.startswith("ESP32:")].copy()
        st.dataframe(esp.iloc[::-1], use_container_width=True, hide_index=True)
        st.download_button(
            "Download ESP32 telemetry CSV",
            esp.to_csv(index=False).encode("utf-8"),
            "blaze_esp32_telemetry.csv", "text/csv",
        )
    sessions = pd.DataFrame(all_sessions(1000))
    if not sessions.empty:
        st.subheader("Session records")
        st.download_button(
            "Download session CSV", sessions.to_csv(index=False).encode("utf-8"),
            "blaze_sessions.csv", "text/csv",
        )

elif page == "Connection guide":
    st.subheader("Connection architecture")
    st.code("MAX6675 → ESP32 → Wi-Fi (private LAN) → FastAPI → SQLite → Streamlit")
    st.markdown("""
**What this version can do**
- Receive actual MAX6675 readings from an ESP32 during a supervised, low-voltage ambient bench test.
- Show the latest reading and plot a history.
- Store sensor faults as invalid readings.
- Export telemetry and research-session records as CSV.

**What it deliberately cannot do**
- Send commands to the ESP32.
- Open or close a valve.
- Operate a servo, relay, burner, heater, or kiln.
- Set or enforce thermal operating thresholds.

Keep the ESP32 and computer on a trusted private network. Do not port-forward the API
or expose it to the public internet. The demo token is stored in firmware and can be
read from the sketch, so use it only on a trusted test network.
""")
    st.info("For this first hardware check, leave the thermocouple at room temperature. Do not connect the probe to a heated reactor, flame, burner, LPG system, or kiln.")
