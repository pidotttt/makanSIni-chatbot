# app.py

import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime

st.set_page_config(page_title="MakanSini V2 - Chatbot", page_icon="🍛")

# 👇 Change this if you rename your CSV
CSV_FILE = "Survey on Restaurant around Seri Iskandar (Responses) - Form Responses 1.csv"


# ==========================
# Data loading & scoring
# ==========================
def load_catalog():
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

    df = df.dropna(subset=["name"])
    return df


def filter_open_today(df):
    if "days" not in df.columns:
        return df
    today_name = datetime.today().strftime("%A")
    mask = df["days"].astype(str).str.contains(today_name, case=False, na=False)
    return df[mask]


def score_restaurants(df, preferences, only_open_today=True):
    """
    preferences example:
      {
        "cuisine": "Malay",
        "max_budget": 12.0,
        "meal_type": "Lunch",
        "max_travel": 10,
        "halal_pref": "Halal only",
        "location_pref": "Any"
      }
    """
    if only_open_today:
        df = filter_open_today(df)

    if df.empty:
        return df

    df = df.copy()
    df["score"] = 0.0

    cuisine_pref = (preferences.get("cuisine") or "").strip()
    meal_type = (preferences.get("meal_type") or "").strip()
    halal_pref = (preferences.get("halal_pref") or "").strip()
    location_pref = (preferences.get("location_pref") or "").strip()
    max_budget = preferences.get("max_budget")
    max_travel = preferences.get("max_travel")

    # 1. Cuisine
    if cuisine_pref:
        df["score"] += df["cuisine"].astype(str).str.contains(
            cuisine_pref, case=False, na=False
        ) * 40

    # 2. Budget
    if max_budget is not None:
        budget_mask = df["min_spend"].le(max_budget) | df["max_spend"].le(max_budget)
        df["score"] += budget_mask * 30

    # 3. Meal type
    if meal_type and meal_type.lower() != "any":
        df["score"] += df["dining_tag"].astype(str).str.contains(
            meal_type, case=False, na=False
        ) * 15

    # 4. Distance
    if max_travel is not None:
        df["score"] += df["travel_mins"].le(max_travel) * 15

    # 5. Halal preference
    if halal_pref.lower().startswith("halal"):
        df = df[df["halal"].astype(str).str.contains("yes", case=False, na=False)]
        df["score"] += 5

    # 6. Location preference
    if location_pref and location_pref.lower() != "any":
        df["score"] += df["location"].astype(str).str.contains(
            location_pref, case=False, na=False
        ) * 5

    # 7. Rating baseline
    if "rating" in df.columns:
        df["score"] += df["rating"].fillna(0) * 2

    df = df.sort_values(by=["score", "rating"], ascending=[False, False])
    return df


# ==========================
# Chatbot questions
# ==========================
QUESTIONS = [
    {
        "key": "cuisine",
        "question": "What cuisine are you craving? (e.g. Malay, Thai, Western, Korean)",
    },
    {
        "key": "max_budget",
        "question": "What is your maximum budget per person? (RM, e.g. 10)",
    },
    {
        "key": "meal_type",
        "question": "Which meal are you planning for? (Breakfast, Lunch, Tea Time, Dinner, or Any)",
    },
    {
        "key": "max_travel",
        "question": "How many minutes are you willing to travel from UTP? (e.g. 5, 10, 15)",
    },
    {
        "key": "halal_pref",
        "question": "Do you want only halal restaurants, or it doesn't matter?",
    },
    {
        "key": "location_pref",
        "question": "Any preferred area? (Inside UTP, Tronoh, Bandar Universiti, or Any)",
    },
]


# ==========================
# Session helpers
# ==========================
def init_session():
    ss = st.session_state
    if "question_index" not in ss:
        ss.question_index = 0
    if "answers" not in ss:
        ss.answers = {}
    if "done" not in ss:
        ss.done = False
    if "messages" not in ss:
        ss.messages = []  # list of {"role": "bot"/"user", "text": str}

    # On very first load, greet + first question
    if not ss.messages:
        ss.messages.append({
            "role": "bot",
            "text": "Hi! I'm MakanSini 🤖🍛. I'll help you find a place to eat around UTP."
        })
        first_q = QUESTIONS[0]["question"]
        ss.messages.append({"role": "bot", "text": first_q})


def reset_session():
    for key in ["question_index", "answers", "done", "messages"]:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()


# ==========================
# UI pieces
# ==========================
def render_chat():
    # Simple chat bubble styling
    for msg in st.session_state.messages:
        if msg["role"] == "bot":
            st.markdown(
                f"""
                <div style="background-color:#f1f0f0; padding:8px 12px; border-radius:10px; margin-bottom:4px; max-width:80%;">
                    <b>MakanSini:</b> {msg['text']}
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"""
                <div style="background-color:#d1ffd6; padding:8px 12px; border-radius:10px; margin-bottom:4px; max-width:80%; margin-left:auto; text-align:right;">
                    {msg['text']}
                </div>
                """,
                unsafe_allow_html=True,
            )


def parse_preferences(raw_answers):
    prefs = raw_answers.copy()

    # Normalize meal_type
    if "meal_type" in prefs and isinstance(prefs["meal_type"], str):
        mt = prefs["meal_type"].strip().lower()
        if mt in ["breakfast", "lunch", "teatime", "tea time", "dinner"]:
            prefs["meal_type"] = mt.title()
        else:
            prefs["meal_type"] = "Any"

    # Normalize halal_pref
    if "halal_pref" in prefs and isinstance(prefs["halal_pref"], str):
        hp = prefs["halal_pref"].strip().lower()
        if "halal" in hp:
            prefs["halal_pref"] = "Halal only"
        else:
            prefs["halal_pref"] = "Doesn't matter"

    # Normalize location_pref
    if "location_pref" in prefs and isinstance(prefs["location_pref"], str):
        lp = prefs["location_pref"].strip().lower()
        if "inside" in lp:
            prefs["location_pref"] = "Inside UTP"
        elif "tronoh" in lp:
            prefs["location_pref"] = "Tronoh"
        elif "bandar" in lp:
            prefs["location_pref"] = "Bandar Universiti"
        else:
            prefs["location_pref"] = "Any"

    # Numeric fields
    for key in ["max_budget", "max_travel"]:
        val = prefs.get(key)
        if isinstance(val, str):
            val = val.strip()
            if val:
                try:
                    prefs[key] = float(val)
                except ValueError:
                    prefs[key] = None
            else:
                prefs[key] = None

    return prefs


def show_recommendations():
    st.markdown(" 🍽 Here are your recommendations:")

    df = load_catalog()
    prefs = parse_preferences(st.session_state.answers)
    ranked_df = score_restaurants(df, prefs, only_open_today=True)

    if ranked_df.empty:
        st.warning(
            "Hmm… I couldn't find any restaurant that matches your preferences "
            "and is open today. You can try again with a higher budget or longer travel time."
        )
        return

    top_choices = ranked_df.head(3)

    for i, (_, row) in enumerate(top_choices.iterrows(), start=1):
        st.markdown(f"**{i}. {row['name']}**")


        cols = st.columns(2)
        with cols[0]:
            st.write(f"**Cuisine:** {row.get('cuisine', 'N/A')}")
            st.write(f"**Area:** {row.get('location', 'N/A')}")
            st.write(f"**Halal:** {row.get('halal', 'N/A')}")
            st.write(f"**Rating:** {row.get('rating', 'N/A')} ⭐")

        with cols[1]:
            st.write(f"**Spend range:** {row.get('spend_range', 'N/A')}")
            min_spend = row.get("min_spend", None)
            max_spend = row.get("max_spend", None)
            if pd.notna(min_spend) and pd.notna(max_spend):
                st.write(f"**Approx. RM/person:** RM{min_spend:.0f} – RM{max_spend:.0f}")
            st.write(f"**Travel time from UTP:** {row.get('travel_mins', 'N/A')} mins")

        st.write(f"**Operating hours:** {row.get('hours', 'N/A')}")
        st.write(f"**Operating days:** {row.get('days', 'N/A')}")

        # Why this restaurant?
        prefs = parse_preferences(st.session_state.answers)
        reasons = []

        if prefs.get("cuisine"):
            if prefs["cuisine"].lower() in str(row.get("cuisine", "")).lower():
                reasons.append(f"- Matches your cuisine preference: **{row['cuisine']}**")

        if prefs.get("max_budget") and pd.notna(row.get("min_spend", None)):
            try:
                if row["min_spend"] <= prefs["max_budget"]:
                    reasons.append(f"- Within your budget (min spend ≈ RM{row['min_spend']:.0f})")
            except Exception:
                pass

        if prefs.get("meal_type") and prefs["meal_type"].lower() != "any":
            if prefs["meal_type"].lower() in str(row.get("dining_tag", "")).lower():
                reasons.append(f"- Suitable for **{prefs['meal_type']}**")

        if prefs.get("max_travel") and pd.notna(row.get("travel_mins", None)):
            try:
                if row["travel_mins"] <= prefs["max_travel"]:
                    reasons.append(f"- Travel time **{row['travel_mins']} mins** is within your limit")
            except Exception:
                pass

        if prefs.get("halal_pref", "").lower().startswith("halal"):
            if str(row.get("halal", "")).lower().startswith("yes"):
                reasons.append("- **Halal-friendly** restaurant")

        if prefs.get("location_pref") and prefs["location_pref"].lower() != "any":
            if prefs["location_pref"].lower() in str(row.get("location", "")).lower():
                reasons.append(f"- Located in your preferred area: **{row['location']}**")

        if not reasons:
            reasons.append("- High overall score based on your preferences and rating.")

        st.markdown("**Why this place?**")
        st.markdown("\n".join(reasons))
        st.markdown("---")


# ==========================
# Main app
# ==========================
def cuisine_exists(user_text: str) -> bool:
    """Check if the typed cuisine appears in the dataset at all."""
    df = load_catalog()
    text = (user_text or "").strip()
    if not text:
        return False
    mask = df["cuisine"].astype(str).str.contains(text, case=False, na=False)
    return mask.any()


def is_number(text: str) -> bool:
    """Return True if text can be converted to a float."""
    try:
        float(text)
        return True
    except Exception:
        return False
def cuisine_exists(user_text: str) -> bool:
    """Check if the typed cuisine appears in the dataset at all."""
    df = load_catalog()
    text = (user_text or "").strip()
    if not text:
        return False
    mask = df["cuisine"].astype(str).str.contains(text, case=False, na=False)
    return mask.any()


def is_number(text: str) -> bool:
    """Return True if text can be converted to a float."""
    try:
        float(text)
        return True
    except Exception:
        return False


def main():
    st.title("🍛 MakanSini V2 – Chatbot")
    st.caption("Chat with the bot and get 3 restaurant suggestions that match you and are open today.")

    init_session()

    if st.button("🔄 Start Over"):
        reset_session()

    # Show chat history
    render_chat()

    # If we've finished all questions, show recommendations
    if st.session_state.done:
        show_recommendations()
        return

    # Chat input (WhatsApp-style bottom box)
    user_input = st.chat_input("Type your answer here...")

    if not user_input:
        return

    # ---------------------------
    # HANDLE USER INPUT + VALIDATE
    # ---------------------------
    # Add user message to history
    st.session_state.messages.append({"role": "user", "text": user_input})

    q_idx = st.session_state.question_index

    # Safety check (shouldn't normally happen)
    if q_idx >= len(QUESTIONS):
        st.rerun()

    key = QUESTIONS[q_idx]["key"]
    answer = user_input.strip()
    answer_low = answer.lower()

    # 1️⃣ VALIDATION BY QUESTION TYPE
    if key == "cuisine":
        # Check if cuisine exists in dataset
        if not cuisine_exists(answer):
            st.session_state.messages.append({
                "role": "bot",
                "text": (
                    "Hmm… I couldn't find that cuisine in my list. 😅\n"
                    "Try something like **Malay, Thai, Western, Korean, Indian, Mamak**, etc."
                )
            })
            # ❌ Do NOT move to next question
            st.rerun()

    elif key == "max_budget":
        if answer and not is_number(answer):
            st.session_state.messages.append({
                "role": "bot",
                "text": "Please enter your budget as a number, e.g. `10` or `15`. 💸"
            })
            st.rerun()

    elif key == "meal_type":
        # Accept only Breakfast, Lunch, Tea Time, Dinner, Any
        valid_meal_words = ["breakfast", "lunch", "tea time", "teatime", "dinner", "any"]
        if not any(w in answer_low for w in valid_meal_words):
            st.session_state.messages.append({
                "role": "bot",
                "text": (
                    "Please choose a meal from: **Breakfast, Lunch, Tea Time, Dinner, or Any**. 🍽️\n"
                    "You can type something like `lunch` or `any`."
                )
            })
            st.rerun()

    elif key == "max_travel":
        if answer and not is_number(answer):
            st.session_state.messages.append({
                "role": "bot",
                "text": "Please enter travel time in minutes as a number, e.g. `5`, `10`, or `15`. 🚗"
            })
            st.rerun()

    elif key == "halal_pref":
        # Require a clear answer – not just random text
        # Accept phrases containing these words:
        valid_halal_words = ["halal", "only", "tak kisah", "doesn't matter", "doesnt matter", "no preference"]
        # Simple yes/no can also be used, but we'll force them to be clear:
        if not any(w in answer_low for w in valid_halal_words):
            st.session_state.messages.append({
                "role": "bot",
                "text": (
                    "Please answer clearly: do you want **only halal** restaurants, "
                    "or it **doesn't matter**?\n"
                    "For example: `only halal` or `doesn't matter`."
                )
            })
            st.rerun()

    elif key == "location_pref":
        # Accept only known areas or 'Any'
        valid_location_words = ["inside utp", "utp", "tronoh", "bandar universiti",
                                "any", "no preference", "tak kisah"]
        if not any(w in answer_low for w in valid_location_words):
            st.session_state.messages.append({
                "role": "bot",
                "text": (
                    "Please choose a location like **Inside UTP, Tronoh, Bandar Universiti, or Any**. 📍\n"
                    "You can also type `no preference` or `tak kisah`."
                )
            })
            st.rerun()

    # 2️⃣ IF WE REACH HERE → INPUT IS ACCEPTED
    st.session_state.answers[key] = answer

    # 3️⃣ Move to next question or finish
    st.session_state.question_index += 1

    if st.session_state.question_index < len(QUESTIONS):
        next_q = QUESTIONS[st.session_state.question_index]["question"]
        st.session_state.messages.append({"role": "bot", "text": next_q})
    else:
        st.session_state.done = True
        st.session_state.messages.append({
            "role": "bot",
            "text": "Got it! Let me check the restaurants that match you..."
        })

    st.rerun()





if __name__ == "__main__":
    main()
