"""View functions for the web UI.

Every calculation and persistence call delegates to neighborhood_score.* --
the same package the console app (main.py) uses -- so both interfaces stay
in sync against the same data/assessments.json and the same scoring rules.
"""

from flask import Blueprint, flash, redirect, render_template, request, url_for

from neighborhood_score import recommendations, storage
from neighborhood_score.constants import CATEGORIES, MAX_MINUTES, RATING_BANDS, TIER_TABLE
from neighborhood_score.models import Assessment
from neighborhood_score.scoring import create_default_calculator
from neighborhood_score.ui import round_half_up

from web.forms import parse_category_times, validate_nickname

bp = Blueprint("main", __name__)

RATING_COLORS = {
    "Excellent": "emerald",
    "Good": "sky",
    "Fair": "amber",
    "Poor": "rose",
}


def _assessment_or_none(assessment_id):
    assessment = storage.find_assessment_by_id(storage.load_all_assessments(), assessment_id)
    if assessment is None:
        flash(f"No assessment with ID {assessment_id}.", "error")
    return assessment


@bp.route("/")
def index():
    calculator = create_default_calculator()
    rows = []
    for assessment in storage.load_all_assessments():
        total_score = calculator.calculate_total_score(assessment)
        rating = calculator.classify_rating(total_score)
        rows.append({
            "assessment": assessment,
            "score": round_half_up(total_score),
            "rating": rating,
            "color": RATING_COLORS[rating],
        })
    rows.sort(key=lambda row: row["score"], reverse=True)
    return render_template("index.html", rows=rows)


@bp.route("/assessments/new", methods=["GET", "POST"])
def new_assessment():
    if request.method == "POST":
        nickname, nickname_error = validate_nickname(request.form.get("nickname"))
        location_note = (request.form.get("location_note") or "").strip()
        category_times, time_errors = parse_category_times(request.form)

        errors = ([nickname_error] if nickname_error else []) + time_errors
        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("new_assessment.html", categories=CATEGORIES,
                                    max_minutes=MAX_MINUTES, form=request.form), 400

        assessments = storage.load_all_assessments()
        new_id = storage.generate_next_id(assessments)
        assessment = Assessment(new_id, nickname, location_note, category_times)
        storage.add_assessment(assessment)
        flash(f'Assessment #{new_id} "{nickname}" saved.', "success")
        return redirect(url_for("main.detail", assessment_id=new_id))

    return render_template("new_assessment.html", categories=CATEGORIES,
                            max_minutes=MAX_MINUTES, form={})


@bp.route("/preview-score", methods=["POST"])
def preview_score():
    """HTMX endpoint: compute a live score from in-progress form data without saving it."""
    category_times, errors = parse_category_times(request.form)
    if errors:
        return render_template("_score_preview.html", ready=False)

    calculator = create_default_calculator()
    draft = Assessment(0, "preview", "", category_times)
    total_score = calculator.calculate_total_score(draft)
    rating = calculator.classify_rating(total_score)
    return render_template("_score_preview.html", ready=True,
                            score=round_half_up(total_score), rating=rating,
                            color=RATING_COLORS[rating])


@bp.route("/assessments/<int:assessment_id>")
def detail(assessment_id):
    assessment = _assessment_or_none(assessment_id)
    if assessment is None:
        return redirect(url_for("main.index"))

    calculator = create_default_calculator()
    category_scores = calculator.calculate_all_category_scores(assessment)
    total_score = calculator.calculate_total_score(assessment)
    rating = calculator.classify_rating(total_score)

    breakdown = []
    for category_key, info in CATEGORIES.items():
        minutes = assessment.get_time(category_key)
        breakdown.append({
            "label": info["label"],
            "minutes": minutes,
            "tier_percent": calculator.get_tier_percentage(minutes) * 100,
            "points": round_half_up(category_scores[category_key]),
            "weight": info["weight"],
        })

    tips = recommendations.generate_recommendations(assessment, calculator)

    return render_template(
        "detail.html", assessment=assessment, breakdown=breakdown,
        score=round_half_up(total_score), rating=rating, color=RATING_COLORS[rating],
        tips=tips,
        chart_labels=[row["label"] for row in breakdown],
        chart_points=[row["points"] for row in breakdown],
    )


@bp.route("/assessments/<int:assessment_id>/edit", methods=["GET", "POST"])
def edit_assessment(assessment_id):
    assessment = _assessment_or_none(assessment_id)
    if assessment is None:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        nickname, nickname_error = validate_nickname(request.form.get("nickname"))
        location_note = (request.form.get("location_note") or "").strip()
        category_times, time_errors = parse_category_times(request.form)

        errors = ([nickname_error] if nickname_error else []) + time_errors
        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("edit_assessment.html", assessment=assessment,
                                    categories=CATEGORIES, max_minutes=MAX_MINUTES,
                                    form=request.form), 400

        assessment.nickname = nickname
        assessment.location_note = location_note
        for category_key, minutes in category_times.items():
            assessment.set_time(category_key, minutes)
        storage.update_assessment(assessment)
        flash("Assessment updated.", "success")
        return redirect(url_for("main.detail", assessment_id=assessment_id))

    form_data = {"nickname": assessment.nickname, "location_note": assessment.location_note}
    form_data.update({key: assessment.get_time(key) for key in CATEGORIES})
    return render_template("edit_assessment.html", assessment=assessment,
                            categories=CATEGORIES, max_minutes=MAX_MINUTES, form=form_data)


@bp.route("/assessments/<int:assessment_id>/delete", methods=["POST"])
def delete_assessment(assessment_id):
    assessment = _assessment_or_none(assessment_id)
    if assessment is not None:
        storage.delete_assessment_by_id(assessment_id)
        flash(f'Assessment #{assessment_id} "{assessment.nickname}" deleted.', "success")

    if request.headers.get("HX-Request"):
        return "", 200, {"HX-Redirect": url_for("main.index")}
    return redirect(url_for("main.index"))


@bp.route("/compare")
def compare():
    calculator = create_default_calculator()
    assessments = storage.load_all_assessments()
    id_a = request.args.get("a", type=int)
    id_b = request.args.get("b", type=int)

    result = None
    if id_a and id_b:
        if id_a == id_b:
            flash("Please choose two different assessments to compare.", "error")
        else:
            assessment_a = storage.find_assessment_by_id(assessments, id_a)
            assessment_b = storage.find_assessment_by_id(assessments, id_b)
            if assessment_a is None or assessment_b is None:
                flash("One or both assessment IDs were not found.", "error")
            else:
                result = _build_comparison(calculator, assessment_a, assessment_b)

    return render_template("compare.html", assessments=assessments, id_a=id_a, id_b=id_b,
                            result=result, colors=RATING_COLORS)


def _build_comparison(calculator, assessment_a, assessment_b):
    """Assemble the per-category and total comparison data for two assessments."""
    score_a = calculator.calculate_total_score(assessment_a)
    score_b = calculator.calculate_total_score(assessment_b)

    rows = []
    for category_key, info in CATEGORIES.items():
        points_a = calculator.calculate_category_score(category_key, assessment_a.get_time(category_key))
        points_b = calculator.calculate_category_score(category_key, assessment_b.get_time(category_key))
        rows.append({
            "label": info["label"],
            "points_a": round_half_up(points_a),
            "points_b": round_half_up(points_b),
            "a_wins": points_a > points_b,
            "b_wins": points_b > points_a,
        })

    winner = None
    if score_a > score_b:
        winner = assessment_a
    elif score_b > score_a:
        winner = assessment_b

    return {
        "a": assessment_a, "b": assessment_b,
        "score_a": round_half_up(score_a), "score_b": round_half_up(score_b),
        "rating_a": calculator.classify_rating(score_a),
        "rating_b": calculator.classify_rating(score_b),
        "rows": rows,
        "winner": winner,
    }


@bp.route("/about")
def about():
    tier_rows = []
    previous_upper = 0
    for upper, percent in TIER_TABLE:
        if upper is None:
            label = f"> {previous_upper} min"
        elif previous_upper == 0:
            label = f"≤ {upper} min"
        else:
            label = f"{previous_upper + 1}–{upper} min"
        tier_rows.append({"label": label, "percent": percent * 100})
        if upper is not None:
            previous_upper = upper

    return render_template("about.html", categories=CATEGORIES, tiers=tier_rows,
                            rating_bands=RATING_BANDS, colors=RATING_COLORS)
