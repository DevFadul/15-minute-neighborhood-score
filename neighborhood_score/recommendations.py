"""Generates human-readable improvement tips from a scored assessment."""

from neighborhood_score.constants import CATEGORIES

# One canned advocacy/improvement tip per category, looked up by key --
# the same table-driven lookup pattern used for tier percentages.
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


def get_tip_for_category(category_key):
    """Look up the canned improvement tip for a category key."""
    return CATEGORY_TIPS.get(category_key, "No specific tip available for this category.")


def generate_recommendations(assessment, calculator, num_weak_categories=2):
    """Return a list of tip strings for the assessment's weakest categories.

    Handles the perfect-score edge case gracefully instead of returning an
    empty, unexplained list.
    """
    ranked = calculator.rank_categories_ascending(assessment)
    max_possible = sum(info["weight"] for info in CATEGORIES.values())
    total_score = calculator.calculate_total_score(assessment)

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


def build_overall_summary_message(total_score, rating_band):
    """Build one human-readable summary line combining score and rating."""
    return f"Overall score: {total_score:.1f}/100 -- Rated '{rating_band}'."
