"""Computes 15-Minute Neighborhood scores from an Assessment's raw data.

All scoring math lives in one place (ScoreCalculator) so that every part
of the app -- the detail view, the history list, recommendations, and
comparisons -- computes the score identically instead of duplicating the
formula.
"""

from neighborhood_score.constants import CATEGORIES, TIER_TABLE, RATING_BANDS


class ScoreCalculator:
    """Applies the weight/tier/rating configuration to Assessment objects."""

    def __init__(self):
        self.category_weights = CATEGORIES
        self.tier_table = TIER_TABLE
        self.rating_bands = RATING_BANDS

    def get_tier_percentage(self, minutes):
        """Convert a walking time in minutes to a tier percentage (0.0-1.0).

        This single function is applied identically to every category --
        the same piece of logic is reused six times rather than copied
        into six near-identical if/elif blocks.
        """
        for upper_bound, percentage in self.tier_table:
            if upper_bound is None or minutes <= upper_bound:
                return percentage
        return 0.0

    def calculate_category_score(self, category_key, minutes):
        """Return the points earned (out of that category's weight)."""
        weight = self.category_weights[category_key]["weight"]
        tier_percentage = self.get_tier_percentage(minutes)
        return weight * tier_percentage

    def calculate_all_category_scores(self, assessment):
        """Return a dict of category_key -> points earned, for every category."""
        scores = {}
        for category_key in self.category_weights:
            minutes = assessment.get_time(category_key)
            scores[category_key] = self.calculate_category_score(category_key, minutes)
        return scores

    def calculate_total_score(self, assessment):
        """Accumulate every category's points into one 0-100 total score."""
        total = 0.0
        for category_key in self.category_weights:
            minutes = assessment.get_time(category_key)
            total += self.calculate_category_score(category_key, minutes)
        return total

    def classify_rating(self, total_score):
        """Map a 0-100 total score to a rating label (Excellent/Good/Fair/Poor)."""
        for threshold, label in self.rating_bands:
            if total_score >= threshold:
                return label
        return self.rating_bands[-1][1]

    def rank_categories_ascending(self, assessment):
        """Return (category_key, points_earned) pairs sorted weakest-first.

        Used to surface the categories most in need of improvement when
        generating recommendations.
        """
        scores = self.calculate_all_category_scores(assessment)
        return sorted(scores.items(), key=lambda item: item[1])


def create_default_calculator():
    """Factory function separating 'how to build a calculator' from its use."""
    return ScoreCalculator()
