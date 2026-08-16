"""View functions for the web UI.

Every calculation and persistence call delegates to neighborhood_score.* --
the same package the console app (main.py) uses -- so both interfaces stay
in sync against the same data/assessments.json and the same scoring rules.
"""

import math

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from neighborhood_score import recommendations, storage
from neighborhood_score.constants import CATEGORIES, MAX_MINUTES, RATING_BANDS, TIER_TABLE
from neighborhood_score.models import Assessment
from neighborhood_score.scoring import create_default_calculator
from neighborhood_score.ui import round_half_up

from web import geocoding
from web.forms import parse_category_times, validate_nickname
from web.icons import CATEGORY_COLORS, CATEGORY_LETTERS, CATEGORY_SHORT

bp = Blueprint("main", __name__)

CATEGORY_KEYS = list(CATEGORIES.keys())

RATING_COLOR_VAR = {
    "Excellent": "var(--excellent)",
    "Good": "var(--good)",
    "Fair": "var(--fair)",
    "Poor": "var(--poor)",
}

# Hexagonal radar geometry: center (140,140), full-tier radius 110, one axis
# per category in CATEGORIES order (matches the design's fixed hexagon).
RADAR_AXES = [(0, -110), (95, -55), (95, 55), (0, 110), (-95, 55), (-95, -55)]
RADAR_AXES_DEGREES = [-90, -30, 30, 90, 150, 210]
RADAR_AXIS_LABEL_POS = [
    (140, 2, "middle"), (258, 73, "start"), (258, 211, "start"),
    (140, 286, "middle"), (22, 211, "end"), (22, 73, "end"),
]

FACILITY_METERS_PER_UNIT = 8  # matches world-stage.js's M_PER_UNIT


def _ring_style(score, rating):
    """Inline style for a conic-gradient score-ring background layer."""
    return (
        f"position:absolute;inset:0;border-radius:50%;"
        f"background:conic-gradient({RATING_COLOR_VAR[rating]} {round(score)}%, var(--line) 0deg);"
    )


def _radar_points(category_times, calculator):
    points = []
    for i, category_key in enumerate(CATEGORY_KEYS):
        tier = calculator.get_tier_percentage(category_times.get(category_key, 0))
        dx, dy = RADAR_AXES[i]
        points.append(f"{140 + dx * tier:.1f},{140 + dy * tier:.1f}")
    return " ".join(points)


def _radar_vertices(category_times, calculator):
    vertices = []
    for i, category_key in enumerate(CATEGORY_KEYS):
        tier = calculator.get_tier_percentage(category_times.get(category_key, 0))
        dx, dy = RADAR_AXES[i]
        vertices.append({
            "x": round(140 + dx * tier, 1),
            "y": round(140 + dy * tier, 1),
            "color": CATEGORY_COLORS[category_key],
        })
    return vertices


def _axis_labels():
    return [
        {"x": x, "y": y, "anchor": anchor, "letter": CATEGORY_LETTERS[key], "color": CATEGORY_COLORS[key]}
        for key, (x, y, anchor) in zip(CATEGORY_KEYS, RADAR_AXIS_LABEL_POS)
    ]


# --- Seeded PRNG (xorshift32), ported bit-for-bit from the design's own
# generator so the illustrative map-sketch panels are stable per assessment
# id (same "random" layout every time you view it) instead of reshuffling on
# every page load. Verified against the JS source with matching seeds.

def _seed_hash(text):
    h = 2166136261
    for ch in str(text):
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return h & 0xFFFFFFFF


def _rng_from_seed(seed):
    state = [(seed & 0xFFFFFFFF) or 1]

    def next_value():
        v = state[0]
        v = (v ^ ((v << 13) & 0xFFFFFFFF)) & 0xFFFFFFFF
        v = (v ^ (v >> 17)) & 0xFFFFFFFF
        v = (v ^ ((v << 5) & 0xFFFFFFFF)) & 0xFFFFFFFF
        state[0] = v
        return v / 4294967296

    return next_value


def _build_sketch_blocks(seed_id, count=16):
    """Deterministic illustrative "buildings" for a map-sketch panel."""
    rand = _rng_from_seed(_seed_hash(seed_id))
    blocks = []
    for _ in range(count):
        x = y = 0.0
        tries = 0
        while True:
            x = 8 + rand() * 176
            y = 8 + rand() * 176
            tries += 1
            if math.hypot(x - 100, y - 100) >= 26 or tries >= 8:
                break
        w, h = 8 + rand() * 14, 8 + rand() * 14
        bx, by = round(x - w / 2), round(y - h / 2)
        bw, bh = round(w), round(h)
        blocks.append({
            "x": bx, "y": by, "w": bw, "h": bh,
            "rx1": bx + 2, "rx2": bx + bw - 2, "ry": by + round(bh / 2),
        })
    return blocks


def _build_sketch_pins(category_times, calculator):
    """Illustrative pin positions radiating from the map-sketch center -- closer means a better tier."""
    pins = []
    for i, category_key in enumerate(CATEGORY_KEYS):
        tier = calculator.get_tier_percentage(category_times.get(category_key, 0))
        angle = math.radians(RADAR_AXES_DEGREES[i])
        radius = 16 + (1 - tier) * 54
        pins.append({
            "id": category_key,
            "x": round(100 + math.cos(angle) * radius, 1),
            "y": round(100 + math.sin(angle) * radius, 1),
            "color": CATEGORY_COLORS[category_key],
            "letter": CATEGORY_LETTERS[category_key],
        })
    return pins


def _build_park_cluster(pins):
    park = next((p for p in pins if p["id"] == "parks"), None)
    if not park:
        return []
    return [
        {"x": park["x"] - 6, "y": park["y"] - 5, "r": 3.2},
        {"x": park["x"] + 5, "y": park["y"] - 3, "r": 2.6},
        {"x": park["x"] - 1, "y": park["y"] + 6, "r": 3},
    ]


def _build_transit_ticks(pins):
    transit = next((p for p in pins if p["id"] == "transit"), None)
    if not transit:
        return []
    ticks = []
    for t in (0.3, 0.55, 0.8):
        mx, my = 100 + (transit["x"] - 100) * t, 100 + (transit["y"] - 100) * t
        dx, dy = transit["x"] - 100, transit["y"] - 100
        length = math.hypot(dx, dy) or 1
        px, py = -dy / length, dx / length
        ticks.append({
            "x1": round(mx - px * 4, 1), "y1": round(my - py * 4, 1),
            "x2": round(mx + px * 4, 1), "y2": round(my + py * 4, 1),
        })
    return ticks


def _breakdown_rows(assessment, calculator):
    category_scores = calculator.calculate_all_category_scores(assessment)
    rows = []
    for category_key, info in CATEGORIES.items():
        minutes = assessment.get_time(category_key)
        points = round_half_up(category_scores[category_key])
        rows.append({
            "key": category_key,
            "label": info["label"],
            "letter": CATEGORY_LETTERS[category_key],
            "color": CATEGORY_COLORS[category_key],
            "minutes": minutes,
            "points": points,
            "weight": info["weight"],
            "pct": round(points / info["weight"] * 100) if info["weight"] else 0,
        })
    return rows


def _build_recommendation_cards(assessment, calculator):
    """Same selection logic as neighborhood_score.recommendations.generate_recommendations,
    reusing its category-tip lookup, but shaped for the letter-badge UI instead of joined text."""
    max_possible = sum(info["weight"] for info in CATEGORIES.values())
    total_score = calculator.calculate_total_score(assessment)

    if total_score >= max_possible - 0.01:
        return [{
            "text": "This neighborhood scores at or near the maximum -- no major accessibility "
                    "gaps were found. Great example of a 15-minute neighborhood!",
            "has_letter": False,
        }]

    ranked = calculator.rank_categories_ascending(assessment)
    cards = []
    for category_key, points_earned in ranked[:2]:
        weight = CATEGORIES[category_key]["weight"]
        if points_earned >= weight * 0.75:
            continue
        cards.append({
            "text": f"{CATEGORIES[category_key]['label']}: {recommendations.get_tip_for_category(category_key)}",
            "has_letter": True,
            "letter": CATEGORY_LETTERS[category_key],
            "color": CATEGORY_COLORS[category_key],
        })

    if not cards:
        cards.append({
            "text": "This neighborhood scores reasonably well across all categories -- "
                    "no urgent gaps stand out.",
            "has_letter": False,
        })
    return cards


def _assessment_or_none(assessment_id):
    assessment = storage.find_assessment_by_id(storage.load_all_assessments(), assessment_id)
    if assessment is None:
        flash(f"No assessment with ID {assessment_id}.", "error")
    return assessment


@bp.route("/")
def landing():
    return render_template("landing.html")


@bp.route("/dashboard")
def dashboard():
    calculator = create_default_calculator()
    cards = []
    for assessment in storage.load_all_assessments():
        total_score = calculator.calculate_total_score(assessment)
        rating = calculator.classify_rating(total_score)
        pins = _build_sketch_pins(assessment.category_times, calculator)
        cards.append({
            "assessment": assessment,
            "score": round_half_up(total_score),
            "rating": rating,
            "rating_var": RATING_COLOR_VAR[rating],
            "ring_style": _ring_style(total_score, rating),
            "sketch_blocks": _build_sketch_blocks(assessment.assessment_id),
            "sketch_pins": pins,
            "breakdown": _breakdown_rows(assessment, calculator),
        })
    cards.sort(key=lambda row: row["score"], reverse=True)
    return render_template("dashboard.html", cards=cards)


@bp.route("/estimate", methods=["POST"])
def estimate():
    """Real geocode + nearby-amenity walk-time estimate -- no fabricated data.

    Saves a genuine Assessment(auto=True) from real OSM places, or returns an
    error for the client's inline message; never invents a score.
    """
    query = (request.form.get("query") or "").strip()
    if not query:
        return jsonify({"error": "Enter an address or place name first."})

    location = geocoding.geocode(query)
    if location is None:
        return jsonify({"error": "Couldn't find that location. Try a more specific address."})

    lat, lon, display_name = location
    category_times = geocoding.estimate_category_times(lat, lon)

    assessments = storage.load_all_assessments()
    new_id = storage.generate_next_id(assessments)
    assessment = Assessment(new_id, query, display_name, category_times, auto=True)
    storage.add_assessment(assessment)

    return jsonify({"redirect": url_for("main.walk", assessment_id=new_id)})


@bp.route("/assessments/<int:assessment_id>/walk")
def walk(assessment_id):
    assessment = _assessment_or_none(assessment_id)
    if assessment is None:
        return redirect(url_for("main.dashboard"))

    calculator = create_default_calculator()
    total_score = calculator.calculate_total_score(assessment)
    rating = calculator.classify_rating(total_score)

    facilities = []
    for category_key, info in CATEGORIES.items():
        minutes = max(1, assessment.get_time(category_key))
        meters = round(max(12, minutes * 10) * FACILITY_METERS_PER_UNIT / 10) * 10
        facilities.append({
            "id": category_key,
            "short": CATEGORY_SHORT[category_key],
            "letter": CATEGORY_LETTERS[category_key],
            "color": CATEGORY_COLORS[category_key],
            "minutes": minutes,
            "meters": meters,
        })

    return render_template(
        "world.html", assessment=assessment,
        score=round_half_up(total_score), rating=rating, rating_var=RATING_COLOR_VAR[rating],
        ring_style=_ring_style(total_score, rating), facilities=facilities,
    )


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
    """HTMX endpoint: compute a live score + radar from in-progress form data without saving."""
    category_times, errors = parse_category_times(request.form)
    if errors:
        return render_template("_score_preview.html", ready=False)

    calculator = create_default_calculator()
    total_score = calculator.calculate_total_score(Assessment(0, "preview", "", category_times))
    rating = calculator.classify_rating(total_score)
    return render_template(
        "_score_preview.html", ready=True,
        score=round_half_up(total_score), rating=rating, rating_var=RATING_COLOR_VAR[rating],
        ring_style=_ring_style(total_score, rating),
        radar_points=_radar_points(category_times, calculator), axis_labels=_axis_labels(),
    )


@bp.route("/assessments/<int:assessment_id>")
def detail(assessment_id):
    assessment = _assessment_or_none(assessment_id)
    if assessment is None:
        return redirect(url_for("main.dashboard"))

    calculator = create_default_calculator()
    total_score = calculator.calculate_total_score(assessment)
    rating = calculator.classify_rating(total_score)
    pins = _build_sketch_pins(assessment.category_times, calculator)

    return render_template(
        "detail.html", assessment=assessment,
        score=round_half_up(total_score), rating=rating, rating_var=RATING_COLOR_VAR[rating],
        ring_style=_ring_style(total_score, rating),
        breakdown=_breakdown_rows(assessment, calculator),
        radar_points=_radar_points(assessment.category_times, calculator),
        radar_vertices=_radar_vertices(assessment.category_times, calculator),
        axis_labels=_axis_labels(),
        sketch_blocks=_build_sketch_blocks(assessment.assessment_id, count=16),
        sketch_pins=pins,
        park_cluster=_build_park_cluster(pins),
        transit_ticks=_build_transit_ticks(pins),
        recommendations=_build_recommendation_cards(assessment, calculator),
        others=[a for a in storage.load_all_assessments() if a.assessment_id != assessment_id],
    )


@bp.route("/assessments/<int:assessment_id>/edit", methods=["GET", "POST"])
def edit_assessment(assessment_id):
    assessment = _assessment_or_none(assessment_id)
    if assessment is None:
        return redirect(url_for("main.dashboard"))

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
        return "", 200, {"HX-Redirect": url_for("main.dashboard")}
    return redirect(url_for("main.dashboard"))


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
                            result=result, axis_labels=_axis_labels())


def _build_comparison(calculator, assessment_a, assessment_b):
    """Per-category diff rows, dual radar polygons, and a verdict that cites which
    categories actually drove the winning margin (not just who scored higher)."""
    score_a = round_half_up(calculator.calculate_total_score(assessment_a))
    score_b = round_half_up(calculator.calculate_total_score(assessment_b))

    rows = []
    for category_key, info in CATEGORIES.items():
        points_a = calculator.calculate_category_score(category_key, assessment_a.get_time(category_key))
        points_b = calculator.calculate_category_score(category_key, assessment_b.get_time(category_key))
        winner = "a" if points_a > points_b else ("b" if points_b > points_a else "tie")
        rows.append({
            "key": category_key, "label": info["label"],
            "letter": CATEGORY_LETTERS[category_key], "color": CATEGORY_COLORS[category_key],
            "a_minutes": assessment_a.get_time(category_key), "b_minutes": assessment_b.get_time(category_key),
            "a_pct": round(points_a / info["weight"] * 100), "b_pct": round(points_b / info["weight"] * 100),
            "winner": winner, "gap": abs(points_a - points_b),
        })

    score_diff = score_a - score_b
    if score_diff == 0:
        verdict = (f"{assessment_a.nickname} and {assessment_b.nickname} score evenly overall at "
                   f"{score_a}/100 -- the difference shows up category by category.")
    else:
        winner_key = "a" if score_diff > 0 else "b"
        winner_assessment = assessment_a if score_diff > 0 else assessment_b
        drivers = [r["label"] for r in sorted(
            (r for r in rows if r["winner"] == winner_key), key=lambda r: r["gap"], reverse=True
        )[:2]]
        margin = round(abs(score_diff), 1)
        if drivers:
            verdict = (f"{winner_assessment.nickname} is the more walkable 15-minute neighborhood, "
                       f"scoring {margin} points higher -- leading mainly on {' and '.join(drivers)}.")
        else:
            verdict = (f"{winner_assessment.nickname} is the more walkable 15-minute neighborhood, "
                       f"scoring {margin} points higher.")

    rating_a = calculator.classify_rating(calculator.calculate_total_score(assessment_a))
    rating_b = calculator.classify_rating(calculator.calculate_total_score(assessment_b))

    return {
        "a": assessment_a, "b": assessment_b, "score_a": score_a, "score_b": score_b,
        "rating_a": rating_a, "rating_b": rating_b,
        "rating_a_var": RATING_COLOR_VAR[rating_a], "rating_b_var": RATING_COLOR_VAR[rating_b],
        "rows": rows, "verdict": verdict,
        "radar_a": _radar_points(assessment_a.category_times, calculator),
        "radar_b": _radar_points(assessment_b.category_times, calculator),
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

    return render_template(
        "about.html", categories=CATEGORIES, tiers=tier_rows, rating_bands=RATING_BANDS,
        rating_color_var=RATING_COLOR_VAR,
    )
