import streamlit as st
import pandas as pd
import sqlite3
import os
import requests
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
import pytz 

# --- Konfiguracija stranice ---
st.set_page_config(
    page_title="Kvaliteta zraka - Zaprešić",
    page_icon="🌤️",
    layout="wide"
)

# --- Konstante ---
DB_URL = "https://www.dropbox.com/scl/fi/5m2y0t8vmj5e0mg2cc5j7/airq.db?rlkey=u9wgei8etxf3go1fke1orarom&st=v1b5nhe5&dl=1"
LOCAL_DB = "airq.db"
ZAGREB_TZ = pytz.timezone('Europe/Zagreb') 

# --- Cachirana funkcija za preuzimanje baze ---
@st.cache_data(ttl=60)
def download_database():
    """Preuzmi bazu s Dropboxa"""
    try:
        # Dodaj timestamp za cache-busting
        # Uklanjamo cache-buster iz URL-a jer već imamo gumb za osvježavanje i st.cache_data(ttl=60)
        url = DB_URL
        
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        with open(LOCAL_DB, "wb") as f:
            f.write(r.content)
        return True, "Baza uspješno preuzeta"
    except Exception as e:
        return False, str(e)

# --- Funkcija za dohvaćanje posljednjeg mjerenja (Novi, pouzdaniji način) ---
def get_latest_measurement(location_id):
    """Čita samo posljednji redak iz baze, koristeći SQLite datetime() za ispravno sortiranje."""
    conn = sqlite3.connect(LOCAL_DB)
    query = """
    SELECT * FROM measurements
    WHERE locationID = ?
    ORDER BY datetime(timestamp) DESC  -- KLJUČNA IZMJENA
    LIMIT 1
    """
    latest_df = pd.read_sql(query, conn, params=(location_id,))
    conn.close()
    
    if latest_df.empty:
        return None

    # Vraćamo samo seriju/dict da se obradi lokalizacija u glavnom programu
    return latest_df.iloc[0].to_dict()

# --- Cachirana funkcija za učitavanje podataka ---
@st.cache_data(ttl=60)
def load_data(location_id, start_dt, end_dt):
    """Učitaj podatke iz baze"""
    conn = sqlite3.connect(LOCAL_DB)
    query = """
    SELECT * FROM measurements
    WHERE locationID = ?
    AND datetime(timestamp) BETWEEN datetime(?) AND datetime(?) -- KLJUČNA IZMJENA
    ORDER BY timestamp
    """
    df = pd.read_sql(query, conn, params=(location_id, start_dt, end_dt))
    conn.close()
    
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        
        # LOKALIZACIJA: Tretiraj naivni datum iz baze kao lokalno vrijeme
        if df["timestamp"].dt.tz is None:
            df["timestamp"] = df["timestamp"].dt.tz_localize(ZAGREB_TZ)

    return df

# --- Funkcije za vizualizaciju (ostaju iste) ---
def get_air_quality_status(pm25_value):
    # ... (kod ostaje isti)
    if pd.isna(pm25_value): return "Nema podataka", "gray"
    elif pm25_value <= 12: return "Dobra", "green"
    elif pm25_value <= 35.4: return "Umjerena", "yellow"
    elif pm25_value <= 55.4: return "Nezdrava za osjetljive", "orange"
    elif pm25_value <= 150.4: return "Nezdrava", "red"
    else: return "Vrlo nezdrava", "purple"

def create_gauge_chart(value, title, max_value=150):
    # ... (kod ostaje isti)
    fig = go.Figure(go.Indicator(...))
    return fig

def create_temp_humidity_chart(df, height=400):
    # ... (kod ostaje isti)
    fig = make_subplots(...)
    return fig

def create_pm_stacked_chart(df, height=400):
    # ... (kod ostaje isti)
    fig = go.Figure(...)
    return fig

def create_pollutants_chart(df, height=400):
    # ... (kod ostaje isti)
    fig = go.Figure(...)
    return fig

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
    
    now_tz = datetime.now(ZAGREB_TZ)

    # --- Sidebar: Kontrole ---
    with st.sidebar:
        st.header("⚙️ Postavke")
        
        # Gumb za osvježavanje
        if st.button("🔄 Osvježi podatke", use_container_width=True):
            st.cache_data.clear()
            st.cache_resource.clear() # Čistimo i resource cache za svaki slučaj
            now_tz = datetime.now(ZAGREB_TZ)
            
            with st.spinner("Preuzimanje najnovije baze..."):
                success, msg = download_database()
                if success:
                    st.success("✅ Baza osvježena!")
                else:
                    st.warning(f"⚠️ {msg}")
            
            st.rerun()
        
        st.caption(f"⏰ Zadnje osvježavanje: {now_tz.strftime('%d.%m.%Y %H:%M:%S')}")
        
        st.divider()
        
        loc_options = locations_df.set_index("locationID")["name"].to_dict()
        selected_loc_id = st.selectbox(
            "📍 Lokacija:",
            list(loc_options.keys()),
            format_func=lambda x: loc_options[x]
        )
        
        st.divider()
        
        # Vremenski raspon
        st.subheader("📅 Vremenski raspon")
        
        quick_select = st.radio(
            "Brzi odabir:",
            ["Posljednjih 24h", "Posljednjih 7 dana", "Posljednjih 30 dana", "Prilagođeno"],
            index=1
        )
        
        # Određivanje start/end datetime bazirano na now_tz
        if quick_select == "Posljednjih 24h":
            start_datetime = now_tz - timedelta(days=1)
            end_datetime = now_tz
        elif quick_select == "Posljednjih 7 dana":
            start_datetime = now_tz - timedelta(days=7)
            end_datetime = now_tz
        elif quick_select == "Posljednjih 30 dana":
            start_datetime = now_tz - timedelta(days=30)
            end_datetime = now_tz
        else:
            naive_now = now_tz.replace(tzinfo=None) 
            
            start_date = st.date_input("Od:", naive_now.date() - timedelta(days=7))
            end_date = st.date_input("Do:", naive_now.date())
            
            start_datetime = ZAGREB_TZ.localize(datetime.combine(start_date, datetime.min.time()))
            end_datetime = ZAGREB_TZ.localize(datetime.combine(end_date, datetime.max.time()))
        
        st.divider()
        
        # Dodatne opcije
        st.subheader("🎨 Prikaz")
        chart_height = st.slider("Visina grafikona (px):", 300, 800, 450, 50)

    # --- Učitaj podatke ---
    with st.spinner("Učitavanje podataka..."):
        # Šaljemo SQLite-u najsigurniji format (s razmakom), ali pošto koristimo datetime()
        # u upitu, SQLite će ga ispravno parsirati.
        start_str = start_datetime.tz_localize(None).strftime('%Y-%m-%d %H:%M:%S')
        end_str = end_datetime.tz_localize(None).strftime('%Y-%m-%d %H:%M:%S')
        
        # Učitaj podatke za grafove
        df = load_data(selected_loc_id, start_str, end_str)

        # Dohvati POSLJEDNJE mjerenje (za metrike i footer)
        latest_data_dict = get_latest_measurement(selected_loc_id)

    if df.empty or latest_data_dict is None:
        st.warning("📭 Nema podataka za odabrani vremenski raspon.")
    else:
        # Priprema latest data
        latest = pd.Series(latest_data_dict)
        latest_ts = pd.to_datetime(latest['timestamp'])
        
        # Lokaliziramo najnoviji zapis za ispravan prikaz u footeru i metricama
        if latest_ts.tz is None:
            latest_ts_aware = latest_ts.tz_localize(ZAGREB_TZ)
        else:
            latest_ts_aware = latest_ts
            
        latest['timestamp'] = latest_ts_aware # Nadopunimo Series s TZ-aware objektom
        
        status, color = get_air_quality_status(latest["PM2_5"])
        
        # --- Sekcija 1: Gauge mjerači (trenutno stanje) ---
        st.header("📊 Trenutno Stanje")
        # [Prikaz ostaje isti]
        
        col1, col2, col3, col4 = st.columns(4)
        
        # [Prikaz Gauge chartova i Metrica]

        with col1:
            if pd.notna(latest["PM2_5"]):
                fig_gauge_pm25 = create_gauge_chart(latest["PM2_5"], "PM2.5")
                st.plotly_chart(fig_gauge_pm25, use_container_width=True)
            else:
                st.metric("PM2.5", "N/A")
        
        with col2:
            if pd.notna(latest["PM10"]):
                fig_gauge_pm10 = create_gauge_chart(latest["PM10"], "PM10")
                st.plotly_chart(fig_gauge_pm10, use_container_width=True)
            else:
                st.metric("PM10", "N/A")
        
        with col3:
            st.metric(
                "🌡️ Temperatura",
                f"{latest['temperature']:.1f} °C" if pd.notna(latest['temperature']) else "N/A",
                # Delta je sada točnija jer se latest uzima izravno iz baze
                delta=f"{latest['temperature'] - df['temperature'].mean():.1f} °C" if pd.notna(latest['temperature']) and not df.empty else None
            )
            st.metric(
                "💧 Vlažnost",
                f"{latest['humidity']:.1f} %" if pd.notna(latest['humidity']) else "N/A"
            )
        
        with col4:
            st.markdown("### Kvaliteta Zraka")
            st.markdown(f"<h2 style='color: {color}; text-align: center;'>{status}</h2>", unsafe_allow_html=True)
            st.caption(f"PM2.5: {latest['PM2_5']:.1f} µg/m³" if pd.notna(latest['PM2_5']) else "Nema podataka")
        
        # Alert ako je loše
        if pd.notna(latest["PM2_5"]):
            if latest["PM2_5"] > 55.4:
                st.error("🚨 UPOZORENJE: Kvaliteta zraka je nezdrava! Preporučuje se izbjegavanje aktivnosti vani.")
            elif latest["PM2_5"] > 35.4:
                st.warning("⚠️ Kvaliteta zraka umjereno nezdrava za osjetljive skupine.")
        
        st.divider()
        
        # --- Sekcije za grafikone (ostaju iste) ---
        st.header("🌡️ Temperatura i Vlažnost")
        fig_temp = create_temp_humidity_chart(df, chart_height)
        st.plotly_chart(fig_temp, use_container_width=True)
        
        st.divider()
        
        st.header("🌫️ Čestične Tvari")
        fig_pm = create_pm_stacked_chart(df, chart_height)
        st.plotly_chart(fig_pm, use_container_width=True)
        
        st.divider()
        
        st.header("🏭 Plinovi")
        fig_pollutants = create_pollutants_chart(df, chart_height)
        st.plotly_chart(fig_pollutants, use_container_width=True)
        
        st.divider()

        # --- Sirovi podaci (uvijek prikazani) ---
        st.header("📋 Tablica Podataka")
        
        df_display = df.drop(columns=["id", "locationID"]).sort_values("timestamp", ascending=False)
        
        # Formatiranje LOKALNOG vremena za prikaz u tablici
        df_display['timestamp'] = df_display['timestamp'].dt.strftime('%d.%m.%Y %H:%M:%S')
        
        st.dataframe(df_display, use_container_width=True, height=400)
        
        # --- Footer ---
        st.divider()
        
        # Prikaz najnovijeg vremena (lokalno, naivno)
        local_timestamp = latest['timestamp'].tz_localize(None).to_pydatetime()
        st.caption(f"📅 Zadnje mjerenje: {local_timestamp.strftime('%d.%m.%Y %H:%M:%S')}")
        st.caption(f"📊 Ukupno mjerenja: {len(df)}")

except Exception as e:
    st.error(f"❌ Došlo je do greške: {e}")
    st.exception(e)