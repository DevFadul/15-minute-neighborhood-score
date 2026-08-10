"""Reusable input-validation helpers.

Every input() call anywhere else in the app routes through one of these
functions, so validation behavior (and its error messages) only needs to
be correct in one place.
"""


def is_valid_float(text):
    """Return True if text can be parsed as a float."""
    try:
        float(text)
        return True
    except ValueError:
        return False


def prompt_nonempty_string(prompt_text):
    """Repeat a prompt until the user enters a non-blank string."""
    while True:
        raw_value = input(prompt_text).strip()
        if raw_value:
            return raw_value
        print("[ERROR] This field cannot be empty. Please enter a value.")


def prompt_float_in_range(prompt_text, min_value, max_value):
    """Repeat a prompt until the user enters a float within [min_value, max_value]."""
    while True:
        raw_value = input(prompt_text).strip()
        if not is_valid_float(raw_value):
            print(f"[ERROR] '{raw_value}' is not a valid number. "
                  f"Please enter minutes as a number (e.g. 8 or 12.5).")
            continue
        value = float(raw_value)
        if value < min_value:
            print(f"[ERROR] Value cannot be negative. Please enter a value between "
                  f"{min_value} and {max_value}.")
            continue
        if value > max_value:
            print(f"[ERROR] That doesn't look realistic (max {max_value}). "
                  f"Please re-enter a value between {min_value} and {max_value}.")
            continue
        return value


def prompt_int_in_range(prompt_text, min_value, max_value):
    """Repeat a prompt until the user enters an int within [min_value, max_value]."""
    while True:
        raw_value = input(prompt_text).strip()
        if not raw_value.lstrip("-").isdigit():
            print(f"[ERROR] Please enter a whole number between {min_value} and {max_value}.")
            continue
        value = int(raw_value)
        if value < min_value or value > max_value:
            print(f"[ERROR] Please enter a number between {min_value} and {max_value}.")
            continue
        return value


def prompt_menu_choice(prompt_text, valid_choices):
    """Repeat a prompt until the user enters one of valid_choices (strings)."""
    while True:
        raw_value = input(prompt_text).strip()
        if raw_value in valid_choices:
            return raw_value
        print(f"[ERROR] '{raw_value}' is not a valid option. "
              f"Please choose one of: {', '.join(valid_choices)}.")


def prompt_yes_no(prompt_text):
    """Ask a yes/no question, reusing prompt_menu_choice, and return a bool."""
    choice = prompt_menu_choice(prompt_text, ["y", "n"])
    return choice == "y"
