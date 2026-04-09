import time
import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta
from geopy.distance import geodesic
from supabase import create_client, Client

# ---------------------------
# Secrets
# ---------------------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
GOOGLE_MAPS_API_KEY = st.secrets["GOOGLE_MAPS_API_KEY"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------------------
# App config
# ---------------------------

st.sidebar.title("Filters")

st.sidebar.markdown("KPI Selection")

show_amenities = st.sidebar.checkbox("Amenities", True)
show_transport = st.sidebar.checkbox("Transport", True)

st.markdown("## Demografy")
st.markdown("### Livability Intelligence Dashboard")
st.caption("Compare suburbs using real-time amenities, transport & location intelligence")


st.divider()

# ---------------------------
# Inputs
# ---------------------------
st.subheader("Select Suburbs to Compare")

col1, col2 = st.columns(2)

with col1:
    suburb_a = st.text_input(
        "Suburb A", 
        placeholder="e.g Sunnybank, QLD"
    )

with col2:
    suburb_b = st.text_input(
        "Suburb B",
        placeholder="e.g. Rochedale, QLD"
    )

st.divider()
run_analysis = st.button("Run Livability Comparison", use_container_width=True)


# ---------------------------
# Helpers
# ---------------------------
def geocode(suburb: str):
    """Return (lat, lng) or None if invalid."""
    suburb = (suburb or "").strip()

    # Make results more reliable 
    if "australia" not in suburb.lower():
        suburb = f"{suburb}, Australia"
    
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": suburb, "key": GOOGLE_MAPS_API_KEY}
    r = requests.get(url, params=params, timeout=15)
    data = r.json()

    if data.get("status") != "OK" or not data.get("results"):
        # Debug (temporary)
        ##st.write("DEBUG geocode status:", data.get("status"))
        ##st.write("DEBUG geocode error_message:", data.get("error_message"))
        ##st.write("DEBUG geocode address used:", suburb)
        return None
    loc = data["results"][0]["geometry"]["location"]
    return (loc["lat"], loc["lng"])

def get_or_create_suburb(suburb_name: str):
    suburb_name = (suburb_name or "").strip()

    res = (
        supabase.table("suburbs")
        .select("lat, lng")
        .eq("name", suburb_name)
        .limit(1)
        .execute()
    )

    rows = getattr(res, "data", None) or []

    if rows:
        lat = rows[0].get("lat")
        lng = rows[0].get("lng")
        if lat is not None and lng is not None:
            return(lat, lng)
        # If row exists but coords missing, treat as not usable and re-geocode
    
    loc = geocode(suburb_name)
    if not loc:
        return None
    
    supabase.table("suburbs").upsert({
        "name": suburb_name,
        "lat": loc[0],
        "lng": loc[1],
        "updated_at": datetime.now(timezone.utc).isoformat()
    }, on_conflict="name").execute()

    return loc

def nearby_count(lat: float, lng: float, place_type: str, radius: int = 2000) -> int:
    """Places API (New) - Nearby Search Return count of places for the included type."""
    url = "https://places.googleapis.com/v1/places:searchNearby"

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        # We only need place ids to count results
        #"X-Goog-FieldMask": "places.id,nextPageToken",
        "X-Goog-FieldMask": "places.id",
    }

    payload = {
        "includedTypes": [place_type],
        "maxResultCount": 20, 
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": float(radius),
            }
        },
    }

    r = requests.post(url, headers=headers, json=payload, timeout=20)
    data = r.json()

    # Helpful debug if something is wrong
    if r.status_code != 200:
        ##st.write(f"DEBUG {place_type} status_code:", r.status_code)
        ##st.write(f"DEBUG {place_type} response:", data)
        return 0
    
    return len(data.get("places", []))
    

def get_cached_metrics(suburb_name: str, max_age_hours: int = 24):
    """Return cached row from suburb_metrics if it exists and is recent enough."""
    res = (
        supabase.table("suburb_metrics")
        .select("*")
        .eq("suburb_name", suburb_name)
        .limit(1)
        .execute()
    )

    rows = getattr(res, "data", None) or []
    if not rows:
        return None
    
    row = rows[0]
    updated_at = row.get("updated_at")

    # If updated_at missing, treat as stale
    if not updated_at:
        return None
    
    # Supabase returns ISO strings; parse safely
    try:
        dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except Exception:
        return None
    
    # If datetime is naive, assume UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now_utc = datetime.now(timezone.utc)
    if now_utc - dt > timedelta(hours=max_age_hours):
        return None
    return row


def insert_raw_history(suburb_name: str, place_type: str, raw_json: dict):
    """Optional: store raw history in raw_places_data."""
    payload = {
        "suburb_name": suburb_name,
        "place_type": place_type,
        "raw_json": raw_json,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return supabase.table("raw_places_data").insert(payload).execute()


if run_analysis:
    if not suburb_a.strip() or not suburb_b.strip():
        st.error("Please enter both suburbs.")
        st.stop()
    progress = st.progress(0, text="Preparing analysis. . .")
    progress.progress(20, text="Geocoding suburbs. . .")
    progress.progress(40, text="Checking cached results. . .")
    progress.progress(60, text="Fetching nearby places. . .")
    progress.progress(80, text="Generating dashboard. . .")
    progress.progress(100, text="Done")
    loc_a = get_or_create_suburb(suburb_a)
    loc_b = get_or_create_suburb(suburb_b)
    progress.progress(25, text="Validating suburbs…")

    if not loc_a:
        st.error(f"Suburb A could not be found: '{suburb_a}'. Try: 'Sunnybank, QLD, Australia'")
        st.stop()
    
    if not loc_b:
        st.error(f"Suburb B could not be found: '{suburb_b}'. Try: 'Sunnybank, QLD, Australia'")
        st.stop()

    st.success("Suburbs validated!")
    ##///st.caption(f"{suburb_a} coordinates: {loc_a[0]:.5f}, {loc_a[1]:.5f}")
    ##///st.caption(f"{suburb_b} coordinates: {loc_b[0]:.5f}, {loc_b[1]:.5f}")

    # Step 2 per brief/wireframe: cache check → fetch if needed → transform → render
    progress.progress(40, text="Checking cache…")

    cached_a = get_cached_metrics(suburb_a)
    cached_b = get_cached_metrics(suburb_b)

    AMENITY_TYPES = [
        "supermarket", 
        "restaurant", 
        "pharmacy", 
        "gym",
    ]

    TRANSPORT_TYPES = [
        "train_station",
        "bus_station"
    ]

    def build_metrics(suburb_name: str, loc: tuple, cached_row):
        if cached_row:
            counts = {
                "supermarket": cached_row.get("supermarket_count", 0),
                "restaurant": cached_row.get("restaurant_count", 0),
                "pharmacy": cached_row.get("pharmacy_count", 0),
                "gym": cached_row.get("gym_count", 0),
            }

            transport_counts = {
                "train_station": cached_row.get("train_station_count", 0),
                "bus_station": cached_row.get("bus_station_count", 0),
            }

            amenities_score = cached_row.get("amenities_score", 0.0)
            transport_score = cached_row.get("transport_score", 0.0)

            return counts, transport_counts, amenities_score, transport_score, True

        # Cache miss: fetch from Google
        counts = {}
        for t in AMENITY_TYPES:
            counts[t] = nearby_count(loc[0], loc[1], t, radius=2000)
        
        transport_counts = {}
        for t in TRANSPORT_TYPES:
            transport_counts[t] = nearby_count(loc[0], loc[1], t, radius=2000)
        
        # Upsert raw counts first
        supabase.table("suburb_metrics").upsert({
            "suburb_name": suburb_name,
            "supermarket_count": counts["supermarket"],
            "restaurant_count": counts["restaurant"],
            "pharmacy_count": counts["pharmacy"],
            "gym_count": counts["gym"],
            "train_station_count": transport_counts["train_station"],
            "bus_station_count": transport_counts["bus_station"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="suburb_name").execute()
        
        # Run SQL transformation in Supabase
        supabase.rpc(
            "refresh_suburb_metrics", 
            {"p_suburb_name": suburb_name}
        ).execute()
        
        # Read back refreshed scores
        fresh_row = get_cached_metrics(suburb_name, max_age_hours=99999)
        amenities_score = float(fresh_row.get("amenities_score", 0.0)) if fresh_row else 0.0
        transport_score = float(fresh_row.get("transport_score", 0.0)) if fresh_row else 0.0
        
        return counts, transport_counts, amenities_score, transport_score, False

    progress.progress(55, text="Fetching places (if needed)…")
    amenities_a, transport_a, amenities_score_a, transport_score_a, hit_a = build_metrics(suburb_a, loc_a, cached_a)
    amenities_b, transport_b, amenities_score_b, transport_score_b, hit_b = build_metrics(suburb_b, loc_b, cached_b)

    progress.progress(80, text="Rendering dashboard…")

    distance_km = geodesic(loc_a, loc_b).km

    # Top KPI cards
    k1, k2, k3 = st.columns(3)

    with k1:
        st.metric("Distance", f"{distance_km:.2f} km")

    with k2:
        st.metric("Amenities Winner", suburb_a if amenities_score_a > amenities_score_b else suburb_b if amenities_score_b > amenities_score_a else "Tie")

    with k3:
        st.metric("Transport Winner", suburb_a if transport_score_a > transport_score_b else suburb_b if transport_score_b > transport_score_a else "Tie")
    

    tab1, tab2, tab3 = st.tabs([
        "Overview",
        "Feature Comparison",
        "Detailed Metrics"
    ])

    # Placeholder overall scoring
    score_a = (0.6 * amenities_score_a) + (0.4 * transport_score_a)
    score_b = (0.6 * amenities_score_b) + (0.4 * transport_score_b)

    st.markdown("## Overall Livability Score")

    col1, col2 = st.columns(2)

    with col1: 
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-value">{score_a:.0f}/100</div>
            <div class="kpi-label">>{suburb_a}</div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-value">{score_a:.0f}/100</div>
            <div class="kpi-label">{suburb_b}</div>
        </div>
        """, unsafe_allow_html=True)

    

    with tab1:
        st.subheader("Distance Between Suburbs")
        st.metric(
            label=f"Distance: {suburb_a} <-> {suburb_b}",
            value=f"{round(distance_km, 2)} km"
        )

        st.subheader("Location Map")
        map_df = pd.DataFrame({
            "lat": [loc_a[0], loc_b[0]],
            "lon": [loc_a[1], loc_b[1]],
            "suburb": [suburb_a, suburb_b],
        })
        st.map(map_df[["lat", "lon"]])
        st.caption(f"Showing locations for {suburb_a} and {suburb_b}")

        if show_amenities:
            st.markdown("---")
            st.subheader("Amenities (MVP)")
            c1, c2 = st.columns(2)

            with c1: 
                st.metric("Amenities score (A)", f"{amenities_score_a:.0f}/100")

            with c2:
                st.metric("Amenities score (B)", f"{amenities_score_b:.0f}/100")
        
        if show_transport:
            st.markdown("---")
            st.subheader("Transport (MVP)")
            t1, t2 = st.columns(2)

            with t1:
                st.metric("Transport score (A)", f"{transport_score_a}/100")

            with t2:
                st.metric("Transport score (B)", f"{transport_score_b}/100")

        st.markdown("## Livability Score Overview")
        col1, col2 = st.columns(2)

        with col1:
            st.metric(
                label=suburb_a,
                value=f"{score_a:.0f}/100",
                delta=f"Amenities {amenities_score_a:.0f} | Transport {transport_score_a:.0f}"
            )

        with col2:
            st.metric(
                label=suburb_b,
                value=f"{score_b:.0f}/100",
                delta=f"Amenities {amenities_score_b:.0f} | Transport {transport_score_b:.0f}"
            )

        st.markdown("## Insight")
        if score_a > score_b:
            st.success(f"{suburb_a} performs better overall based on current livability metrics.")
        elif score_b > score_a:
            st.success(f"{suburb_b} performs better overall based on current livability metrics.")
        else:
            st.info("Both suburbs perform equally based on current metrics.")
    
    with tab2:
        st.subheader("Overall Score Comparison")
        chart_df = pd.DataFrame({
            "Suburb": [suburb_a, suburb_b],
            "Score": [score_a, score_b]
        })
        st.bar_chart(chart_df.set_index("Suburb"))

        import plotly.graph_objects as go

        st.markdown("### Suburb Feature Comparison")

        categories = [
            "Supermarkets",
            "Restaurants",
            "Pharmacies",
            "Gym",
            "Train Stations",
            "Bus Stations"
        ]

        values_a = [
            amenities_a.get("supermarket", 0),
            amenities_a.get("restaurant", 0),
            amenities_a.get("pharmacy", 0),
            amenities_a.get("gym", 0),
            transport_a.get("train_station", 0),
            transport_a.get("bus_station", 0)
        ]
        
        values_b = [
            amenities_b.get("supermarket", 0),
            amenities_b.get("restaurant", 0),
            amenities_b.get("pharmacy", 0),
            amenities_b.get("gym", 0),
            transport_b.get("train_station", 0),
            transport_b.get("bus_station", 0)
        ]

        fig = go.Figure()

        fig.add_trace(go.Scatterpolar(
            r=values_a,
            theta=categories,
            fill="toself",
            name=suburb_a
        ))

        fig.add_trace(go.Scatterpolar(
            r=values_b,
            theta=categories,
            fill="toself",
            name=suburb_b
        ))

        fig.update_layout(
            polar=dict(radialaxis=dict(visible=True)),
            showlegend=True
        )

        st.plotly_chart(fig, use_container_width=True)

    with tab3:
        st.subheader("Comparison Breakdown")

        if show_amenities:
            st.markdown("### Amenities")
            amenities_df = pd.DataFrame({
                "Metric": ["Supermarkets", "Restaurants", "Pharmacies", "Gym"],
                suburb_a: [
                    amenities_a.get("supermarket", 0),
                    amenities_a.get("restaurant", 0),
                    amenities_a.get("pharmacy", 0),
                    amenities_a.get("gym", 0)
                ],
                suburb_b: [
                    amenities_b.get("supermarket", 0),
                    amenities_b.get("restaurant", 0),
                    amenities_b.get("pharmacy", 0),
                    amenities_b.get("gym", 0)
                ],                
            })

            st.dataframe(amenities_df, use_container_width=True)

            st.bar_chart(
                pd.DataFrame({
                    suburb_a: list(amenities_df[suburb_a]),
                    suburb_b: list(amenities_df[suburb_b]),
                }, index=amenities_df["Metric"])
            )
        if show_transport:
            st.markdown("### Transport")
            transport_df = pd.DataFrame({
                "Metric": ["Train Station", "Bus Stations"],
                suburb_a: [
                    transport_a.get("train_station", 0),
                    transport_a.get("bus_station", 0),
                ],
                suburb_b: [
                    transport_b.get("train_station", 0),
                    transport_b.get("bus_station", 0),
                ],
            })

            st.dataframe(transport_df, use_container_width=True)

            st.bar_chart(
                pd.DataFrame({
                    suburb_a: list(transport_df[suburb_a]),
                    suburb_b: list(transport_df[suburb_b]),
                }, index=transport_df["Metric"])
            )
        
        progress.progress(100, text="Done.")
        st.success("Comparison built successfully")

    supabase.table("suburb_comparisons").insert({
        "suburb_a": suburb_a,
        "suburb_b": suburb_b,
        "lat_a": loc_a[0],
        "lng_a": loc_a[1],
        "lat_b": loc_b[0],
        "lng_b": loc_b[1],
        "distance_km": float(distance_km),
        "amenities_score_a": float(amenities_score_a),
        "amenities_score_b": float(amenities_score_b),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }).execute()

    st.divider()
    st.caption(
        "Neighbourhood Livability Index - Built with Streamlit, Google Places API, and Supabase"
    )
