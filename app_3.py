# app_v3.py  — One-shot chat mode (FULL FIXED VERSION)

import re
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st

st.set_page_config(page_title="MakanSini V3 - One-shot Chatbot", page_icon="🍜")

# ==========================
# GLOBAL CSS — Reliable font control
# ==========================
st.markdown("""
<style>
    .chat-message {
        font-size: 1.0rem !important; 
        line-height: 1.35 !important;
    }
</style>
""", unsafe_allow_html=True)




# ==========================
# Data loading & scoring
# ==========================

CSV_FILE = "Survey on Restaurant around Seri Iskandar (Responses) - Form Responses 1.csv"

def load_catalog():
    csv_path = Path(__file__).parent / CSV_FILE
    df = pd.read_csv(csv_path)

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

    for col in ["min_spend", "max_spend", "travel_mins", "rating"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["name"])
    return df


def filter_open_today(df):
    today_name = datetime.today().strftime("%A")
    return df[df["days"].astype(str).str.contains(today_name, case=False, na=False)]


def score_restaurants(df, preferences, only_open_today=True):
    if only_open_today:
        df = filter_open_today(df)
    if df.empty:
        return df

    df = df.copy()
    df["score"] = 0

    cuisine_pref = preferences.get("cuisine") or ""
    meal_type = preferences.get("meal_type") or ""
    halal_pref = preferences.get("halal_pref") or ""
    location_pref = preferences.get("location_pref") or ""
    max_budget = preferences.get("max_budget")
    max_travel = preferences.get("max_travel")

    if cuisine_pref:
        df["score"] += df["cuisine"].astype(str).str.contains(cuisine_pref, case=False, na=False) * 40

    if max_budget is not None:
        mask = df["min_spend"].le(max_budget) | df["max_spend"].le(max_budget)
        df["score"] += mask * 30

    if meal_type and meal_type.lower() != "any":
        df["score"] += df["dining_tag"].astype(str).str.contains(meal_type, case=False, na=False) * 15

    if max_travel is not None:
        df["score"] += df["travel_mins"].le(max_travel) * 15

    if halal_pref.lower().startswith("halal"):
        df = df[df["halal"].astype(str).str.contains("yes", case=False, na=False)]
        df["score"] += 5

    if location_pref and location_pref.lower() != "any":
        df["score"] += df["location"].astype(str).str.contains(location_pref, case=False, na=False) * 5

    df["score"] += df["rating"].fillna(0) * 2

    return df.sort_values("score", ascending=False)



# ==========================
# Parsing helpers
# ==========================

def get_known_cuisines():
    df = load_catalog()
    cuisines = set()
    for raw in df["cuisine"].dropna():
        for part in re.split(r"[,/;]", str(raw)):
            cuisines.add(part.strip())
    return sorted([c for c in cuisines if c])


def pick_cuisine(text):
    text_low = text.lower()
    for c in get_known_cuisines():
        if c.lower() in text_low:
            return c
    return None


def pick_meal_type(t):
    t = t.lower()
    if "breakfast" in t: return "Breakfast"
    if "lunch" in t: return "Lunch"
    if "tea" in t: return "Tea Time"
    if "dinner" in t or "supper" in t: return "Dinner"
    return "Any"


def pick_halal_pref(t):
    t = t.lower()
    if "halal" in t: return "Halal only"
    if "tak kisah" in t or "doesn't matter" in t or "doesnt matter" in t or "any" in t:
        return "Doesn't matter"
    return "Doesn't matter"


def pick_location(t):
    t = t.lower()
    if "inside utp" in t: return "Inside UTP"
    if "tronoh" in t: return "Tronoh"
    if "bandar" in t: return "Bandar Universiti"
    return "Any"


def pick_budget(text):
    """
    Understand both keywords ('cheap') and numbers (rm10, under 15, etc.)
    """
    t = text.lower()

    # 1) Keyword buckets (no explicit number)
    # You can tune these RM values however you like
    if "cheap" in t or "murah" in t:
        return 10.0          # treat 'cheap' as roughly RM10 max
    if "mid" in t or "medium" in t or "average" in t or "sederhana" in t:
        return 15.0          # 'medium price'
    if "expensive" in t or "mahal" in t or "high end" in t:
        return 25.0          # 'expensive'

    # 2) Exact numeric patterns
    # rmxx or rm xx
    rm_match = re.search(r"rm\s*(\d+)", t)
    if rm_match:
        return float(rm_match.group(1))

    # 'under 10', 'below 15', 'max 12', 'budget 8'
    nearby_match = re.search(r"(under|below|max|budget)\s*(rm)?\s*(\d+)", t)
    if nearby_match:
        return float(nearby_match.group(3))

    # 3) Plain number (not followed by 'min' etc.) → assume it's a budget
    num_match = re.search(r"\b(\d+)\b(?!\s*(min|mins|minute|minutes))", t)
    if num_match:
        return float(num_match.group(1))

    return None



def pick_travel(t):
    t = t.lower()
    m = re.search(r"(\d+)\s*(min|mins|minute)", t)
    return float(m.group(1)) if m else None


def parse_one_shot(t):
    return {
        "cuisine": pick_cuisine(t),
        "max_budget": pick_budget(t),
        "meal_type": pick_meal_type(t),
        "max_travel": pick_travel(t),
        "halal_pref": pick_halal_pref(t),
        "location_pref": pick_location(t),
    }


def prefs_summary(prefs):
    return (
        f"- Cuisine: **{prefs.get('cuisine') or 'any cuisine'}**\n"
        f"- Budget: **{('≤ RM'+str(int(prefs['max_budget']))) if prefs.get('max_budget') else 'any budget'}**\n"
        f"- Meal: **{prefs.get('meal_type', 'Any')}**\n"
        f"- Distance: **{('within '+str(int(prefs['max_travel']))+' mins') if prefs.get('max_travel') else 'any distance'}**\n"
        f"- Preference: **{'halal only' if prefs.get('halal_pref','').startswith('Halal') else 'halal or non-halal'}**\n"
        f"- Area: **{prefs.get('location_pref','Any')}**"
    )


# ==========================
# Session helpers
# ==========================

def init_session():
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {"role": "assistant", "text": "Hi! I'm MakanSini V3 🍜🤖<br><br>Tell me what you're craving in **one sentence**.<br><br>Example: `cheap halal Korean dinner within 10 minutes from UTP`", "small": False}
        ]


def add_message(role, text, small=False):
    st.session_state.messages.append({"role": role, "text": text, "small": small})


def render_chat():
    for msg in st.session_state.messages:
        role = "assistant" if msg["role"] == "assistant" else "user"
        with st.chat_message(role):
            st.markdown(f"<div class='chat-message'>{msg['text']}</div>", unsafe_allow_html=True)



def reset_session():
    st.session_state.pop("messages", None)
    st.rerun()



# ==========================
# Main
# ==========================

def main():
    st.title("🍜 MakanSini V3 – One-shot Chatbot")
    st.caption("Powered by natural-language preferences.")

# guide on how to chat with the app
    with st.expander("ℹ️ How to talk to this bot"):
     st.markdown("""
- Type **one sentence** with what you feel like eating.
- Order and grammar **don’t matter** – I look for keywords.

**You can include:**
- **Cuisine:** Malay, Mamak, Thai, Korean, Western, Chinese, Indian…
- **Budget:** `rm10`, `under 15`, `budget 8`, or words like *cheap / murah / mahal*.
- **Distance:** `5 mins`, `10 minutes`, `inside utp`, `in tronoh`, `in BU`.
- **Halal:** `halal only`, `tak kisah halal`, `doesn't matter`.
- **Meal:** `breakfast`, `lunch`, `tea time`, `dinner`.

**Examples:**
- `cheap halal mamak inside utp`
- `korean dinner under rm20 within 5 mins from utp`
- `any halal western food in tronoh, budget 15`
- `murah malay breakfast near BU`
- `thai food, halal, max rm12, 10 minutes from utp`
        """)

    

    init_session()
    render_chat()

    if st.button("🔄 Start Over"):
        reset_session()

    text = st.chat_input("Tell me what you're craving...")

    if not text:
        return

    # user msg
    add_message("user", text)

    prefs = parse_one_shot(text)

    if not prefs["cuisine"] and prefs["max_budget"] is None and prefs["max_travel"] is None:
        add_message("assistant",
            "I couldn't catch any specific cuisine, budget, or distance 😅<br><br>"
            "Try including at least one detail, e.g.:<br>"
            "- `cheap Malay food`<br>"
            "- `halal Western lunch under RM15`<br>"
            "- `any cuisine within 5 mins from UTP`"
            
        )
        st.rerun()

    add_message("assistant", "Here’s what I understood:<br><br>"+ prefs_summary(prefs))

    df = load_catalog()
    ranked = score_restaurants(df, prefs, True)

    if ranked.empty:
        add_message("assistant", "Hmm… no restaurants matched **and** are open today 😔<br>Try increasing distance or budget." )
        st.rerun()

    lines = ["Here are some suggestions for you 👇<br><br>"]
    for _, row in ranked.head(3).iterrows():
        lines.append(
            f"**{row['name']}** ({row['cuisine']})<br>"
            f"💸 {row['spend_range']} | ⭐ {row['rating']}<br>"
            f"📍 {row['location']} | ⏱ {row['travel_mins']} minutes<br>"
            f"🕌 Halal: {row['halal']}<br>"
            f"🕒 {row['hours']}<br>"
            f"📅 {row['days']}<br>"
            "<hr>"
        )

    add_message("assistant", "<br>".join(lines))

    st.rerun()


if __name__ == "__main__":
    main()
