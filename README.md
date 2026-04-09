# 🏡 Neighbourhood Livability Index (MVP)

An interactive data-driven dashboard that compares the livability of suburbs using real-time amenities, transport access, and geospatial analytics.

## 🔗 Live Demo
(we will add this after deployment)

## 📊 Key Features
- Compare two suburbs in real-time
- Amenities scoring (supermarkets, restaurants, gyms, etc.)
- Transport accessibility analysis
- Distance calculation using geospatial data
- Interactive visualisations (Plotly)
- Map-based location insights

## 🧠 Problem Statement
Choosing where to live is complex. This project simplifies decision-making by quantifying suburb livability using data-driven metrics.

## ⚙️ Tech Stack
- Python
- Streamlit
- Google Places API
- Supabase
- Plotly
- Pandas

## 📈 Business Value
- Helps users make informed housing decisions
- Can be extended for real estate analytics
- Supports urban planning insights

# Neighborhood Livability Index (MVP)

## Overview
This project is an intercative Streamlit dashboard that compares the livability of two suburbs using amenities, transport access, distance, and location analytics.

## Features
- Compare two suburbs
- Geocode suburb locations
- Calculate distance between suburbs
- Show suburb locations on a map
- Score amenities and transport
- Generate overall livability score
- Radar and bar chart comparison
- Cache results in Supabase

## Tech Stack
- Python
- Streamlit
- Supabase
- Google Places API
- Plotly
- Pandas
- Geopy

## Architecture
Streamlit UI -> Google Places API -> Feature extraction -> Supabase caching -> SQL scoring -> Dashboard visualisation

## Scoring Model
Overall Score = (0.6 x Amenities Score) + (0.4 x Transport Score)

## Future Improvements
- Distance to CBD
- User-controlled score weighting
- Population-normalised metrics
- Crime/school/healthcare metrics