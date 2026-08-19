"""15-Minute Neighborhood Score -- console app for SDG 11.

Scores how walkable a neighborhood is: the user enters how many minutes it
takes to walk to six everyday places (grocery, healthcare, education,
transit, parks, retail), and the program turns that into a 0-100 score and
a rating. Assessments are saved to data/assessments.json so they're still
there next time the program runs.

All the scoring math and file saving/loading lives in neighborhood_score.py.
This file is just the menu, the screen output, and the input prompts.
"""

import neighborhood_score as ns

LINE_WIDTH = 60


# ---------------------------------------------------------------------------
# Small print helpers
# ---------------------------------------------------------------------------

def print_header(title):
    print("=" * LINE_WIDTH)
    print(title.center(LINE_WIDTH))
    print("=" * LINE_WIDTH)


def print_separator():
    print("-" * LINE_WIDTH)


def print_message(message, level="info"):
    prefixes = {"info": "[OK]", "error": "[ERROR]", "warn": "[!]"}
    print(f"{prefixes.get(level, '[OK]')} {message}")


def truncate_text(text, max_width):
    """Shorten text to max_width so it doesn't overflow a fixed-width column."""
    if len(text) <= max_width:
        return text
    return text[: max_width - 1] + "…"


# ---------------------------------------------------------------------------
# Small input helpers -- each one loops until the user gives a valid answer
# ---------------------------------------------------------------------------

def get_menu_choice(prompt_text, valid_choices):
    while True:
        choice = input(prompt_text).strip()
        if choice in valid_choices:
            return choice
        options = ", ".join(valid_choices)
        print(f"[ERROR] '{choice}' is not a valid option. Please choose one of: {options}.")


def get_nonempty_text(prompt_text):
    while True:
        text = input(prompt_text).strip()
        if text:
            return text
        print("[ERROR] This field cannot be empty.")


def get_minutes(prompt_text):
    while True:
        text = input(prompt_text).strip()
        try:
            minutes = float(text)
        except ValueError:
            print(f"[ERROR] '{text}' is not a valid number. Please enter minutes as a number (e.g. 8 or 12.5).")
            continue
        if minutes < 0:
            print("[ERROR] Travel time cannot be negative. Please try again.")
        elif minutes > ns.MAX_MINUTES:
            print(f"[ERROR] That doesn't look like a realistic one-way walk (max {ns.MAX_MINUTES} minutes). Please try again.")
        else:
            return minutes


def get_id_in_range(prompt_text, min_value, max_value):
    while True:
        text = input(prompt_text).strip()
        try:
            value = int(text)
        except ValueError:
            print(f"[ERROR] '{text}' is not a whole number. Please try again.")
            continue
        if value < min_value or value > max_value:
            print(f"[ERROR] Please enter a number between {min_value} and {max_value}.")
        else:
            return value


def get_yes_no(prompt_text):
    while True:
        answer = input(prompt_text).strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("[ERROR] Please answer 'y' or 'n'.")


# ---------------------------------------------------------------------------
# Printing an assessment
# ---------------------------------------------------------------------------

def print_assessment_list(assessments):
    print_header("ALL ASSESSMENTS")
    if not assessments:
        print("No assessments yet. Choose option 1 to create your first one.")
        print_separator()
        return
    for assessment in assessments:
        total_score = ns.calculate_total_score(assessment)
        rating = ns.classify_rating(total_score)
        score_text = f"{ns.round_half_up(total_score):.1f}/100"
        nickname_display = truncate_text(assessment["nickname"], 28)
        print(f"[{assessment['id']:>2}] {nickname_display:<28} {score_text:>10}  {rating}")
    print_separator()


def print_score_breakdown(assessment):
    nickname_display = truncate_text(assessment["nickname"], 30)
    print_header(f"SCORE BREAKDOWN: {nickname_display}  (ID {assessment['id']})")
    if assessment["location_note"]:
        print(f"Location note: {assessment['location_note']}")
    print(f"{'Category':<30}{'Minutes':>9}{'Tier':>7}{'Points':>12}")
    print_separator()
    for category_key, info in ns.CATEGORIES.items():
        minutes = assessment["category_times"][category_key]
        tier_percentage = ns.get_tier_percentage(minutes)
        points = ns.calculate_category_score(category_key, minutes)
        points_text = f"{ns.round_half_up(points):.1f} / {info['weight']}"
        print(f"{info['label']:<30}{minutes:>9.1f}{tier_percentage * 100:>6.0f}%{points_text:>12}")
    print_separator()
    total_score = ns.calculate_total_score(assessment)
    rating = ns.classify_rating(total_score)
    print(f"TOTAL SCORE: {ns.round_half_up(total_score):.1f} / 100   ->   Rating: {rating.upper()}")
    print_separator()


def print_recommendations(messages):
    print_header("RECOMMENDATIONS")
    for message in messages:
        print(f"- {message}")
    print_separator()


def print_comparison(assessment_a, assessment_b):
    print_header("COMPARE ASSESSMENTS")
    print(f"Option A = {assessment_a['nickname']} (ID {assessment_a['id']})")
    print(f"Option B = {assessment_b['nickname']} (ID {assessment_b['id']})")
    print_separator()
    print(f"{'Category':<30}{'Option A':>15}{'Option B':>15}")
    print_separator()
    for category_key, info in ns.CATEGORIES.items():
        points_a = ns.calculate_category_score(category_key, assessment_a["category_times"][category_key])
        points_b = ns.calculate_category_score(category_key, assessment_b["category_times"][category_key])
        print(f"{info['label']:<30}{ns.round_half_up(points_a):>15.1f}{ns.round_half_up(points_b):>15.1f}")
    print_separator()
    score_a = ns.calculate_total_score(assessment_a)
    score_b = ns.calculate_total_score(assessment_b)
    band_a = ns.classify_rating(score_a)
    band_b = ns.classify_rating(score_b)
    print(f"{'TOTAL SCORE':<30}{ns.round_half_up(score_a):>15.1f}{ns.round_half_up(score_b):>15.1f}")
    print(f"{'RATING':<30}{band_a:>15}{band_b:>15}")
    print_separator()
    if score_a > score_b:
        print(f"Verdict: '{assessment_a['nickname']}' is the more walkable 15-minute neighborhood.")
    elif score_b > score_a:
        print(f"Verdict: '{assessment_b['nickname']}' is the more walkable 15-minute neighborhood.")
    else:
        print("Verdict: Both neighborhoods score equally.")
    print_separator()


def print_about_info():
    print_header("ABOUT SDG 11 & METHODOLOGY")
    print("SDG 11 (Sustainable Cities and Communities) calls for inclusive, safe,")
    print("resilient, and sustainable urban areas with access to green space and")
    print("affordable, accessible transport. The '15-minute city' concept holds")
    print("that residents should be able to reach daily essentials within a")
    print("15-minute walk, reducing car dependency and emissions.")
    print()
    print("This tool scores a neighborhood (0-100) across 6 weighted categories:")
    print_separator()
    for info in ns.CATEGORIES.values():
        print(f"  {info['label']:<32} weight {info['weight']}")
    print_separator()
    print("Each category's walking time earns a tier percentage of its weight:")
    print("  <=5 min: 100%   6-10 min: 75%   11-15 min: 50%")
    print("  16-25 min: 20%   >25 min: 0%")
    print_separator()


# ---------------------------------------------------------------------------
# Menu actions -- one function per menu option
# ---------------------------------------------------------------------------

def print_main_menu():
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


def handle_new_assessment():
    print_header("NEW NEIGHBORHOOD ASSESSMENT")
    nickname = get_nonempty_text("Enter a nickname for this neighborhood: ")
    location_note = input("Enter an optional location note (or press Enter to skip): ").strip()

    print()
    print("Enter the estimated one-way WALKING time (minutes) to the")
    print(f"NEAREST place in each category (0-{ns.MAX_MINUTES}).\n")

    category_times = {}
    for category_key, info in ns.CATEGORIES.items():
        minutes = get_minutes(f"{info['label']} (minutes): ")
        category_times[category_key] = minutes

    assessments = ns.load_all_assessments()
    new_id = ns.generate_next_id(assessments)
    new_assessment = ns.make_assessment(new_id, nickname, location_note, category_times)
    ns.add_assessment(new_assessment)

    print()
    print_message(f'Assessment #{new_id} "{nickname}" saved.')
    print()
    print_score_breakdown(new_assessment)


def handle_view_all():
    assessments = ns.load_all_assessments()
    print_assessment_list(assessments)


def select_assessment_or_none(prompt_text="Enter Assessment ID: "):
    """Show the assessment list and let the user pick one by ID, or None."""
    assessments = ns.load_all_assessments()
    if not assessments:
        print_message("No assessments yet. Create one first (option 1).", "error")
        return None

    print_assessment_list(assessments)
    max_id = max(a["id"] for a in assessments)
    assessment_id = get_id_in_range(prompt_text, 1, max_id)
    assessment = ns.find_assessment_by_id(assessments, assessment_id)
    if assessment is None:
        print_message(f"No assessment with ID {assessment_id}.", "error")
        return None
    return assessment


def handle_view_detail():
    assessment = select_assessment_or_none("Enter Assessment ID to view: ")
    if assessment is not None:
        print_score_breakdown(assessment)


def handle_recommendations():
    assessment = select_assessment_or_none("Enter Assessment ID for recommendations: ")
    if assessment is not None:
        messages = ns.generate_recommendations(assessment)
        print_recommendations(messages)


def handle_compare():
    assessments = ns.load_all_assessments()
    if len(assessments) < 2:
        print_message("You need at least 2 assessments saved to compare.", "error")
        return

    print_assessment_list(assessments)
    max_id = max(a["id"] for a in assessments)
    id_a = get_id_in_range("Enter ID of first assessment: ", 1, max_id)
    id_b = get_id_in_range("Enter ID of second assessment: ", 1, max_id)

    if id_a == id_b:
        print_message("Please choose two different assessments to compare.", "error")
        return

    assessment_a = ns.find_assessment_by_id(assessments, id_a)
    assessment_b = ns.find_assessment_by_id(assessments, id_b)
    if assessment_a is None or assessment_b is None:
        print_message("One or both assessment IDs were not found.", "error")
        return

    print_comparison(assessment_a, assessment_b)


def handle_edit():
    assessment = select_assessment_or_none("Enter Assessment ID to edit: ")
    if assessment is None:
        return

    print("\nWhat would you like to edit?")
    print("1. Nickname")
    print("2. Location note")
    print("3. One category's walking time")
    sub_choice = get_menu_choice("Select an option (1-3): ", ["1", "2", "3"])

    if sub_choice == "1":
        assessment["nickname"] = get_nonempty_text("Enter new nickname: ")
    elif sub_choice == "2":
        assessment["location_note"] = input("Enter new location note: ").strip()
    elif sub_choice == "3":
        category_keys = list(ns.CATEGORIES.keys())
        for index, category_key in enumerate(category_keys, start=1):
            print(f"{index}. {ns.CATEGORIES[category_key]['label']}")
        category_number = get_id_in_range("Select category number: ", 1, len(category_keys))
        selected_key = category_keys[category_number - 1]
        new_minutes = get_minutes(f"New walking time for {ns.CATEGORIES[selected_key]['label']} (minutes): ")
        assessment["category_times"][selected_key] = new_minutes

    ns.update_assessment(assessment)
    print_message("Assessment updated.")
    print_score_breakdown(assessment)


def handle_delete():
    assessment = select_assessment_or_none("Enter Assessment ID to delete: ")
    if assessment is None:
        return

    confirmed = get_yes_no(f"Delete '{assessment['nickname']}' (ID {assessment['id']})? (y/n): ")
    if not confirmed:
        print_message("Delete cancelled.")
        return

    ns.delete_assessment_by_id(assessment["id"])
    print_message(f"Assessment #{assessment['id']} deleted.")


def handle_about():
    print_about_info()


# ---------------------------------------------------------------------------
# Main program loop
# ---------------------------------------------------------------------------

def main():
    print("Welcome to the 15-Minute Neighborhood Score tool.")
    print("Assess how walkable your neighborhood is, and compare options")
    print("to make more sustainable, informed housing decisions.\n")

    while True:
        print_main_menu()
        choice = get_menu_choice("Select an option (0-8): ", [str(n) for n in range(9)])

        if choice == "1":
            handle_new_assessment()
        elif choice == "2":
            handle_view_all()
        elif choice == "3":
            handle_view_detail()
        elif choice == "4":
            handle_recommendations()
        elif choice == "5":
            handle_compare()
        elif choice == "6":
            handle_edit()
        elif choice == "7":
            handle_delete()
        elif choice == "8":
            handle_about()
        elif choice == "0":
            print("Goodbye! Thanks for using 15-Minute Neighborhood Score.")
            break


if __name__ == "__main__":
    main()
