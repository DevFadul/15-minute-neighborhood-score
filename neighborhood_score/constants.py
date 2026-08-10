"""Shared configuration data for the 15-Minute Neighborhood Score app.

Centralizing these tables here means the scoring logic, the console menu,
and the "About" screen all read from the exact same numbers -- nothing
about weights, tiers, or ratings is ever hard-coded a second time
elsewhere in the codebase.
"""

import os

# Each amenity category a neighborhood is scored on, with its weight
# (out of 100) and the console label shown to the user. Keys are stable
# identifiers used in storage; labels can change without touching data.
CATEGORIES = {
    "grocery": {"label": "Grocery / Fresh Food Access", "weight": 20},
    "healthcare": {"label": "Healthcare / Pharmacy", "weight": 15},
    "education": {"label": "Education / Childcare", "weight": 15},
    "transit": {"label": "Public Transit Access", "weight": 20},
    "parks": {"label": "Parks / Green Space", "weight": 15},
    "retail": {"label": "Everyday Retail & Services", "weight": 15},
}

# Piecewise mapping from one-way walking minutes to the percentage of a
# category's weight earned. Each tuple is (upper_bound_minutes, percentage);
# the last row's upper bound is None, meaning "anything above the previous
# bound". Read top-to-bottom, first matching row wins.
TIER_TABLE = [
    (5, 1.00),
    (10, 0.75),
    (15, 0.50),
    (25, 0.20),
    (None, 0.00),
]

# Overall 0-100 score bands, checked from highest to lowest.
RATING_BANDS = [
    (85, "Excellent"),
    (70, "Good"),
    (50, "Fair"),
    (0, "Poor"),
]

MAX_MINUTES = 180
LINE_WIDTH = 60

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DATA_FILE_PATH = os.path.join(DATA_DIR, "assessments.json")


def get_category_keys():
    """Return the list of category keys in a stable, consistent order."""
    return list(CATEGORIES.keys())
