import math
import random
from datetime import datetime, timedelta

import streamlit as st
import pandas as pd
import folium
from folium.plugins import Fullscreen
from streamlit_folium import st_folium

st.set_page_config(page_title="Power Grid Weather Dashboard", layout="wide")

# -----------------------------
# PAGE STYLE
# -----------------------------
st.markdown("""
<style>
.block-container {
    padding-top: 0.6rem;
    padding-bottom: 0.6rem;
    padding-left: 1rem;
    padding-right: 1rem;
    max-width: 100%;
}
[data-testid="stSidebar"] {
    min-width: 320px;
    max-width: 380px;
}
.metric-card {
    background: linear-gradient(135deg, #081325, #0b1b36);
    padding: 18px 16px;
    border-radius: 16px;
    color: white;
    margin-bottom: 14px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.18);
}
.small-label {
    font-size: 0.95rem;
    opacity: 0.95;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 8px;
}
.big-number {
    font-size: 2rem;
    font-weight: 700;
    line-height: 1.2;
}
.title-box {
    background: linear-gradient(90deg, #0f172a, #1e293b);
    color: white;
    padding: 14px 18px;
    border-radius: 16px;
    margin-top: 40px;
    margin-bottom: 12px;
}
.info-dot {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    border: 1px solid #9aa4b2;
    color: #cfd8e3;
    font-size: 12px;
    cursor: help;
}
.section-note {
    font-size: 0.9rem;
    color: #475569;
    margin-top: -4px;
    margin-bottom: 10px;
}

[data-testid="stSidebar"][aria-expanded="false"] ~ [data-testid="stMain"] {
    margin-left: 0 !important;
}
[data-testid="stMain"] {
    transition: margin-left 0.3s ease;
}            
</style>
""", unsafe_allow_html=True)

# -----------------------------
# HELPER FUNCTIONS
# -----------------------------
def blue_card(title, value, help_text=""):
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="small-label">
                <span>{title}</span>
                <span class="info-dot" title="{help_text}">i</span>
            </div>
            <div class="big-number">{value}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

def line_health_card(healthy_count, warning_count, critical_count):
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="small-label">
                <span>Line Health</span>
                <span class="info-dot" title="Overview of transmission line conditions across the network. Lines are classified as Healthy, Warning, or Critical based on their simulated operating condition.">i</span>
            </div>
            <div style="font-size:16px; line-height:1.9;">
                <div><span style="color:#32cd32; font-size:18px;">⬤</span> Healthy: <b>{healthy_count}</b></div>
                <div><span style="color:#ffa500; font-size:18px;">⬤</span> Warning: <b>{warning_count}</b></div>
                <div><span style="color:#ff3b30; font-size:18px;">⬤</span> Critical: <b>{critical_count}</b></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

def demand_factor(hour_value, mode):
    day_curve = (
        1.0
        + 0.18 * math.sin((hour_value - 7) / 24 * 2 * math.pi)
        + 0.10 * math.sin((hour_value - 18) / 24 * 2 * math.pi)
    )
    weather_adj = {
        "Clear": 0.00,
        "Windy": -0.03,
        "Rain": 0.05,
        "Storm": 0.12,
        "Cold Wave": 0.18,
        "Heat Wave": 0.15,
    }
    return max(0.7, day_curve + weather_adj.get(mode, 0))

def renewable_factor(mode):
    return {
        "Clear": 0.95,
        "Windy": 1.20,
        "Rain": 0.75,
        "Storm": 0.65,
        "Cold Wave": 0.70,
        "Heat Wave": 0.85,
    }.get(mode, 1.0)

def weather_icon(mode):
    return {
        "Clear": "☀️",
        "Windy": "💨",
        "Rain": "🌧️",
        "Storm": "⛈️",
        "Cold Wave": "❄️",
        "Heat Wave": "🌡️",
    }.get(mode, "🌤️")

def get_line_condition(line_health):
    if line_health > 75:
        return "Healthy", "green"
    elif line_health > 50:
        return "Warning", "orange"
    else:
        return "Critical", "red"

# -----------------------------
# CURRENT TIME CONTEXT
# -----------------------------
now = datetime.now()
current_hour = now.hour
current_month_num = now.month
current_month_name = now.strftime("%B")
current_weekday_name = now.strftime("%A")
current_weekday_num = now.weekday()

# -----------------------------
# SIDEBAR CONTROLS
# -----------------------------
st.sidebar.title("Controls")

weather_mode = st.sidebar.selectbox(
    "Weather pattern",
    ["Clear", "Windy", "Rain", "Storm", "Cold Wave", "Heat Wave"]
)

prediction_horizon_label = st.sidebar.selectbox(
    "Prediction horizon",
    [
        "Next 1 hour",
        "Next 2 hours",
        "Next 3 hours",
        "Next 6 hours",
        "Next 12 hours",
        "Next 18 hours",
        "Next 24 hours",
        "Next 36 hours",
        "Next 48 hours",
        "Next 72 hours",
    ],
    index=6
)

horizon_map = {
    "Next 1 hour": 1,
    "Next 2 hours": 2,
    "Next 3 hours": 3,
    "Next 6 hours": 6,
    "Next 12 hours": 12,
    "Next 18 hours": 18,
    "Next 24 hours": 24,
    "Next 36 hours": 36,
    "Next 48 hours": 48,
    "Next 72 hours": 72,
}
prediction_horizon = horizon_map[prediction_horizon_label]

lag_feature_map = {
    1: "lag_1",
    2: "lag_2",
    3: "lag_3",
    6: "lag_6",
    12: "lag_12",
    18: "lag_18",
    24: "lag_24",
    36: "lag_36",
    48: "lag_48",
    72: "lag_72",
}
selected_lag_feature = lag_feature_map[prediction_horizon]

target_time = now + timedelta(hours=prediction_horizon)
target_hour = target_time.hour
target_month_num = target_time.month
target_month_name = target_time.strftime("%B")
target_weekday_name = target_time.strftime("%A")
target_weekday_num = target_time.weekday()

show_substations = st.sidebar.checkbox("Show substations", True)
show_lines = st.sidebar.checkbox("Show transmission lines", True)
show_weather = st.sidebar.checkbox("Show weather markers", True)
show_buffers = st.sidebar.checkbox("Show impact zones", False)

line_weight = st.sidebar.slider("Line thickness", 2, 10, 5)
map_theme = st.sidebar.selectbox(
    "Map style",
    ["CartoDB positron", "CartoDB dark_matter", "OpenStreetMap"],
    format_func=lambda x: {
        "CartoDB positron": "Light",
        "CartoDB dark_matter": "Dark",
        "OpenStreetMap": "Street"
    }[x]
)

st.sidebar.markdown("---")
st.sidebar.subheader("Current time context")
st.sidebar.write(f"**Current Hour:** {current_hour:02d}:00")
st.sidebar.write(f"**Current Weekday:** {current_weekday_name}")
st.sidebar.write(f"**Current Month:** {current_month_name}")

st.sidebar.markdown("---")
st.sidebar.subheader("Prediction target")
st.sidebar.write(f"**Forecast Horizon:** +{prediction_horizon}h")
st.sidebar.write(f"**Target Hour:** {target_hour:02d}:00")
st.sidebar.write(f"**Target Weekday:** {target_weekday_name}")
st.sidebar.write(f"**Target Month:** {target_month_name}")
st.sidebar.write(f"**Lag Feature:** {selected_lag_feature}")

st.sidebar.markdown("---")
st.sidebar.subheader("Grid assumptions")
base_demand = st.sidebar.slider("Base demand (GW)", 80, 250, 155)
renewable_share = st.sidebar.slider("Renewable share (%)", 10, 80, 42)
interconnection_strength = st.sidebar.slider("Cross-border exchange (%)", 10, 100, 70)

# -----------------------------
# HEADER
# -----------------------------
st.markdown(f"""
<div class="title-box">
    <h2 style="margin:0;">European Power Grid & Weather Monitor</h2>
    <div style="opacity:0.85;">
        Germany • France • Belgium<br>
        Current Time: {current_weekday_name}, {current_month_name} {now.day} — {current_hour:02d}:00<br>
        Forecast Horizon: +{prediction_horizon}h → Target Time: {target_hour:02d}:00 ({target_weekday_name})
    </div>
</div>
""", unsafe_allow_html=True)

# -----------------------------
# COUNTRY / NODE DATA
# -----------------------------
nodes = [
    {"name": "Brussels Hub", "country": "Belgium", "lat": 50.8503, "lon": 4.3517},
    {"name": "Antwerp Substation", "country": "Belgium", "lat": 51.2194, "lon": 4.4025},
    {"name": "Liège Grid Node", "country": "Belgium", "lat": 50.6326, "lon": 5.5797},
    {"name": "Paris Control", "country": "France", "lat": 48.8566, "lon": 2.3522},
    {"name": "Lille Substation", "country": "France", "lat": 50.6292, "lon": 3.0573},
    {"name": "Strasbourg Node", "country": "France", "lat": 48.5734, "lon": 7.7521},
    {"name": "Frankfurt Grid Hub", "country": "Germany", "lat": 50.1109, "lon": 8.6821},
    {"name": "Cologne Substation", "country": "Germany", "lat": 50.9375, "lon": 6.9603},
    {"name": "Stuttgart Node", "country": "Germany", "lat": 48.7758, "lon": 9.1829},
]

lines = [
    ("Brussels Hub", "Antwerp Substation"),
    ("Brussels Hub", "Liège Grid Node"),
    ("Brussels Hub", "Lille Substation"),
    ("Lille Substation", "Paris Control"),
    ("Paris Control", "Strasbourg Node"),
    ("Liège Grid Node", "Cologne Substation"),
    ("Cologne Substation", "Frankfurt Grid Hub"),
    ("Frankfurt Grid Hub", "Stuttgart Node"),
    ("Strasbourg Node", "Frankfurt Grid Hub"),
    ("Lille Substation", "Cologne Substation"),
]

node_lookup = {n["name"]: n for n in nodes}

# -----------------------------
# SIMULATION LOGIC
# -----------------------------
grid_demand = round(base_demand * demand_factor(target_hour, weather_mode), 1)
renewable_output = round((grid_demand * renewable_share / 100) * renewable_factor(weather_mode), 1)
conventional_output = round(max(0, grid_demand - renewable_output), 1)
cross_border_flow = round((grid_demand * interconnection_strength / 100) * 0.18, 1)

random.seed(current_hour + prediction_horizon + len(weather_mode))

node_rows = []
for n in nodes:
    country_bias = {"Belgium": 1.00, "France": 1.06, "Germany": 1.10}[n["country"]]
    local_load = round((grid_demand / len(nodes)) * country_bias * random.uniform(0.82, 1.18), 1)

    temp = {
        "Clear": random.randint(14, 24),
        "Windy": random.randint(9, 18),
        "Rain": random.randint(8, 16),
        "Storm": random.randint(7, 15),
        "Cold Wave": random.randint(-6, 4),
        "Heat Wave": random.randint(28, 38),
    }[weather_mode]

    wind = {
        "Clear": random.randint(5, 15),
        "Windy": random.randint(25, 50),
        "Rain": random.randint(15, 28),
        "Storm": random.randint(40, 75),
        "Cold Wave": random.randint(10, 24),
        "Heat Wave": random.randint(4, 14),
    }[weather_mode]

    node_rows.append({
        "name": n["name"],
        "country": n["country"],
        "lat": n["lat"],
        "lon": n["lon"],
        "load": local_load,
        "temp": temp,
        "wind": wind,
        "prediction_horizon_h": prediction_horizon,
        "target_hour": target_hour,
        "lag_feature": selected_lag_feature,
    })

node_df = pd.DataFrame(node_rows)
total_demand = round(node_df["load"].sum(), 1)

line_rows = []
for a, b in lines:
    na = node_df[node_df["name"] == a].iloc[0]
    nb = node_df[node_df["name"] == b].iloc[0]

    avg_load = (na["load"] + nb["load"]) / 2

    weather_penalty = {
        "Clear": 0,
        "Windy": 5,
        "Rain": 10,
        "Storm": 20,
        "Cold Wave": 12,
        "Heat Wave": 15,
    }[weather_mode]

    utilization = min(
        100,
        round((avg_load / 24) * 10 + weather_penalty + random.uniform(-5, 5), 1)
    )

    base_health = 100
    load_penalty = utilization * 0.6
    weather_health_penalty = weather_penalty * 0.8
    noise = random.uniform(-5, 5)

    line_health = max(
        0,
        min(100, round(base_health - load_penalty - weather_health_penalty + noise, 1))
    )

    status, color = get_line_condition(line_health)

    line_rows.append({
        "from": a,
        "to": b,
        "utilization": utilization,
        "line_health": line_health,
        "status": status,
        "color": color
    })

line_df = pd.DataFrame(line_rows)

healthy_lines = int((line_df["status"] == "Healthy").sum())
warning_lines = int((line_df["status"] == "Warning").sum())
critical_lines = int((line_df["status"] == "Critical").sum())

# -----------------------------
# LAYOUT
# -----------------------------
left, right = st.columns([4.8, 1.7], gap="medium")

with left:
    m = folium.Map(
        location=[49.8, 5.4],
        zoom_start=6,
        tiles=map_theme
    )

    Fullscreen(position="topleft").add_to(m)

    country_labels = [
        ("Belgium", 50.7, 4.7),
        ("France", 48.9, 3.1),
        ("Germany", 50.4, 8.0),
    ]

    for label, lat, lon in country_labels:
        folium.Marker(
            [lat, lon],
            icon=folium.DivIcon(html=f"""
                <div style="
                    font-size: 14px;
                    font-weight: bold;
                    color: #111827;
                    background: rgba(255,255,255,0.75);
                    padding: 4px 8px;
                    border-radius: 8px;
                    border: 1px solid #cbd5e1;
                    display: inline-block;
                ">
                    {label}
                </div>
            """)
        ).add_to(m)

    if show_lines:
        for _, row in line_df.iterrows():
            a = node_lookup[row["from"]]
            b = node_lookup[row["to"]]

            folium.PolyLine(
                locations=[[a["lat"], a["lon"]], [b["lat"], b["lon"]]],
                color=row["color"],
                weight=line_weight,
                opacity=0.85,
                tooltip=(
                    f"{row['from']} → {row['to']} | "
                    f"{row['status']} | "
                    f"Utilization: {row['utilization']}% | "
                    f"Health: {row['line_health']}"
                )
            ).add_to(m)

    if show_substations:
        for _, row in node_df.iterrows():
            if row["load"] < 18:
                node_color = "green"
            elif row["load"] < 24:
                node_color = "orange"
            else:
                node_color = "red"

            popup_html = f"""
            <b>{row['name']}</b><br>
            Country: {row['country']}<br>
            Forecast Target: {target_hour:02d}:00 ({target_weekday_name})<br>
            Load: {row['load']} GW<br>
            Temp: {row['temp']} °C<br>
            Wind: {row['wind']} km/h<br>
            Weather: {weather_icon(weather_mode)} {weather_mode}<br>
            Horizon: +{prediction_horizon}h<br>
            Lag Feature: {row['lag_feature']}
            """

            folium.CircleMarker(
                location=[row["lat"], row["lon"]],
                radius=9,
                color=node_color,
                fill=True,
                fill_opacity=0.95,
                tooltip=row["name"],
                popup=popup_html
            ).add_to(m)

            if show_buffers:
                folium.Circle(
                    location=[row["lat"], row["lon"]],
                    radius=35000,
                    color=node_color,
                    weight=1,
                    fill=True,
                    fill_opacity=0.08
                ).add_to(m)

    if show_weather:
        for _, row in node_df.iterrows():
            folium.Marker(
                [row["lat"] + 0.18, row["lon"] + 0.12],
                icon=folium.DivIcon(html=f"""
                    <div style="
                        font-size: 18px;
                        text-align:center;
                        background: rgba(255,255,255,0);
                        border-radius: 10px;
                        padding: 3px 6px;
                        
                    ">
                        {weather_icon(weather_mode)}<br>
                        <span style="font-size:11px;">{row['temp']}°C</span>
                    </div>
                """)
            ).add_to(m)

    folium.LayerControl().add_to(m)
    st_folium(m, height=760, width=None)

with right:
    blue_card(
        "Weather Mode",
        f"{weather_icon(weather_mode)} {weather_mode}",
        "Displays the current weather scenario used in the simulation. Weather affects transmission line stress, renewable generation, and overall grid stability."
    )

    blue_card(
        "Total Demand",
        f"{total_demand:.1f} GW",
        "Total electricity consumption across the simulated grid, measured in gigawatts, for the forecast target time."
    )

    blue_card(
        "Renewable Output",
        f"{renewable_output:.1f} GW",
        "Amount of electricity generated from renewable sources such as wind and solar for the forecast target time."
    )

    blue_card(
        "Conventional Output",
        f"{conventional_output:.1f} GW",
        "Electricity generated by conventional sources such as gas, coal, or nuclear to meet the remaining forecast demand."
    )

    blue_card(
        "Cross-border Flow",
        f"{cross_border_flow:.1f} GW",
        "Power exchanged between interconnected regions or countries during the forecast target period."
    )

    line_health_card(healthy_lines, warning_lines, critical_lines)

st.divider()
table_nodes, table_transmission = st.columns(2)

with table_nodes:
    st.subheader("Node Conditions")
    st.markdown(
        f"<div class='section-note'>Forecasted node conditions for {target_weekday_name} at {target_hour:02d}:00.</div>",
        unsafe_allow_html=True
    )
    st.dataframe(
        node_df[[
            "name", "country", "load", "temp", "wind",
            "prediction_horizon_h", "target_hour", "lag_feature"
        ]].rename(columns={
            "name": "Node",
            "country": "Country",
            "load": "Load (GW)",
            "temp": "Temp (°C)",
            "wind": "Wind (km/h)",
            "prediction_horizon_h": "Horizon (h)",
            "target_hour": "Target Hour",
            "lag_feature": "Lag Feature",
        }),
        use_container_width=True,
        height=290
    )

with table_transmission:
    st.markdown("### Transmission Line Status")
    st.markdown(
        f"<div class='section-note'>Transmission status forecast for the target time window (+{prediction_horizon}h).</div>",
        unsafe_allow_html=True
    )
    st.dataframe(
        line_df[["from", "to", "utilization", "line_health", "status"]].rename(columns={
            "from": "From",
            "to": "To",
            "utilization": "Utilization (%)",
            "line_health": "Line Health",
            "status": "Status"
        }),
        use_container_width=True,
        height=240
    )