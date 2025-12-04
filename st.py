import streamlit as st
import pandas as pd
import sqlite3
import os
import requests
from datetime import datetime, timedelta

# --- Dropbox URL (direktni link ?dl=1) ---
DB_URL = "https://www.dropbox.com/scl/fi/du8k3t4720bxdm01b8eex/airq.db?rlkey=3elgzgmos9bbttezt2hg2d4ae&st=kfqkx07d&dl=1"
LOCAL_DB = "airq.db"  # lokalna kopija koju Streamlit koristi

st.title("Kvaliteta zraka - Zaprešić")

# --- Preuzmi najnoviju bazu s Dropboxa ---
try:
    r = requests.get(DB_URL)
    r.raise_for_status()
    with open(LOCAL_DB, "wb") as f:
        f.write(r.content)
    ##st.success("Baza preuzeta s Dropboxa.")
except Exception as e:
    if os.path.exists(LOCAL_DB):
        st.warning(f"Nije moguće preuzeti bazu: {e}. Koristi se lokalna kopija.")
    else:
        st.error(f"Baza podataka ne postoji i ne može se preuzeti: {e}")
        st.stop()

DB_FILE = LOCAL_DB

# --- Glavni Streamlit kod ---
try:
    # --- Poveži se na bazu ---
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    # --- Učitaj lokacije ---
    locations_df = pd.read_sql("SELECT * FROM locations", conn)
    if locations_df.empty:
        st.warning("Nema lokacija u bazi.")
        st.stop()

    # --- Odabir lokacije ---
    loc_options = locations_df.set_index("locationID")["name"].to_dict()
    selected_loc_id = st.selectbox("Odaberite lokaciju:", list(loc_options.keys()), format_func=lambda x: loc_options[x])

    # --- Odabir vremenskog raspona ---
    st.sidebar.header("Filter vremenskog raspona")
    now = datetime.now()
    default_start = now - timedelta(days=7)
    start_date = st.sidebar.date_input("Od:", default_start)
    end_date = st.sidebar.date_input("Do:", now)
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.max.time())

    # --- Dohvati mjerenja ---
    query = """
    SELECT * FROM measurements
    WHERE locationID = ?
    AND timestamp BETWEEN ? AND ?
    ORDER BY timestamp
    """
    df = pd.read_sql(query, conn, params=(selected_loc_id, start_datetime.isoformat(), end_datetime.isoformat()))

    if df.empty:
        st.warning("Nema podataka za odabrani vremenski raspon.")
    else:
        df["timestamp"] = pd.to_datetime(df["timestamp"])

        st.subheader("Temperatura i Vlažnost")
        st.line_chart(df.set_index("timestamp")[["temperature", "humidity"]])

        st.subheader("Polutanti")
        pollutants = ["NO2", "O3", "SO2", "PM10", "PM2_5"]
        st.line_chart(df.set_index("timestamp")[pollutants])

        st.subheader("Tabela podataka")
        # --- Sakrij id i locationID ---
        df_to_show = df.drop(columns=["id", "locationID"])
        st.dataframe(df_to_show.set_index("timestamp"))

    conn.close()

except Exception as e:
    st.error(f"Došlo je do greške: {e}")
