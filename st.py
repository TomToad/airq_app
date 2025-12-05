import streamlit as st
import pandas as pd
import sqlite3
import os
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time

# --- Konfiguracija stranice ---
st.set_page_config(
    page_title="Kvaliteta zraka - Zaprešić",
    page_icon="🌤️",
    layout="wide"
)

# --- Konstante ---
DB_URL = "https://www.dropbox.com/scl/fi/5m2y0t8vmj5e0mg2cc5j7/airq.db?rlkey=u9wgei8etxf3go1fke1orarom&st=v1b5nhe5&dl=1"
LOCAL_DB = "airq.db"
ZAGREB_TZ = ZoneInfo("Europe/Zagreb")

# --- Cachirana funkcija za preuzimanje baze ---
@st.cache_data(ttl=60)
def download_database():
    """Preuzmi bazu s Dropboxa"""
    try:
        # Dodaj timestamp za cache-busting
        cache_buster = f"&_t={int(time.time())}"
        url = DB_URL + cache_buster
        
        r = requests.get(url, timeout=10)
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
        # Pokušaj parsirati timestamp - radi sa svim formatima
        df["timestamp"] = pd.to_datetime(df["timestamp"], format='mixed', utc=True).dt.tz_convert(ZAGREB_TZ)
    
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

# --- Funkcija za gauge chart sa kazaljkom ---
def create_gauge_chart(value, title, max_value=150):
    """Kreira gauge chart sa kazaljkom"""
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value if pd.notna(value) else 0,
        title={'text': title, 'font': {'size': 20, 'family': 'Arial, sans-serif', 'color': '#E0E0E0'}},
        number={
            'suffix': " µg/m³", 
            'font': {'size': 28, 'family': 'Arial, sans-serif', 'color': '#FFFFFF'},
            'valueformat': '.1f'
        },
        gauge={
            'axis': {
                'range': [None, max_value],
                'tickwidth': 2,
                'tickcolor': "#666666",
                'tickfont': {'size': 13, 'color': '#AAAAAA'},
                'showticklabels': True
            },
            'bar': {
                'color': "#FF4444",
                'thickness': 0.15,
                'line': {'color': '#CC0000', 'width': 1}
            },
            'bgcolor': "#1a1a1a",
            'borderwidth': 3,
            'bordercolor': "#444444",
            'steps': [
                {'range': [0, 12], 'color': "#2E7D32"},
                {'range': [12, 35.4], 'color': "#F9A825"},
                {'range': [35.4, 55.4], 'color': "#EF6C00"},
                {'range': [55.4, max_value], 'color': "#C62828"}
            ],
            'threshold': {
                'line': {'color': "#FFFFFF", 'width': 3},
                'thickness': 0.75,
                'value': value if pd.notna(value) else 0
            }
        }
    ))
    
    fig.update_layout(
        height=300,
        margin=dict(l=20, r=20, t=70, b=20),
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        font={'color': '#E0E0E0', 'family': 'Arial, sans-serif'}
    )
    
    return fig

# --- Funkcija za area chart (temperatura/vlažnost) ---
def create_temp_humidity_chart(df, height=400):
    """Kreira area chart za temperaturu i vlažnost"""
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    # Temperatura (area)
    fig.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=df["temperature"],
            name="Temperatura",
            fill='tozeroy',
            line=dict(color='rgb(255, 99, 71)', width=2),
            fillcolor='rgba(255, 99, 71, 0.3)',
            hovertemplate='%{y:.1f} °C<extra></extra>'
        ),
        secondary_y=False
    )
    
    # Vlažnost (area)
    fig.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=df["humidity"],
            name="Vlažnost",
            fill='tozeroy',
            line=dict(color='rgb(30, 144, 255)', width=2),
            fillcolor='rgba(30, 144, 255, 0.3)',
            hovertemplate='%{y:.1f} %<extra></extra>'
        ),
        secondary_y=True
    )
    
    fig.update_xaxes(title_text="Vrijeme", tickformat="%d.%m. %H:%M")
    fig.update_yaxes(title_text="Temperatura (°C)", secondary_y=False)
    fig.update_yaxes(title_text="Vlažnost (%)", secondary_y=True)
    
    fig.update_layout(
        title="Temperatura i Vlažnost",
        height=height,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=50, r=50, t=80, b=50)
    )
    
    return fig

# --- Funkcija za stacked area (PM10 vs PM2.5) ---
def create_pm_stacked_chart(df, height=400):
    """Kreira stacked area chart za PM čestice"""
    fig = go.Figure()
    
    # PM10 baza
    fig.add_trace(go.Scatter(
        x=df["timestamp"],
        y=df["PM10"],
        name="PM10 (ukupno)",
        mode='lines',
        fill='tozeroy',
        line=dict(width=0.5, color='rgb(255, 165, 0)'),
        fillcolor='rgba(255, 165, 0, 0.3)',
        hovertemplate='PM10: %{y:.1f} µg/m³<extra></extra>'
    ))
    
    # PM2.5 overlay
    fig.add_trace(go.Scatter(
        x=df["timestamp"],
        y=df["PM2_5"],
        name="PM2.5 (fine)",
        mode='lines',
        fill='tozeroy',
        line=dict(width=0.5, color='rgb(220, 20, 60)'),
        fillcolor='rgba(220, 20, 60, 0.5)',
        hovertemplate='PM2.5: %{y:.1f} µg/m³<extra></extra>'
    ))
    
    # Referentne linije
    fig.add_hline(y=35.4, line_dash="dash", line_color="orange", 
                  annotation_text="PM2.5 prag (35.4)", annotation_position="right")
    fig.add_hline(y=55.4, line_dash="dash", line_color="red",
                  annotation_text="Nezdrava razina (55.4)", annotation_position="right")
    
    fig.update_layout(
        title="Čestične Tvari (PM10 vs PM2.5)",
        xaxis_title="Vrijeme",
        yaxis_title="Koncentracija (µg/m³)",
        height=height,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=50, r=50, t=80, b=50)
    )
    
    fig.update_xaxes(tickformat="%d.%m. %H:%M")
    
    return fig

# --- Funkcija za line chart (ostali polutanti) ---
def create_pollutants_chart(df, height=400):
    """Kreira line chart za ostale polutante"""
    fig = go.Figure()
    
    pollutants = {
        "NO2": {"color": "rgb(139, 69, 19)", "name": "NO₂"},
        "O3": {"color": "rgb(70, 130, 180)", "name": "O₃"},
        "SO2": {"color": "rgb(128, 0, 128)", "name": "SO₂"}
    }
    
    for pollutant, config in pollutants.items():
        if pollutant in df.columns and df[pollutant].notna().any():
            fig.add_trace(go.Scatter(
                x=df["timestamp"],
                y=df[pollutant],
                name=config["name"],
                mode='lines',
                line=dict(color=config["color"], width=2),
                hovertemplate=f'{config["name"]}: ' + '%{y:.1f} µg/m³<extra></extra>'
            ))
    
    fig.update_layout(
        title="Plinovi (NO₂, O₃, SO₂)",
        xaxis_title="Vrijeme",
        yaxis_title="Koncentracija (µg/m³)",
        height=height,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=50, r=50, t=80, b=50)
    )
    
    fig.update_xaxes(tickformat="%d.%m. %H:%M")
    
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

    # --- Sidebar: Kontrole ---
    with st.sidebar:
        st.header("⚙️ Postavke")
        
        # Gumb za osvježavanje
        if st.button("🔄 Osvježi podatke", use_container_width=True):
            # Obriši SVE cache-ove
            st.cache_data.clear()
            
            # Forsiraj novi download baze
            with st.spinner("Preuzimanje najnovije baze..."):
                success, msg = download_database()
                if success:
                    st.success("✅ Baza osvježena!")
                else:
                    st.warning(f"⚠️ {msg}")
            
            st.rerun()
        
        st.caption(f"⏰ Zadnje osvježavanje: {datetime.now(ZAGREB_TZ).strftime('%H:%M:%S')}")
        
        st.divider()
        
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
        now = datetime.now(ZAGREB_TZ)
        
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
        chart_height = st.slider("Visina grafikona (px):", 300, 800, 450, 50)

    # --- Učitaj podatke ---
    with st.spinner("Učitavanje podataka..."):
        df = load_data(selected_loc_id, start_datetime.isoformat(), end_datetime.isoformat())

    if df.empty:
        st.warning("📭 Nema podataka za odabrani vremenski raspon.")
    else:
        latest = df.iloc[-1]
        status, color = get_air_quality_status(latest["PM2_5"])
        
        # --- Sekcija 1: Gauge mjerači (trenutno stanje) ---
        st.header("📊 Trenutno Stanje")
        
        col1, col2, col3, col4 = st.columns(4)
        
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
                delta=f"{latest['temperature'] - df['temperature'].mean():.1f} °C" if pd.notna(latest['temperature']) else None
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
        
        # --- Sekcija 2: Area chart (temperatura/vlažnost) ---
        st.header("🌡️ Temperatura i Vlažnost")
        fig_temp = create_temp_humidity_chart(df, chart_height)
        st.plotly_chart(fig_temp, use_container_width=True)
        
        st.divider()
        
        # --- Sekcija 3: Stacked area (PM čestice) ---
        st.header("🌫️ Čestične Tvari")
        fig_pm = create_pm_stacked_chart(df, chart_height)
        st.plotly_chart(fig_pm, use_container_width=True)
        
        st.divider()
        
        # --- Sekcija 4: Line chart (ostali polutanti) ---
        st.header("🏭 Plinovi")
        fig_pollutants = create_pollutants_chart(df, chart_height)
        st.plotly_chart(fig_pollutants, use_container_width=True)
        
        st.divider()

        # --- Sirovi podaci (uvijek prikazani) ---
        st.header("📋 Tablica Podataka")
        df_display = df.drop(columns=["id", "locationID"]).sort_values("timestamp", ascending=False)
        st.dataframe(df_display, use_container_width=True, height=400)
        
        # --- Footer ---
        st.divider()
        st.caption(f"📅 Zadnje mjerenje: {latest['timestamp'].strftime('%d.%m.%Y %H:%M:%S')}")
        st.caption(f"📊 Ukupno mjerenja: {len(df)}")

except Exception as e:
    st.error(f"❌ Došlo je do greške: {e}")
    st.exception(e)