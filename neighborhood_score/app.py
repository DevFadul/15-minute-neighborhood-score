"""Application controller: the menu loop and one handler per menu option.

Each handler composes the validation, storage, scoring, recommendations,
and ui modules -- this file contains no business logic or math of its own.
"""

from neighborhood_score import storage, ui, recommendations
from neighborhood_score.constants import CATEGORIES, MAX_MINUTES
from neighborhood_score.models import Assessment
from neighborhood_score.scoring import create_default_calculator
from neighborhood_score.validation import (
    prompt_nonempty_string,
    prompt_float_in_range,
    prompt_int_in_range,
    prompt_menu_choice,
    prompt_yes_no,
)


def run():
    """Run the main menu-driven application loop until the user exits."""
    calculator = create_default_calculator()
    print_welcome_banner()

    while True:
        ui.print_main_menu()
        choice = prompt_menu_choice("Select an option (0-8): ", [str(n) for n in range(9)])

        if choice == "1":
            handle_new_assessment(calculator)
        elif choice == "2":
            handle_view_all(calculator)
        elif choice == "3":
            handle_view_detail(calculator)
        elif choice == "4":
            handle_recommendations(calculator)
        elif choice == "5":
            handle_compare(calculator)
        elif choice == "6":
            handle_edit(calculator)
        elif choice == "7":
            handle_delete()
        elif choice == "8":
            handle_about()
        elif choice == "0":
            print("Goodbye! Thanks for using 15-Minute Neighborhood Score.")
            break


def print_welcome_banner():
    """Print a one-time welcome message when the app starts."""
    print("Welcome to the 15-Minute Neighborhood Score tool.")
    print("Assess how walkable your neighborhood is, and compare options")
    print("to make more sustainable, informed housing decisions.\n")


def handle_new_assessment(calculator):
    """Collect a new assessment's data from the user and save it."""
    ui.print_header("NEW NEIGHBORHOOD ASSESSMENT")
    nickname = prompt_nonempty_string("Enter a nickname for this neighborhood: ")
    location_note = input("Enter an optional location note (or press Enter to skip): ").strip()

    print()
    print("Enter the estimated one-way WALKING time (minutes) to the")
    print(f"NEAREST place in each category (0-{MAX_MINUTES}).\n")

    category_times = {}
    for category_key, info in CATEGORIES.items():
        minutes = prompt_float_in_range(f"{info['label']} (minutes): ", 0, MAX_MINUTES)
        category_times[category_key] = minutes

    assessments = storage.load_all_assessments()
    new_id = storage.generate_next_id(assessments)
    new_assessment = Assessment(new_id, nickname, location_note, category_times)
    storage.add_assessment(new_assessment)

    print()
    ui.print_message(f'Assessment #{new_id} "{nickname}" saved.')
    print()
    ui.print_score_breakdown(new_assessment, calculator)


def handle_view_all(calculator):
    """Display every saved assessment as a summary list."""
    assessments = storage.load_all_assessments()
    ui.print_assessment_list(assessments, calculator)


def select_assessment_or_none(prompt_text="Enter Assessment ID: "):
    """Show the assessment list and let the user pick one by ID, or None."""
    assessments = storage.load_all_assessments()
    if not assessments:
        ui.print_message("No assessments yet. Create one first (option 1).", "error")
        return None

    ui.print_assessment_list(assessments, create_default_calculator())
    assessment_id = prompt_int_in_range(prompt_text, 1, max(a.assessment_id for a in assessments))
    assessment = storage.find_assessment_by_id(assessments, assessment_id)
    if assessment is None:
        ui.print_message(f"No assessment with ID {assessment_id}.", "error")
        return None
    return assessment


def handle_view_detail(calculator):
    """Show the full score breakdown for one selected assessment."""
    assessment = select_assessment_or_none("Enter Assessment ID to view: ")
    if assessment is not None:
        ui.print_score_breakdown(assessment, calculator)


def handle_recommendations(calculator):
    """Show improvement recommendations for one selected assessment."""
    assessment = select_assessment_or_none("Enter Assessment ID for recommendations: ")
    if assessment is not None:
        messages = recommendations.generate_recommendations(assessment, calculator)
        ui.print_recommendations(messages)


def handle_compare(calculator):
    """Compare two different saved assessments side by side."""
    assessments = storage.load_all_assessments()
    if len(assessments) < 2:
        ui.print_message("You need at least 2 assessments saved to compare.", "error")
        return

    ui.print_assessment_list(assessments, calculator)
    max_id = max(a.assessment_id for a in assessments)
    id_a = prompt_int_in_range("Enter ID of first assessment: ", 1, max_id)
    id_b = prompt_int_in_range("Enter ID of second assessment: ", 1, max_id)

    if id_a == id_b:
        ui.print_message("Please choose two different assessments to compare.", "error")
        return

    assessment_a = storage.find_assessment_by_id(assessments, id_a)
    assessment_b = storage.find_assessment_by_id(assessments, id_b)
    if assessment_a is None or assessment_b is None:
        ui.print_message("One or both assessment IDs were not found.", "error")
        return

    score_a = calculator.calculate_total_score(assessment_a)
    score_b = calculator.calculate_total_score(assessment_b)
    band_a = calculator.classify_rating(score_a)
    band_b = calculator.classify_rating(score_b)
    ui.print_comparison(assessment_a, score_a, band_a, assessment_b, score_b, band_b, calculator)


def handle_edit(calculator):
    """Edit an existing assessment: rename, edit note, or update one category's time."""
    assessment = select_assessment_or_none("Enter Assessment ID to edit: ")
    if assessment is None:
        return

    print("\nWhat would you like to edit?")
    print("1. Nickname")
    print("2. Location note")
    print("3. One category's walking time")
    sub_choice = prompt_menu_choice("Select an option (1-3): ", ["1", "2", "3"])

    if sub_choice == "1":
        assessment.nickname = prompt_nonempty_string("Enter new nickname: ")
    elif sub_choice == "2":
        assessment.location_note = input("Enter new location note: ").strip()
    elif sub_choice == "3":
        for index, (category_key, info) in enumerate(CATEGORIES.items(), start=1):
            print(f"{index}. {info['label']}")
        category_keys = list(CATEGORIES.keys())
        category_number = prompt_int_in_range("Select category number: ", 1, len(category_keys))
        selected_key = category_keys[category_number - 1]
        new_minutes = prompt_float_in_range(
            f"New walking time for {CATEGORIES[selected_key]['label']} (minutes): ", 0, MAX_MINUTES
        )
        assessment.set_time(selected_key, new_minutes)

    storage.update_assessment(assessment)
    ui.print_message("Assessment updated.")
    ui.print_score_breakdown(assessment, calculator)


def handle_delete():
    """Delete a selected assessment, after confirmation."""
    assessment = select_assessment_or_none("Enter Assessment ID to delete: ")
    if assessment is None:
        return

    confirmed = prompt_yes_no(f"Delete '{assessment.nickname}' (ID {assessment.assessment_id})? (y/n): ")
    if not confirmed:
        ui.print_message("Delete cancelled.")
        return

    storage.delete_assessment_by_id(assessment.assessment_id)
    ui.print_message(f"Assessment #{assessment.assessment_id} deleted.")


def handle_about():
    """Show the About/methodology screen."""
    ui.print_about_info()
