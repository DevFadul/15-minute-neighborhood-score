"""Console presentation layer: every print() in the app lives here.

Keeping formatting separate from app.py's control flow and from
scoring.py's math means changing how something LOOKS never risks
touching how it is CALCULATED.
"""

from neighborhood_score.constants import CATEGORIES, LINE_WIDTH


def print_header(title):
    """Print a banner-style section header."""
    print("=" * LINE_WIDTH)
    print(title.center(LINE_WIDTH))
    print("=" * LINE_WIDTH)


def print_separator():
    """Print a thin divider line, reused between sections."""
    print("-" * LINE_WIDTH)


def print_main_menu():
    """Print the numbered main menu."""
    print_header("15-MINUTE NEIGHBORHOOD SCORE  (SDG 11)")
    print("1. Create New Assessment")
    print("2. View All Assessments")
    print("3. View Assessment Detail & Score Breakdown")
    print("4. View Recommendations")
    print("5. Compare Two Assessments")
    print("6. Edit an Assessment")
    print("7. Delete an Assessment")
    print("8. About SDG 11 & Methodology")
    print("0. Exit")
    print("=" * LINE_WIDTH)


def round_half_up(value, ndigits=1):
    """Round using standard half-up rounding for predictable display output.

    Avoids Python's built-in round() "banker's rounding" (round-half-to-even),
    which can surprise users comparing hand-calculated scores against the
    program's displayed output (e.g. round(11.25, 1) -> 11.2 in Python's
    default rounding, but users expect 11.3).
    """
    shifted = value * (10 ** ndigits)
    rounded = int(shifted + 0.5) if shifted >= 0 else -int(-shifted + 0.5)
    return rounded / (10 ** ndigits)


def truncate_text(text, max_width):
    """Shorten text to max_width, marking truncation with an ellipsis.

    Used wherever user-supplied text (e.g. a nickname) is placed inside a
    fixed-width column -- format specifiers like {:<28} only pad short
    strings, they never truncate long ones, so without this a long
    nickname would overflow into neighboring columns.
    """
    if len(text) <= max_width:
        return text
    return text[: max_width - 1] + "…"


def print_assessment_summary_row(assessment, total_score, rating_band):
    """Print one line summarizing an assessment for a history list."""
    score_text = f"{round_half_up(total_score):.1f}/100"
    nickname_display = truncate_text(assessment.nickname, 28)
    print(f"[{assessment.assessment_id:>2}] {nickname_display:<28} "
          f"{score_text:>10}  {rating_band}")


def print_assessment_list(assessments, calculator):
    """Print every saved assessment as a summary row."""
    print_header("ALL ASSESSMENTS")
    if not assessments:
        print("No assessments yet. Choose option 1 to create your first one.")
        print_separator()
        return
    for assessment in assessments:
        total_score = calculator.calculate_total_score(assessment)
        rating_band = calculator.classify_rating(total_score)
        print_assessment_summary_row(assessment, total_score, rating_band)
    print_separator()


def print_score_breakdown(assessment, calculator):
    """Print the full per-category score table for one assessment."""
    nickname_display = truncate_text(assessment.nickname, 30)
    print_header(f"SCORE BREAKDOWN: {nickname_display}  (ID {assessment.assessment_id})")
    if assessment.location_note:
        print(f"Location note: {assessment.location_note}")
    print(f"{'Category':<30}{'Minutes':>9}{'Tier':>7}{'Points':>12}")
    print_separator()
    for category_key, info in CATEGORIES.items():
        minutes = assessment.get_time(category_key)
        tier_percentage = calculator.get_tier_percentage(minutes)
        points = calculator.calculate_category_score(category_key, minutes)
        points_text = f"{round_half_up(points):.1f} / {info['weight']}"
        print(f"{info['label']:<30}{minutes:>9.1f}{tier_percentage * 100:>6.0f}%{points_text:>12}")
    print_separator()
    total_score = calculator.calculate_total_score(assessment)
    rating_band = calculator.classify_rating(total_score)
    print(f"TOTAL SCORE: {round_half_up(total_score):.1f} / 100   ->   Rating: {rating_band.upper()}")
    print_separator()


def print_recommendations(messages):
    """Print a bullet list of recommendation messages."""
    print_header("RECOMMENDATIONS")
    for message in messages:
        print(f"- {message}")
    print_separator()


def print_comparison(assessment_a, score_a, band_a, assessment_b, score_b, band_b, calculator):
    """Print a side-by-side comparison of two assessments.

    Column headers use fixed-width "Option A"/"Option B" labels (with the
    full nicknames spelled out in a legend above) rather than embedding a
    user-supplied nickname directly into a fixed-width column -- a long
    nickname would otherwise overflow its column and run into the next one.
    """
    print_header("COMPARE ASSESSMENTS")
    print(f"Option A = {assessment_a.nickname} (ID {assessment_a.assessment_id})")
    print(f"Option B = {assessment_b.nickname} (ID {assessment_b.assessment_id})")
    print_separator()
    print(f"{'Category':<30}{'Option A':>15}{'Option B':>15}")
    print_separator()
    for category_key, info in CATEGORIES.items():
        points_a = calculator.calculate_category_score(category_key, assessment_a.get_time(category_key))
        points_b = calculator.calculate_category_score(category_key, assessment_b.get_time(category_key))
        print(f"{info['label']:<30}{round_half_up(points_a):>15.1f}{round_half_up(points_b):>15.1f}")
    print_separator()
    print(f"{'TOTAL SCORE':<30}{round_half_up(score_a):>15.1f}{round_half_up(score_b):>15.1f}")
    print(f"{'RATING':<30}{band_a:>15}{band_b:>15}")
    print_separator()
    if score_a > score_b:
        print(f"Verdict: '{assessment_a.nickname}' is the more walkable 15-minute neighborhood.")
    elif score_b > score_a:
        print(f"Verdict: '{assessment_b.nickname}' is the more walkable 15-minute neighborhood.")
    else:
        print("Verdict: Both neighborhoods score equally.")
    print_separator()


def print_about_info():
    """Print background on SDG 11 and the scoring methodology, from constants."""
    print_header("ABOUT SDG 11 & METHODOLOGY")
    print("SDG 11 (Sustainable Cities and Communities) calls for inclusive, safe,")
    print("resilient, and sustainable urban areas with access to green space and")
    print("affordable, accessible transport. The '15-minute city' concept holds")
    print("that residents should be able to reach daily essentials within a")
    print("15-minute walk, reducing car dependency and emissions.")
    print()
    print("This tool scores a neighborhood (0-100) across 6 weighted categories:")
    print_separator()
    for info in CATEGORIES.values():
        print(f"  {info['label']:<32} weight {info['weight']}")
    print_separator()
    print("Each category's walking time earns a tier percentage of its weight:")
    print("  <=5 min: 100%   6-10 min: 75%   11-15 min: 50%")
    print("  16-25 min: 20%   >25 min: 0%")
    print_separator()


def print_message(message, level="info"):
    """Print a message with a consistent prefix based on its level."""
    prefixes = {"info": "[OK]", "error": "[ERROR]", "warn": "[!]"}
    prefix = prefixes.get(level, "[OK]")
    print(f"{prefix} {message}")
