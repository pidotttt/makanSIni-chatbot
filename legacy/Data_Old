# data.py
import pandas as pd
from pathlib import Path
from datetime import datetime

CSV_FILE = "Survey on Restaurant around Seri Iskandar (Responses) - Form Responses 1.csv"


def load_catalog():
    """
    Load the restaurant survey CSV and clean up/standardize column names.
    """
    csv_path = Path(__file__).parent / CSV_FILE
    df = pd.read_csv(csv_path)

    # Rename to simpler internal names
    df = df.rename(columns={
        "Restaurant Name": "name",
        "Range spending per meal": "spend_range",
        "Minimum spending per person  (eg: RM5)": "min_spend",
        "Maximum spending per person (eg: RM15)": "max_spend",
        "Dining Tag": "dining_tag",
        "Is this restaurant Halal?": "halal",
        "Cuisine Tag": "cuisine",
        "Operating Hours (eg: 8.00am - 3.00pm)": "hours",
        "Operating Days": "days",
        "Travel time from UTP (in mins, eg: 6 mins)": "travel_mins",
        "Location/Area": "location",
        "Rating": "rating",
    })

    # Convert numeric columns
    for col in ["min_spend", "max_spend", "travel_mins", "rating"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Drop rows without a restaurant name just in case
    df = df.dropna(subset=["name"])

    return df


def filter_open_today(df):
    """
    Keep only restaurants that are open today based on the 'days' column.
    """
    if "days" not in df.columns:
        return df

    # e.g. "Monday, Tuesday, Wednesday, Thursday, Friday"
    today_name = datetime.today().strftime("%A")
    mask = df["days"].astype(str).str.contains(today_name, case=False, na=False)
    return df[mask]


def score_restaurants(df, preferences, only_open_today=True):
    """
    Score each restaurant based on how well it matches the user's preferences.

    preferences is a dict, for example:
      {
        "cuisine": "Malay",
        "max_budget": 12.0,
        "meal_type": "Lunch",
        "max_travel": 10,
        "halal_pref": "Halal only",
        "location_pref": "Any"
      }
    """

    # Optionally filter only restaurants open today
    if only_open_today:
        df = filter_open_today(df)

    if df.empty:
        return df

    df = df.copy()
    df["score"] = 0.0

    # Unpack preferences safely
    cuisine_pref = (preferences.get("cuisine") or "").strip()
    meal_type = (preferences.get("meal_type") or "").strip()
    halal_pref = (preferences.get("halal_pref") or "").strip()
    location_pref = (preferences.get("location_pref") or "").strip()
    max_budget = preferences.get("max_budget")
    max_travel = preferences.get("max_travel")

    # 1. Cuisine match (high weight)
    if cuisine_pref:
        df["score"] += df["cuisine"].astype(str).str.contains(
            cuisine_pref, case=False, na=False
        ) * 40

    # 2. Budget match (numeric)
    if max_budget is not None:
        # Reward if user's budget covers at least the min spend
        budget_mask = df["min_spend"].le(max_budget) | df["max_spend"].le(max_budget)
        df["score"] += budget_mask * 30

    # 3. Meal type vs dining_tag (breakfast/lunch/tea time/dinner)
    if meal_type and meal_type.lower() != "any":
        df["score"] += df["dining_tag"].astype(str).str.contains(
            meal_type, case=False, na=False
        ) * 15

    # 4. Max travel time (distance)
    if max_travel is not None:
        # Reward if travel time is <= max_travel
        df["score"] += df["travel_mins"].le(max_travel) * 15

    # 5. Halal preference
    if halal_pref.lower().startswith("halal"):  # "Halal only"
        # Strong filter: keep only halal restaurants
        df = df[df["halal"].astype(str).str.contains("yes", case=False, na=False)]
        # Small extra score boost for being halal
        df["score"] += 5

    # 6. Location preference (Inside UTP, Tronoh, Bandar Universiti, etc.)
    if location_pref and location_pref.lower() != "any":
        df["score"] += df["location"].astype(str).str.contains(
            location_pref, case=False, na=False
        ) * 5

    # 7. Rating as baseline quality
    if "rating" in df.columns:
        df["score"] += df["rating"].fillna(0) * 2

    # Sort by score (desc) and rating as tie-breaker
    df = df.sort_values(by=["score", "rating"], ascending=[False, False])

    return df
