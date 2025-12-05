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
# Koristimo osnovni Dropbox URL za dl=1
DB_URL = "https://www.dropbox.com/scl/fi/5m2y0t8vmj5e0mg2cc5j7/airq.db?rlkey=u9wgei8etxf3go1fke1orarom&dl=1"
LOCAL_DB = "airq.db"
ZAGREB_TZ = pytz.timezone('Europe/Zagreb')

# --- Cachirana funkcija za preuzimanje baze ---
@st.cache_data(ttl=60)
def download_database():
    """Preuzmi bazu s Dropboxa"""
    try:
        # Koristimo jednostavni URL jer je cache-busting unutar Streamlita dovoljan
        r = requests.get(DB_URL, timeout=10)
        r.raise_for_status()
        with open(LOCAL_DB, "wb") as f:
            f.write(r.content)
        return True, "Baza uspješno preuzeta"
    except Exception as e:
        return False, str(e)

# --- Cachirana funkcija za učitavanje podataka ---
@st.cache_data(ttl=60)
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
        
        # LOKALIZACIJA: pretpostavljamo da su zapisi u bazi snimljeni kao lokalno vrijeme
        if df["timestamp"].dt.tz is None:
            df["timestamp"] = df["timestamp"].dt.tz_localize(ZAGREB_TZ, ambiguous='NaT', nonexistent='NaT')
        
    return df

# --- Funkcije za vizualizaciju (nepromijenjeno) ---
def get_air_quality_status(pm25_value):
    # ... (kod ostaje isti)
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

# Ostavljam prazne funkcije radi preglednosti, ali one su nepromijenjene
def create_gauge_chart(value, title, max_value=150):
    fig = go.Figure(go.Indicator(mode="gauge+number", value=value))
    fig.update_layout(height=300)
    return fig

def create_temp_humidity_chart(df, height=400):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    return fig

def create_pm_stacked_chart(df, height=400):
    fig = go.Figure()
    return fig

def create_pollutants_chart(df, height=400):
    fig = go.Figure()
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

    # --- Sidebar: Kontrole (nepromijenjeno) ---
    with st.sidebar:
        st.header("⚙️ Postavke")
        
        # Gumb za osvježavanje
        if st.button("🔄 Osvježi podatke", use_container_width=True):
            st.cache_data.clear()
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
        # ... (ostale kontrole)
        loc_options = locations_df.set_index("locationID")["name"].to_dict()
        selected_loc_id = st.selectbox("📍 Lokacija:", list(loc_options.keys()), format_func=lambda x: loc_options[x])
        st.divider()
        
        st.subheader("📅 Vremenski raspon")
        quick_select = st.radio("Brzi odabir:", ["Posljednjih 24h", "Posljednjih 7 dana", "Posljednjih 30 dana", "Prilagođeno"], index=1)
        
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
        st.subheader("🎨 Prikaz")
        chart_height = st.slider("Visina grafikona (px):", 300, 800, 450, 50)

    # --- Učitaj podatke ---
    with st.spinner("Učitavanje podataka..."):
        start_str = start_datetime.strftime('%Y-%m-%d %H:%M:%S')
        end_str = end_datetime.strftime('%Y-%m-%d %H:%M:%S')
        df = load_data(selected_loc_id, start_str, end_str)

    if df.empty:
        st.warning("📭 Nema podataka za odabrani vremenski raspon.")
    else:
        latest = df.iloc[-1]
        status, color = get_air_quality_status(latest["PM2_5"])
        
        # --- (Grafikoni - nepromijenjeno) ---
        # [Preskočeno radi preglednosti]
        
        # --- Sirovi podaci (uvijek prikazani) ---
        st.header("📋 Tablica Podataka")
        
        # KREIRANJE KOPIJE ZA PRIKAZ
        df_display = df.drop(columns=["id", "locationID"]).sort_values("timestamp", ascending=False).copy()
        
        # KLJUČNA ISPRAVKA ZA TABLICU:
        # 1. Konvertiraj TZ-aware vrijeme u Naive (bez TZ) objekt, zadržavajući LOKALNO vrijeme (npr. 11:23)
        # 2. Formatiraj taj Naive objekt kao string
        df_display['timestamp'] = df_display['timestamp'].dt.tz_localize(None).dt.strftime('%d.%m.%Y %H:%M:%S')

        st.dataframe(df_display, use_container_width=True, height=400)
        
        # --- Footer ---
        st.divider()
        
        # Footer ispravka: Konvertiraj latest u naivni datetime, pa formatiraj
        # to_pydatetime() obično radi isto, ali ovdje radimo eksplicitno
        local_timestamp = latest['timestamp'].tz_localize(None).to_pydatetime()
        
        st.caption(f"📅 Zadnje mjerenje: {local_timestamp.strftime('%d.%m.%Y %H:%M:%S')}")
        st.caption(f"📊 Ukupno mjerenja: {len(df)}")

except Exception as e:
    st.error(f"❌ Došlo je do greške: {e}")
    st.exception(e)