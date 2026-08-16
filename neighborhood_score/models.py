"""Data entity for a single neighborhood assessment."""

from datetime import datetime


class Assessment:
    """Holds the raw data collected for one neighborhood.

    Deliberately does NOT store a total score or rating -- those are
    always derived on demand by ScoreCalculator, so there is exactly one
    source of truth and no risk of a cached score going stale after an
    edit.
    """

    def __init__(self, assessment_id, nickname, location_note, category_times, created_at=None, auto=False):
        self.assessment_id = assessment_id
        self.nickname = nickname
        self.location_note = location_note
        self.category_times = category_times
        self.created_at = created_at if created_at else datetime.now().isoformat(timespec="seconds")
        # True when walk times came from an automatic address estimate rather
        # than a person's own measurements -- surfaced as a "refine this" hint
        # in the web UI. Console-created assessments are always False.
        self.auto = auto

    def to_dict(self):
        """Serialize this assessment into a JSON-safe dictionary."""
        return {
            "id": self.assessment_id,
            "nickname": self.nickname,
            "location_note": self.location_note,
            "created_at": self.created_at,
            "category_times": dict(self.category_times),
            "auto": self.auto,
        }

    @staticmethod
    def from_dict(data):
        """Rebuild an Assessment object from a dictionary loaded from JSON."""
        return Assessment(
            assessment_id=data["id"],
            nickname=data["nickname"],
            location_note=data.get("location_note", ""),
            category_times=dict(data["category_times"]),
            created_at=data.get("created_at"),
            auto=data.get("auto", False),
        )

    def get_time(self, category_key):
        """Return the recorded walking time (minutes) for one category."""
        return self.category_times[category_key]

    def set_time(self, category_key, minutes):
        """Update the walking time (minutes) for one category."""
        self.category_times[category_key] = minutes
