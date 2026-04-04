import math
import random
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
    margin-bottom: 12px;
}
.info-dot {
    display:inline-flex;
    align-items:center;
    justify-content:center;
    width:18px;
    height:18px;
    border-radius:50%;
    border:1px solid #9aa4b2;
    color:#cfd8e3;
    font-size:12px;
    cursor: help;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="title-box">
    <h2 style="margin:0;">European Power Grid & Weather Monitor</h2>
    <div style="opacity:0.85;">Germany • France • Belgium</div>
</div>
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
            <div style="font-size:16px; line-height:1.8;">
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
# SIDEBAR CONTROLS
# -----------------------------
st.sidebar.title("Controls")

hour = st.sidebar.slider("Simulation hour", 0, 23, 14)
weather_mode = st.sidebar.selectbox(
    "Weather pattern",
    ["Clear", "Windy", "Rain", "Storm", "Cold Wave", "Heat Wave"]
)

show_substations = st.sidebar.checkbox("Show substations", True)
show_lines = st.sidebar.checkbox("Show transmission lines", True)
show_weather = st.sidebar.checkbox("Show weather markers", True)
show_buffers = st.sidebar.checkbox("Show impact zones", False)

line_weight = st.sidebar.slider("Line thickness", 2, 10, 5)
map_theme = st.sidebar.selectbox(
    "Map style",
    ["CartoDB positron", "CartoDB dark_matter", "OpenStreetMap"]
)

st.sidebar.markdown("---")
st.sidebar.subheader("Grid assumptions")
base_demand = st.sidebar.slider("Base demand (GW)", 80, 250, 155)
renewable_share = st.sidebar.slider("Renewable share (%)", 10, 80, 42)
interconnection_strength = st.sidebar.slider("Cross-border exchange (%)", 10, 100, 70)

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
grid_demand = round(base_demand * demand_factor(hour, weather_mode), 1)
renewable_output = round((grid_demand * renewable_share / 100) * renewable_factor(weather_mode), 1)
conventional_output = round(max(0, grid_demand - renewable_output), 1)
cross_border_flow = round((grid_demand * interconnection_strength / 100) * 0.18, 1)

random.seed(hour + len(weather_mode))

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
            Load: {row['load']} GW<br>
            Temp: {row['temp']} °C<br>
            Wind: {row['wind']} km/h<br>
            Weather: {weather_icon(weather_mode)} {weather_mode}
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
                        background: rgba(255,255,255,0.80);
                        border-radius: 10px;
                        padding: 3px 6px;
                        border: 1px solid #d1d5db;
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
        weather_mode,
        "Displays the current weather scenario used in the simulation. Weather affects transmission line stress, renewable generation, and overall grid stability."
    )

    blue_card(
        "Total Demand",
        f"{total_demand:.1f} GW",
        "Total electricity consumption across the simulated grid, measured in gigawatts."
    )

    blue_card(
        "Renewable Output",
        f"{renewable_output:.1f} GW",
        "Amount of electricity generated from renewable sources such as wind and solar."
    )

    blue_card(
        "Conventional Output",
        f"{conventional_output:.1f} GW",
        "Electricity generated by conventional sources such as gas, coal, or nuclear."
    )

    blue_card(
        "Cross-border Flow",
        f"{cross_border_flow:.1f} GW",
        "Power exchanged between interconnected regions or countries."
    )

    line_health_card(healthy_lines, warning_lines, critical_lines)

    st.subheader("Node Conditions")
    st.dataframe(
        node_df[["name", "country", "load", "temp", "wind"]].rename(columns={
            "name": "Node",
            "country": "Country",
            "load": "Load (GW)",
            "temp": "Temp (°C)",
            "wind": "Wind (km/h)"
        }),
        use_container_width=True,
        height=280
    )

    st.markdown("### Transmission Line Status")
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