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
DB_URL = "https://www.dropbox.com/scl/fi/5m2y0t8vmj5e0mg2cc5j7/airq.db?rlkey=u9wgei8etxf3go1fke1orarom&dl=1"
LOCAL_DB = "airq.db"
ZAGREB_TZ = pytz.timezone('Europe/Zagreb')
UTC_TZ = pytz.timezone('UTC')

# --- Cachirana funkcija za preuzimanje baze ---
@st.cache_data(ttl=60)
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
        # Podesi Pandas da čita ISO format ispravno i dodaj mu TZ informaciju
        # 1. Konvertiraj stupac u datetime objekte
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        
        # 2. Pretpostavi da je naivni datum u bazi STVARNO UTC vrijeme.
        if df["timestamp"].dt.tz is None:
            df["timestamp"] = df["timestamp"].dt.tz_localize(UTC_TZ, ambiguous='NaT', nonexistent='NaT')
        
        # 3. Konvertiraj ga u lokalnu vremensku zonu (CET/CEST)
        df["timestamp"] = df["timestamp"].dt.tz_convert(ZAGREB_TZ)
        
    return df

# --- Funkcije za vizualizaciju (skraćeno radi preglednosti) ---
def get_air_quality_status(pm25_value):
    # ... (kod ostaje isti)
    if pd.isna(pm25_value): return "Nema podataka", "gray"
    elif pm25_value <= 12: return "Dobra", "green"
    elif pm25_value <= 35.4: return "Umjerena", "yellow"
    elif pm25_value <= 55.4: return "Nezdrava za osjetljive", "orange"
    elif pm25_value <= 150.4: return "Nezdrava", "red"
    else: return "Vrlo nezdrava", "purple"

# ... (Ostale funkcije za grafikone su nepromijenjene) ...

# --- Glavni program ---
st.title("🌤️ Kvaliteta zraka - Zaprešić")

with st.spinner("Preuzimanje najnovijih podataka..."):
    success, message = download_database()
    if not success:
        if os.path.exists(LOCAL_DB):
            st.warning(f"⚠️ Nije moguće preuzeti najnoviju bazu: {message}. Koristi se lokalna kopija.")
        else:
            st.error(f"❌ Baza ne postoji i ne može se preuzeti: {message}")
            st.stop()

try:
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
        
        if st.button("🔄 Osvježi podatke", use_container_width=True):
            st.cache_data.clear()
            now_tz = datetime.now(ZAGREB_TZ)
            with st.spinner("Preuzimanje najnovije baze..."):
                download_database()
            st.rerun()
        
        st.caption(f"⏰ Zadnje osvježavanje: {now_tz.strftime('%d.%m.%Y %H:%M:%S')}")
        
        st.divider()
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
        # KLJUČNA IZMJENA ZA UPIT:
        # Prvo konvertiramo TZ-aware datume u UTC, jer baza pohranjuje naivno vrijeme koje se čini da odgovara UTC-u.
        # Zatim koristimo standardni SQLite format 'YYYY-MM-DD HH:MM:SS' za upit.
        
        start_utc = start_datetime.astimezone(UTC_TZ)
        end_utc = end_datetime.astimezone(UTC_TZ)
        
        # Koristimo ISO format s T za upit (jer se taj format koristi u bazi)
        start_str = start_utc.strftime('%Y-%m-%dT%H:%M:%S')
        end_str = end_utc.strftime('%Y-%m-%dT%H:%M:%S')
        
        df = load_data(selected_loc_id, start_str, end_str)

    if df.empty:
        st.warning("📭 Nema podataka za odabrani vremenski raspon.")
    else:
        latest = df.iloc[-1]
        status, color = get_air_quality_status(latest["PM2_5"])
        
        # --- (Prikaz mjerača i grafikona - nepromijenjeno) ---
        
        # --- Sirovi podaci (uvijek prikazani) ---
        st.header("📋 Tablica Podataka")
        
        df_display = df.drop(columns=["id", "locationID"]).sort_values("timestamp", ascending=False).copy()
        
        # KONAČNA ISPRAVKA ZA TABLICU:
        # Konvertiraj TZ-aware vrijeme u Naive (bez TZ) LOKALNO vrijeme i formatiraj.
        # Ovo je logički ispravno: datum u bazi je 11:22, mi ga pretvorimo u TZ-aware objekt 11:22 CET,
        # zatim uklonimo oznaku TZ za prikaz, ostavljajući 11:22.
        df_display['timestamp'] = df_display['timestamp'].dt.tz_localize(None).dt.strftime('%d.%m.%Y %H:%M:%S')
        
        st.dataframe(df_display, use_container_width=True, height=400)
        
        # --- Footer ---
        st.divider()
        
        local_timestamp = latest['timestamp'].tz_localize(None).to_pydatetime()
        
        st.caption(f"📅 Zadnje mjerenje: {local_timestamp.strftime('%d.%m.%Y %H:%M:%S')}")
        st.caption(f"📊 Ukupno mjerenja: {len(df)}")

except Exception as e:
    st.error(f"❌ Došlo je do greške: {e}")
    st.exception(e)