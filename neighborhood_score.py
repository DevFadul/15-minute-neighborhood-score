"""15-Minute Neighborhood Score -- shared scoring logic and data storage.

Used by both the console program (main.py) and the web app (web/).
An "assessment" is just a dictionary, saved and loaded straight from JSON:

    {
        "id": 1,
        "nickname": "Current Apartment",
        "location_note": "Jalan Ampang, KL",
        "created_at": "2026-08-10T21:15:03",
        "category_times": {"grocery": 4, "healthcare": 12, ...},
        "auto": False,
    }
"""

import json
import os
from datetime import datetime

# ---------------------------------------------------------------------------
# Category weights, walking-time tiers, and rating bands
# ---------------------------------------------------------------------------

# Each amenity category, with its weight out of 100 and its console label.
CATEGORIES = {
    "grocery": {"label": "Grocery / Fresh Food Access", "weight": 20},
    "healthcare": {"label": "Healthcare / Pharmacy", "weight": 15},
    "education": {"label": "Education / Childcare", "weight": 15},
    "transit": {"label": "Public Transit Access", "weight": 20},
    "parks": {"label": "Parks / Green Space", "weight": 15},
    "retail": {"label": "Everyday Retail & Services", "weight": 15},
}

# (upper_bound_minutes, percentage) pairs, checked top to bottom.
# The last row (None) matches anything larger than the row above it.
TIER_TABLE = [
    (5, 1.00),
    (10, 0.75),
    (15, 0.50),
    (25, 0.20),
    (None, 0.00),
]

# (minimum_score, rating_label) pairs, checked top to bottom.
RATING_BANDS = [
    (85, "Excellent"),
    (70, "Good"),
    (50, "Fair"),
    (0, "Poor"),
]

# One improvement tip per category, used by generate_recommendations().
CATEGORY_TIPS = {
    "grocery": "Limited fresh food access nearby. Consider advocating for a "
               "local farmers market, mini-mart, or community garden.",
    "healthcare": "No nearby clinic or pharmacy. Look into telehealth options, "
                  "or raise this gap with local health authorities.",
    "education": "Schools or childcare are far away. Carpooling groups or "
                 "petitioning for a satellite childcare centre may help.",
    "transit": "Public transit is hard to reach. Check for feeder bus routes, "
               "or support local calls for a new stop nearby.",
    "parks": "Little green space within reach. Consider advocating for a "
             "pocket park or better use of vacant nearby land.",
    "retail": "Everyday services (bank, post office, etc.) are far. Look for "
              "postal/banking agents or online alternatives in the meantime.",
}

MAX_MINUTES = 180

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DATA_FILE_PATH = os.path.join(DATA_DIR, "assessments.json")


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def get_tier_percentage(minutes):
    """Turn a walking time into the percentage of points it earns."""
    for upper_bound, percentage in TIER_TABLE:
        if upper_bound is None or minutes <= upper_bound:
            return percentage
    return 0.0


def calculate_category_score(category_key, minutes):
    """Points earned for one category, out of that category's weight."""
    weight = CATEGORIES[category_key]["weight"]
    return weight * get_tier_percentage(minutes)


def calculate_total_score(assessment):
    """Add up every category's points into one 0-100 score."""
    total = 0
    for category_key in CATEGORIES:
        minutes = assessment["category_times"][category_key]
        total += calculate_category_score(category_key, minutes)
    return total


def classify_rating(total_score):
    """Turn a 0-100 score into a rating label."""
    for threshold, label in RATING_BANDS:
        if total_score >= threshold:
            return label
    return RATING_BANDS[-1][1]


def rank_categories_ascending(assessment):
    """Return (category_key, points_earned) pairs, weakest category first."""
    scores = []
    for category_key in CATEGORIES:
        minutes = assessment["category_times"][category_key]
        points = calculate_category_score(category_key, minutes)
        scores.append((category_key, points))
    scores.sort(key=lambda pair: pair[1])
    return scores


def round_half_up(value, ndigits=1):
    """Round using standard half-up rounding (11.25 -> 11.3, not Python's default 11.2)."""
    shifted = value * (10 ** ndigits)
    rounded = int(shifted + 0.5) if shifted >= 0 else -int(-shifted + 0.5)
    return rounded / (10 ** ndigits)


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

def get_tip_for_category(category_key):
    """Look up the canned improvement tip for a category key."""
    return CATEGORY_TIPS.get(category_key, "No specific tip available for this category.")


def generate_recommendations(assessment, num_weak_categories=2):
    """Return a list of tip strings for the assessment's weakest categories."""
    ranked = rank_categories_ascending(assessment)
    max_possible = sum(info["weight"] for info in CATEGORIES.values())
    total_score = calculate_total_score(assessment)

    if total_score >= max_possible - 0.01:
        return ["This neighborhood scores at or near the maximum -- no major "
                "accessibility gaps were found. Great example of a 15-minute neighborhood!"]

    messages = []
    for category_key, points_earned in ranked[:num_weak_categories]:
        weight = CATEGORIES[category_key]["weight"]
        if points_earned >= weight * 0.75:
            continue
        label = CATEGORIES[category_key]["label"]
        tip = get_tip_for_category(category_key)
        messages.append(f"{label}: {tip}")

    if not messages:
        messages.append("This neighborhood scores reasonably well across all categories -- "
                         "no urgent gaps stand out.")
    return messages


# ---------------------------------------------------------------------------
# Saving and loading assessments (a JSON file on disk)
# ---------------------------------------------------------------------------

def load_all_assessments():
    """Load every saved assessment from disk as a list of dictionaries.

    A missing file (first run) returns an empty list. A corrupted file is
    renamed to a .bak backup (instead of silently deleted) and the app
    continues with an empty list rather than crashing.
    """
    if not os.path.exists(DATA_FILE_PATH):
        return []

    try:
        with open(DATA_FILE_PATH, "r", encoding="utf-8") as data_file:
            raw_data = json.load(data_file)
        assessments = raw_data.get("assessments", [])
        for assessment in assessments:
            # Older saved files predate these fields.
            assessment.setdefault("auto", False)
            assessment.setdefault("lat", None)
            assessment.setdefault("lon", None)
        return assessments
    except (json.JSONDecodeError, KeyError, TypeError):
        backup_path = DATA_FILE_PATH + ".bak"
        os.replace(DATA_FILE_PATH, backup_path)
        print(f"[!] The saved data file was unreadable and has been moved to "
              f"'{backup_path}'. Starting with an empty history.")
        return []


def save_all_assessments(assessments):
    """Write the full list of assessments back to the JSON data file."""
    os.makedirs(DATA_DIR, exist_ok=True)
    payload = {"schema_version": 1, "assessments": assessments}
    with open(DATA_FILE_PATH, "w", encoding="utf-8") as data_file:
        json.dump(payload, data_file, indent=2)


def generate_next_id(assessments):
    """Return the next unused assessment ID (max existing ID + 1, or 1)."""
    if not assessments:
        return 1
    return max(assessment["id"] for assessment in assessments) + 1


def make_assessment(assessment_id, nickname, location_note, category_times,
                    auto=False, lat=None, lon=None):
    """Build a new assessment dictionary.

    lat/lon are only filled in by the web app when a real address was looked
    up, so the 3D view can load that spot's real map data. The console app
    leaves them as None.
    """
    return {
        "id": assessment_id,
        "nickname": nickname,
        "location_note": location_note,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "category_times": category_times,
        "auto": auto,
        "lat": lat,
        "lon": lon,
    }


def add_assessment(new_assessment):
    """Append one new assessment to storage."""
    assessments = load_all_assessments()
    assessments.append(new_assessment)
    save_all_assessments(assessments)


def find_assessment_by_id(assessments, assessment_id):
    """Linear search for an assessment with the given ID, or None."""
    for assessment in assessments:
        if assessment["id"] == assessment_id:
            return assessment
    return None


def update_assessment(updated_assessment):
    """Replace the stored assessment that shares the updated one's ID."""
    assessments = load_all_assessments()
    for index, assessment in enumerate(assessments):
        if assessment["id"] == updated_assessment["id"]:
            assessments[index] = updated_assessment
            save_all_assessments(assessments)
            return True
    return False


def delete_assessment_by_id(assessment_id):
    """Remove the assessment with the given ID from storage."""
    assessments = load_all_assessments()
    remaining = [a for a in assessments if a["id"] != assessment_id]
    if len(remaining) == len(assessments):
        return False
    save_all_assessments(remaining)
    return True
