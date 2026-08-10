"""JSON persistence and CRUD operations for Assessment records."""

import json
import os

from neighborhood_score.constants import DATA_DIR, DATA_FILE_PATH
from neighborhood_score.models import Assessment


def load_all_assessments():
    """Load every saved assessment from disk.

    A missing file (first run) returns an empty list. A corrupted file is
    renamed to a .bak backup (instead of silently deleted) and the app
    continues with an empty list rather than crashing.
    """
    if not os.path.exists(DATA_FILE_PATH):
        return []

    try:
        with open(DATA_FILE_PATH, "r", encoding="utf-8") as data_file:
            raw_data = json.load(data_file)
        return [Assessment.from_dict(record) for record in raw_data.get("assessments", [])]
    except (json.JSONDecodeError, KeyError, TypeError):
        backup_path = DATA_FILE_PATH + ".bak"
        os.replace(DATA_FILE_PATH, backup_path)
        print(f"[!] The saved data file was unreadable and has been moved to "
              f"'{backup_path}'. Starting with an empty history.")
        return []


def save_all_assessments(assessments):
    """Write the full list of assessments back to the JSON data file."""
    os.makedirs(DATA_DIR, exist_ok=True)
    payload = {
        "schema_version": 1,
        "assessments": [assessment.to_dict() for assessment in assessments],
    }
    with open(DATA_FILE_PATH, "w", encoding="utf-8") as data_file:
        json.dump(payload, data_file, indent=2)


def generate_next_id(assessments):
    """Return the next unused assessment ID (max existing ID + 1, or 1)."""
    if not assessments:
        return 1
    return max(assessment.assessment_id for assessment in assessments) + 1


def add_assessment(new_assessment):
    """Append one new assessment to storage."""
    assessments = load_all_assessments()
    assessments.append(new_assessment)
    save_all_assessments(assessments)


def find_assessment_by_id(assessments, assessment_id):
    """Linear search for an assessment with the given ID, or None."""
    for assessment in assessments:
        if assessment.assessment_id == assessment_id:
            return assessment
    return None


def update_assessment(updated_assessment):
    """Replace the stored assessment that shares the updated one's ID."""
    assessments = load_all_assessments()
    for index, assessment in enumerate(assessments):
        if assessment.assessment_id == updated_assessment.assessment_id:
            assessments[index] = updated_assessment
            save_all_assessments(assessments)
            return True
    return False


def delete_assessment_by_id(assessment_id):
    """Remove the assessment with the given ID from storage."""
    assessments = load_all_assessments()
    remaining = [a for a in assessments if a.assessment_id != assessment_id]
    if len(remaining) == len(assessments):
        return False
    save_all_assessments(remaining)
    return True
