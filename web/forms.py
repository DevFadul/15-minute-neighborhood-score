"""Server-side validation for web forms, mirroring the rules in neighborhood_score.validation."""

from neighborhood_score.constants import CATEGORIES, MAX_MINUTES


def validate_nickname(raw_value):
    """Return (nickname, error). error is None when valid."""
    value = (raw_value or "").strip()
    if not value:
        return None, "Nickname cannot be empty."
    return value, None


def validate_minutes(raw_value, label):
    """Return (minutes, error). error is None when valid."""
    raw_value = (raw_value or "").strip()
    try:
        minutes = float(raw_value)
    except ValueError:
        return None, f"{label}: '{raw_value}' is not a valid number."
    if minutes < 0 or minutes > MAX_MINUTES:
        return None, f"{label}: enter a value between 0 and {MAX_MINUTES}."
    return minutes, None


def parse_category_times(form):
    """Read every category's minutes field from a submitted form.

    Returns (category_times, errors). category_times only has all 6 keys
    when errors is empty.
    """
    category_times = {}
    errors = []
    for category_key, info in CATEGORIES.items():
        minutes, error = validate_minutes(form.get(category_key), info["label"])
        if error:
            errors.append(error)
        else:
            category_times[category_key] = minutes
    return category_times, errors
