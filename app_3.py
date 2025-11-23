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

# Cleaning Rows With Numbers
    for col in ["min_spend", "max_spend", "travel_mins", "rating"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

# Drop Rows W/O Names
    df = df.dropna(subset=["name"])
    return df


# Drop Restaurants not open today from df
def filter_open_today(df):
    today_name = datetime.today().strftime("%A")
    return df[df["days"].astype(str).str.contains(today_name, case=False, na=False)]


# Vectorised Scoring Method - Score every row simultaneously without loop
def score_restaurants(df, preferences, only_open_today=True, debug_mode=False):

    if df.empty:
        return df

    df = df.copy()
    df["score"] = 0

    # initialise per-aspect score columns (debug purposes)
    df["score_cuisine"] = 0.0
    df["score_budget"] = 0.0
    df["score_travel"] = 0.0
    df["score_meal"] = 0.0
    df["score_halal"] = 0.0
    df["score_location"] = 0.0
    df["score_rating"] = 0.0

    # unpack user preferences
    cuisine_pref = preferences.get("cuisine") or ""
    cuisine_list = preferences.get("cuisines") or []
    meal_type = preferences.get("meal_type") or ""
    halal_pref = preferences.get("halal_pref") or ""
    location_pref = preferences.get("location_pref") or ""
    max_budget = preferences.get("max_budget")
    max_travel = preferences.get("max_travel")

    # buang smua restos not open today
    if only_open_today:
        df = filter_open_today(df)

    # ------------ CUISINE SCORING -------------------
    if cuisine_list:
        pattern = "|".join(re.escape(c) for c in cuisine_list)
        mask_cuisines = df["cuisine"].astype(str).str.contains(pattern, case=False, na=False)
        df.loc[mask_cuisines, "score_cuisine"] += 40

    elif cuisine_pref:
        mask_cuisine = df["cuisine"].astype(str).str.contains(cuisine_pref, case=False, na=False)
        df.loc[mask_cuisine, "score_cuisine"] += 40

    # ------------ BUDGET SCORING --------------------
    if max_budget is not None:
        min_spend_col = df["min_spend"]
        max_spend_col = df["max_spend"]

        # Valid rows where both min and max are known
        valid = min_spend_col.notna() & max_spend_col.notna()

        # Budget Tiering
        # 1) Fully in budget: entire range is <= budget
        fully_in_budget = valid & max_spend_col.le(max_budget)
        # 2) Partially in budget: cheapest item is affordable, but some items are above budget
        partially_in_budget = valid & ~fully_in_budget & min_spend_col.le(max_budget)
        # 3) Over budget: even the cheapest option is above budget
        over_budget = valid & ~fully_in_budget & ~partially_in_budget

        # Reward/Penalise tiers
        df.loc[fully_in_budget, "score_budget"] += 30  # best match
        df.loc[partially_in_budget, "score_budget"] += 15  # okay
        df.loc[over_budget, "score_budget"] -= 10  # should not be recommended

    # ------------ MEALTYPE SCORING -------------------------
    if meal_type and meal_type.lower() != "any":
        mask_meal = df["dining_tag"].astype(str).str.contains(meal_type, case=False, na=False)
        df.loc[mask_meal, "score_meal"] += 15

    # ------------------- TRAVEL SCORING -------------------------
    if max_travel is not None:
        df["score_travel"] += df["travel_mins"].le(max_travel) * 15

    # ------------------- HALAL SCORING -------------------------
    if halal_pref:
        halal_col = df["halal"].astype(str).str.lower()
        if halal_pref.lower() == "halal":
            df.loc[halal_col.str.contains("yes", na=False), "score_halal"] += 10
            df.loc[~halal_col.str.contains("yes", na=False), "score_halal"] -= 20

    # --------------------- LOCATION SCORING -------------------
    if location_pref and location_pref.lower() != "any":
        loc_series = df["location"].astype(str)

        if location_pref == "Outside UTP":
            # smua yang ~Inside UTP considered "outside"
            mask_inside = loc_series.str.contains("Inside UTP", case=False, na=False)
            mask_outside = ~mask_inside
            # Reward every restos outside UTP
            df.loc[mask_outside, "score_location"] += 10
            # penalise every restos Inside UTP if user explicitly said outside
            df.loc[mask_inside, "score_location"] -= 10

        else:
            # Normal case: reward exact match to the preferred location
            mask_loc = loc_series.str.contains(location_pref, case=False, na=False)
            df.loc[mask_loc, "score_location"] += 5

    # ------------------------ RATING SCORING -------------------
    df["score_rating"] += df["rating"].fillna(0) * 2

    # ----------------------ADD ALL SCORES ----------------------
    df["score"] = (
            df["score_cuisine"]
            + df["score_budget"]
            + df["score_travel"]
            + df["score_meal"]
            + df["score_halal"]
            + df["score_location"]
            + df["score_rating"]
    )

    df = df.sort_values("score", ascending=False) # top of list score highest

    if debug_mode:
        # return full debug info (you'll show selected columns in Streamlit)
        return df
    else:
        # for normal usage, maybe just return with score
        return df


# ==========================
# Parsing helpers
# ==========================

# ====== location helpers and dictionary ==================
def get_known_locations():
    df = load_catalog()
    locations = {
        str(loc).strip()
        for loc in df["location"].dropna()
        if str(loc).strip()
    }
    return sorted(locations)


LOCATION_SYNONYMS = {
    "Inside UTP": [
        "inside utp", "dalam utp", "in utp", "within utp",
        "dalam kampus", "inside campus", "inside"
    ],
    "Tronoh": [
        "tronoh", "trono", "teronoh"
    ],
    "Bandar Universiti": [
        "bandar universiti", "bandar uni", "bdr uni", "bu", "lotus"
    ],
    "Outside UTP": [
        "town", "luar", "outside", "out"
    ],
    "SIBC": [
        "sibc", "si", "seri iskandar", "billion"
    ]
}


def normalize_location_text(text):
    t = text.lower()
    for canonical, syns in LOCATION_SYNONYMS.items():
        for s in syns:
            pattern = r"\b" + re.escape(s) + r"\b"
            t = re.sub(pattern, canonical.lower(), t)

    return t.lower()


def pick_location(text):
    t = normalize_location_text(text)
    t_no_punc = re.sub(r"[^\w\s]", " ", t)

    if "outside utp" in t_no_punc:
        return "Outside UTP"

    for loc in get_known_locations():
        if loc and loc.lower() in t_no_punc:
            return loc

    return "Any"
# =====================================================

# ======== Budget Helpers and Dictionaries ============


BUDGET_SYNONYMS = {
    "cheap": [
        "cheap", "murah", "bajet", "budget sikit",
        "taknak mahal", "tak nak mahal", "not expensive",
        "jimat", "low budget", "affordable", "ekonomi", "rahmah"
    ],
    "medium": [
        "medium", "average", "sederhana", "mid-range", "mid range",
        "normal price", "biasa", "reasonable"
    ],
    "expensive": [
        "expensive", "mahal", "high end", "mahal sikit",
        "premium", "luxury", "boujee"
    ]
}

BUDGET_VALUES = {
    "cheap": 10.0,
    "medium": 15.0,
    "expensive": 25.0
}


def pick_budget(text):
    t = text.lower()

    for category, syns in BUDGET_SYNONYMS.items():
        if any(s in t for s in syns):
            return BUDGET_VALUES[category]

    rm_match = re.search(r"rm\s*(\d+)", t)
    if rm_match:
        return float(rm_match.group(1))

    nearby_match = re.search(
        r"(under|below|bawah|max|budget)\s*(rm)?\s*(\d+(?:\.\d+)?)\b(?!\s*(min|mins|minute|minutes))", t)
    if nearby_match:
        return float(nearby_match.group(3))

    more_malay = re.search(r"(bawah|taknak lebih|tak nak lebih|jangan lebih|around|sekitar)\s*(rm)?\s*(\d+)", t)
    if more_malay:
        return float(more_malay.group(3))

    ringgit_match = re.search(r"\b(\d+(?:\.\d+)?)\b\s*(ringgit)\b", t)
    if ringgit_match:
        return float(ringgit_match.group(1))

    return None
# =======================================================

# ================ Cuisine ==============================


def get_known_cuisines():
    df = load_catalog()
    cuisines = set()
    for raw in df["cuisine"].dropna():
        for part in re.split(r"[,/;]", str(raw)):
            cuisines.add(part.strip())
    return sorted([c for c in cuisines if c])


CUISINE_SYNONYMS = {

    "Malay": [
        "melayu", "masakan melayu", "nasi lemak",
        "lauk melayu", "lauk kampung", "kampung style",
        "masakan kampung", "ayam masak merah", "asam pedas",
        "nasi goreng kampung", "ikan keli", "ikan bawal"
    ],

    "Chinese": [
        "cina", "chinese", "char kuey teow", "ckt",
        "dim sum", "wantan", "wonton", "claypot", "fried rice chinese",
        "kongfu", "kung fu"
    ],

    "Mamak": [
        "mamak", "nasi kandar", "roti canai", "roti telur",
        "roti tampal", "maggi goreng", "mee goreng mamak",
        "teh tarik", "nasi goreng mamak"
    ],

    "Indian": [
        "indian", "india", "biryani", "briyani", "tandoori",
        "naan", "butter chicken", "masala", "dhal"
    ],

    "Korean": [
        "korean", "korea", "kimchi", "ramyeon", "ramyun",
        "tteokbokki", "kimbap", "jajangmyeon", "buldak"
    ],

    "Japanese": [
        "japanese", "japan", "jepun", "sushi", "ramen",
        "donburi", "bento", "tempura", "udon"
    ],

    "Fast Food": [
        "kfc", "mcd", "mcD", "burger king", "a&w", "texas",
        "marrybrown", "pizza hut", "dominos", "subway",
        "fast food", "burger"
    ],

    "Nasi Campur": [
        "nasi campur", "lauk campur", "mixed rice", "economy rice",
        "kedai campur", "nasi berlauk"
    ],

    "Thailand": [
        "thai", "tomyam", "tom yam", "paprik",
        "pad kra pao", "thai food", "kerabu maggi",
        "somtam"
    ],

    "Arabic": [
        "arab", "arabic", "mandy", "mandi", "kabsah",
        "kebab", "shawarma", "hummus"
    ],

    "Dessert": [
        "dessert", "aiskrim", "ice cream", "cendol",
        "bingsu", "kek", "cake", "brownies", "pancake"
    ],

    "Beverage": [
        "drink", "beverage", "minum", "coffee", "kopi",
        "tea", "teh", "milkshake", "smoothie", "frappe",
        "boba", "bubble tea", "ngopi"
    ],

    "Western": [
        "western", "chicken chop", "lamb chop", "steak",
        "fries", "fish and chips", "pasta", "spaghetti",
        "carbonara", "bolognese", "lasagna", "grilled chicken"
    ],
}



def pick_cuisine(text):  # update from raja punya to allow multiple cuisine choices
    t = text.lower()
    c_intext = []

    for category, syns in CUISINE_SYNONYMS.items():
        if any(cat in t for cat in syns):
            c_intext.append(category)

    for c in get_known_cuisines():
        c_low = c.lower()
        if c_low and c_low in t:
            c_intext.append(c)

    seen = set()
    unique = []  # handle dupes e.g. "mamak nasi campur mamak kat SI" return ["Mamak", "Nasi Campur"]
    for c in c_intext:
        if c not in seen:
            seen.add(c)
            unique.append(c)

    return unique  # may be [] if nothing found
# =====================================================

# ========== Pick Meal Helpers and Dict ===============


MEALTYPE_SYNONYMS = {
    "Breakfast": ["pagi", "sarapan", "bfast", "breakfast", "breakie"],
    "Lunch": ["tengahari", "lunch", "afternoon", "noon"],
    "Tea Time": ["petang", "ptg", "tea", "tea time", "hi tea", "hi-tea", "snack"],
    "Dinner": ["malam", "mlm", "dinner", "supper", "night"]
}


def pick_meal_type(t):
    t = t.lower()

    for category, syns in MEALTYPE_SYNONYMS.items():
        if any(s in t for s in syns):
            return category

    return "Any"
# =====================================================

# ================= Halal Pref ========================


def pick_halal_pref(t):
    t = t.lower()
    if "halal" in t: return "Halal only"
    return "Doesn't matter"
# ====================================================

# ================= Travel Time Pref =================


def pick_travel(t):
    t = t.lower()
    m = re.search(r"(\d+)\s*(min|mins|minute)", t)
    return float(m.group(1)) if m else None
# ===================================================

# ========== Call all pick fx =======================


def parse_one_shot(t):
    cuisines = pick_cuisine(t)
    return {
        "cuisine": cuisines[0] if cuisines else None,
        "cuisines": cuisines,
        "max_budget": pick_budget(t),
        "meal_type": pick_meal_type(t),
        "max_travel": pick_travel(t),
        "halal_pref": pick_halal_pref(t),
        "location_pref": pick_location(t),
    }
# ===================================================

# =============== Produce Summary ===================


def prefs_summary(prefs):
    return (
        f"- Cuisine: **{prefs.get('cuisine') or 'any cuisine'}**\n"
        f"- Budget: **{('≤ RM'+str(int(prefs['max_budget']))) if prefs.get('max_budget') else 'any budget'}**\n"
        f"- Meal: **{prefs.get('meal_type', 'Any')}**\n"
        f"- Distance: **{('within '+str(int(prefs['max_travel']))+' mins') if prefs.get('max_travel') else 'any distance'}**\n"
        f"- Preference: **{'halal only' if prefs.get('halal_pref','').startswith('Halal') else 'halal or non-halal'}**\n"
        f"- Area: **{prefs.get('location_pref','Any')}**"
    )
# ===================================================


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
    st.caption("Powered by natural-language processing.")

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

    # storage for last ranking (for debug view)
    if "last_ranked" not in st.session_state:
        st.session_state["last_ranked"] = None
    if "last_prefs" not in st.session_state:
        st.session_state["last_prefs"] = None

    if st.button("🔄 Start Over"):
        reset_session()
        st.session_state["last_ranked"] = None
        st.session_state["last_prefs"] = None
        st.rerun()

    # 1) Render chat FIRST (shows all previous messages)
    render_chat()

    # 2) Debug toggle
    debug_mode = st.checkbox("🔍 Show score breakdown (debug mode)", value=False)

    # 3) If we have previous results and debug is ON, show them
    if debug_mode and st.session_state["last_ranked"] is not None:
        ranked = st.session_state["last_ranked"]
        st.subheader("🔎 Full Score Breakdown (Debug Mode)")
        debug_cols = [
            "name", "cuisine", "location",
            "score",
            "score_cuisine", "score_budget", "score_travel",
            "score_meal", "score_halal", "score_location", "score_rating"
        ]
        st.dataframe(ranked[debug_cols].head(25))

    # 4) Chat input is ALWAYS at the bottom
    text = st.chat_input("Tell me what you're craving...")

    if not text:
        return

    # 5) Process new message when user sends it
    add_message("user", text)

    prefs = parse_one_shot(text)
    st.session_state["last_prefs"] = prefs

    # basic guard: need at least one strong signal
    if not prefs["cuisine"] and prefs["max_budget"] is None and prefs["max_travel"] is None:
        add_message(
            "assistant",
            "I couldn't catch any specific cuisine, budget, or distance 😅<br><br>"
            "Try including at least one detail, e.g.:<br>"
            "- `cheap Malay food`<br>"
            "- `halal Western lunch under RM15`<br>"
            "- `any cuisine within 5 mins from UTP`"
        )
        st.rerun()

    add_message("assistant", "Here’s what I understood:<br><br>" + prefs_summary(prefs))

    df = load_catalog()
    ranked = score_restaurants(df, prefs, only_open_today=True, debug_mode=True)

    if ranked.empty:
        add_message(
            "assistant",
            "Hmm… no restaurants matched **and** are open today 😔<br>"
            "Try increasing distance or budget."
        )
        st.session_state["last_ranked"] = None
        st.rerun()

    # build suggestions text
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

    # store latest ranking for debug display on next run
    st.session_state["last_ranked"] = ranked

    # trigger rerun so new messages + debug can be rendered at top
    st.rerun()



if __name__ == "__main__":
    main()
