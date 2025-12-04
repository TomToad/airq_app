import streamlit as st
import pandas as pd
import sqlite3
import os
import requests
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go

# --- Konfiguracija stranice ---
st.set_page_config(
    page_title="Kvaliteta zraka - Zaprešić",
    page_icon="🌤️",
    layout="wide"
)

# --- Konstante ---
DB_URL = "https://www.dropbox.com/scl/fi/5m2y0t8vmj5e0mg2cc5j7/airq.db?rlkey=u9wgei8etxf3go1fke1orarom&st=v1b5nhe5&dl=1"
LOCAL_DB = "airq.db"

# --- Cachirana funkcija za preuzimanje baze ---
@st.cache_data(ttl=600)  # Cache na 10 minuta
def download_database():
    """Preuzmi bazu s Dropboxa"""
    try:
        r = requests.get(DB_URL, timeout=10)
        r.raise_for_status()
        with open(LOCAL_DB, "wb") as f:
            f.write(r.content)
        return True, "Baza uspješno preuzeta"
    except Exception as e:
        return False, str(e)

# --- Cachirana funkcija za učitavanje podataka ---
@st.cache_data(ttl=300)  # Cache na 5 minuta
def load_data(location_id, start_dt, end_dt):
    """Učitaj podatke iz baze"""
    conn = sqlite3.connect(LOCAL_DB)
    query = """
    SELECT * FROM measurements
    WHERE locationID = ?
    AND timestamp BETWEEN ? AND ?
    ORDER BY timestamp
    """
    df = pd.read_sql(query, conn, params=(location_id, start_dt, end_dt))
    conn.close()
    
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    
    return df

# --- Funkcija za kvalitativnu ocjenu ---
def get_air_quality_status(pm25_value):
    """Odredi kvalitetu zraka prema PM2.5"""
    if pd.isna(pm25_value):
        return "Nema podataka", "gray"
    elif pm25_value <= 12:
        return "Dobra", "green"
    elif pm25_value <= 35.4:
        return "Umjerena", "yellow"
    elif pm25_value <= 55.4:
        return "Nezdrava za osjetljive", "orange"
    elif pm25_value <= 150.4:
        return "Nezdrava", "red"
    else:
        return "Vrlo nezdrava", "purple"

# --- Glavni program ---
st.title("🌤️ Kvaliteta zraka - Zaprešić")

# Preuzmi bazu
with st.spinner("Preuzimanje najnovijih podataka..."):
    success, message = download_database()
    if not success:
        if os.path.exists(LOCAL_DB):
            st.warning(f"⚠️ Nije moguće preuzeti najnoviju bazu: {message}. Koristi se lokalna kopija.")
        else:
            st.error(f"❌ Baza ne postoji i ne može se preuzeti: {message}")
            st.stop()

try:
    # Učitaj lokacije
    conn = sqlite3.connect(LOCAL_DB)
    locations_df = pd.read_sql("SELECT * FROM locations", conn)
    conn.close()
    
    if locations_df.empty:
        st.warning("Nema lokacija u bazi.")
        st.stop()

    # --- Sidebar: Kontrole ---
    with st.sidebar:
        st.header("⚙️ Postavke")
        
        # Odabir lokacije
        loc_options = locations_df.set_index("locationID")["name"].to_dict()
        selected_loc_id = st.selectbox(
            "📍 Lokacija:",
            list(loc_options.keys()),
            format_func=lambda x: loc_options[x]
        )
        
        st.divider()
        
        # Vremenski raspon
        st.subheader("📅 Vremenski raspon")
        now = datetime.now()
        
        # Brzi odabir
        quick_select = st.radio(
            "Brzi odabir:",
            ["Posljednjih 24h", "Posljednjih 7 dana", "Posljednjih 30 dana", "Prilagođeno"],
            index=1
        )
        
        if quick_select == "Posljednjih 24h":
            start_datetime = now - timedelta(days=1)
            end_datetime = now
        elif quick_select == "Posljednjih 7 dana":
            start_datetime = now - timedelta(days=7)
            end_datetime = now
        elif quick_select == "Posljednjih 30 dana":
            start_datetime = now - timedelta(days=30)
            end_datetime = now
        else:
            start_date = st.date_input("Od:", now - timedelta(days=7))
            end_date = st.date_input("Do:", now)
            start_datetime = datetime.combine(start_date, datetime.min.time())
            end_datetime = datetime.combine(end_date, datetime.max.time())
        
        st.divider()
        
        # Dodatne opcije
        st.subheader("🎨 Prikaz")
        show_raw_data = st.checkbox("Prikaži sirove podatke", value=False)
        chart_height = st.slider("Visina grafikona (px):", 300, 800, 500, 50)

    # --- Učitaj podatke ---
    with st.spinner("Učitavanje podataka..."):
        df = load_data(selected_loc_id, start_datetime.isoformat(), end_datetime.isoformat())

    if df.empty:
        st.warning("📭 Nema podataka za odabrani vremenski raspon.")
    else:
        # --- Metrika: Trenutna kvaliteta zraka ---
        latest = df.iloc[-1]
        status, color = get_air_quality_status(latest["PM2_5"])
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "🌡️ Temperatura",
                f"{latest['temperature']:.1f} °C" if pd.notna(latest['temperature']) else "N/A"
            )
        
        with col2:
            st.metric(
                "💧 Vlažnost",
                f"{latest['humidity']:.1f} %" if pd.notna(latest['humidity']) else "N/A"
            )
        
        with col3:
            st.metric(
                "🌫️ PM2.5",
                f"{latest['PM2_5']:.1f} µg/m³" if pd.notna(latest['PM2_5']) else "N/A"
            )
        
        with col4:
            st.markdown(f"### Kvaliteta zraka")
            st.markdown(f"<h3 style='color: {color};'>{status}</h3>", unsafe_allow_html=True)

        st.divider()

        # --- Graf: Temperatura i Vlažnost ---
        st.subheader("🌡️ Temperatura i Vlažnost")
        
        fig_temp = go.Figure()
        fig_temp.add_trace(go.Scatter(
            x=df["timestamp"], 
            y=df["temperature"],
            name="Temperatura (°C)",
            line=dict(color='red', width=2),
            yaxis="y"
        ))
        fig_temp.add_trace(go.Scatter(
            x=df["timestamp"], 
            y=df["humidity"],
            name="Vlažnost (%)",
            line=dict(color='blue', width=2),
            yaxis="y2"
        ))
        
        fig_temp.update_layout(
            height=chart_height,
            xaxis=dict(title="Vrijeme", tickformat="%d.%m. %H:%M"),
            yaxis=dict(title="Temperatura (°C)", side="left"),
            yaxis2=dict(title="Vlažnost (%)", overlaying="y", side="right"),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        st.plotly_chart(fig_temp, use_container_width=True)

        # --- Graf: Polutanti ---
        st.subheader("🏭 Koncentracija polutanata")
        
        pollutants = ["NO2", "O3", "SO2", "PM10", "PM2_5"]
        pollutant_labels = {
            "NO2": "NO₂ (µg/m³)",
            "O3": "O₃ (µg/m³)",
            "SO2": "SO₂ (µg/m³)",
            "PM10": "PM10 (µg/m³)",
            "PM2_5": "PM2.5 (µg/m³)"
        }
        
        fig_pollutants = go.Figure()
        
        for pollutant in pollutants:
            if pollutant in df.columns and df[pollutant].notna().any():
                fig_pollutants.add_trace(go.Scatter(
                    x=df["timestamp"],
                    y=df[pollutant],
                    name=pollutant_labels.get(pollutant, pollutant),
                    mode='lines',
                    line=dict(width=2)
                ))
        
        fig_pollutants.update_layout(
            height=chart_height,
            xaxis=dict(title="Vrijeme", tickformat="%d.%m. %H:%M"),
            yaxis=dict(title="Koncentracija (µg/m³)"),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        st.plotly_chart(fig_pollutants, use_container_width=True)

        # --- Statistika ---
        st.subheader("📊 Statistički pregled")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Temperatura**")
            temp_stats = df["temperature"].describe()
            st.dataframe(temp_stats.to_frame().T, use_container_width=True)
        
        with col2:
            st.markdown("**PM2.5**")
            pm25_stats = df["PM2_5"].describe()
            st.dataframe(pm25_stats.to_frame().T, use_container_width=True)

        # --- Sirovi podaci ---
        if show_raw_data:
            st.subheader("📋 Tablica podataka")
            df_display = df.drop(columns=["id", "locationID"]).sort_values("timestamp", ascending=False)
            st.dataframe(df_display, use_container_width=True, height=400)
        
        # --- Info o zadnjem ažuriranju ---
        st.caption(f"Zadnje mjerenje: {latest['timestamp'].strftime('%d.%m.%Y %H:%M:%S')}")

except Exception as e:
    st.error(f"❌ Došlo je do greške: {e}")
    st.exception(e)