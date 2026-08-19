"""Real geocoding and nearby-amenity walk-time estimation.

Turns a free-text address/place into estimated one-way walking minutes for
each of the app's six categories, using two free OpenStreetMap services:
Nominatim (geocoding) and Overpass (nearby-place search). No API key and no
extra pip dependency -- stdlib urllib is enough for two GET/POST+JSON calls.

This is a straight-line-distance approximation (Haversine, times a detour
factor for the fact streets aren't straight lines), not a routed walking
distance from a mapping API -- documented as a limitation on the About page.
"""

import json
import math
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "15-Minute-Neighborhood-Score-CourseProject/1.0"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
NOMINATIM_TIMEOUT_SECONDS = 8
OVERPASS_TIMEOUT_SECONDS = 12
OVERPASS_QUERY_BUDGET_SECONDS = 11  # internal [timeout:] must stay under the HTTP timeout above

# Two-tier search: a small, fast radius first; only the categories that come
# up empty get one second, wider query. Both calls are capped at
# OVERPASS_TIMEOUT_SECONDS, so a slow/overloaded public Overpass instance
# degrades to FALLBACK_MINUTES for whatever didn't resolve in time rather
# than hanging the request -- a bounded ~20s worst case, not an open-ended one.
NEARBY_RADIUS_METERS = 1200
WIDE_RADIUS_METERS = 3000

WALK_METERS_PER_MINUTE = 80  # matches world-stage.js's WALK_M_PER_MIN
DETOUR_FACTOR = 1.3  # straight-line distance underestimates real street routes
FALLBACK_MINUTES = 30.0  # used when nothing of that category is found nearby even at the wide radius

# OSM tag(s) that count as "nearest place" for each of our six categories.
CATEGORY_TAGS = {
    "grocery": [("shop", ["supermarket", "convenience", "greengrocer", "grocery"])],
    "healthcare": [("amenity", ["hospital", "clinic", "pharmacy", "doctors"])],
    "education": [("amenity", ["school", "kindergarten", "college", "university"])],
    "transit": [
        ("highway", ["bus_stop"]),
        ("railway", ["station", "tram_stop"]),
        ("public_transport", ["station", "stop_position", "platform"]),
    ],
    "parks": [("leisure", ["park", "garden"])],
    "retail": [("shop", ["mall", "department_store"]), ("amenity", ["bank", "post_office"])],
}


def geocode(query):
    """Look up a free-text place with Nominatim. Returns (lat, lon, display_name) or None."""
    params = urllib.parse.urlencode({"q": query, "format": "json", "limit": 1})
    request = urllib.request.Request(
        f"{NOMINATIM_URL}?{params}", headers={"User-Agent": USER_AGENT}
    )
    try:
        with urllib.request.urlopen(request, timeout=NOMINATIM_TIMEOUT_SECONDS) as response:
            results = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None

    if not results:
        return None
    result = results[0]
    return float(result["lat"]), float(result["lon"]), result["display_name"]


def estimate_category_times(lat, lon):
    """Return {category_key: minutes} estimated from real nearby OSM places."""
    nearest = _nearest_per_category(lat, lon)
    return {
        category_key: (_meters_to_minutes(place["meters"]) if place else FALLBACK_MINUTES)
        for category_key, place in nearest.items()
    }


def nearest_places(lat, lon):
    """Return {category_key: {meters, bearing, name} or None} for the real nearest place.

    Same Overpass search estimate_category_times() uses, but keeps the bearing
    and name so the 3D view can put each marker in its true compass direction
    instead of an arbitrary evenly-spaced angle.
    """
    return _nearest_per_category(lat, lon)


def times_from_places(places):
    """Convert the result of nearest_places() into {category_key: minutes}.

    Lets a caller run the (slow) Overpass search once and get both the walking
    times and the map geometry out of it, instead of searching twice.
    """
    return {
        category_key: (_meters_to_minutes(place["meters"]) if place else FALLBACK_MINUTES)
        for category_key, place in places.items()
    }


def _nearest_per_category(lat, lon):
    nearest = _search_categories(lat, lon, CATEGORY_TAGS.keys(), NEARBY_RADIUS_METERS)

    # Every category coming back empty at a 1200m radius is a strong sign the
    # request itself failed (shared public Overpass instance timed out/errored)
    # rather than a genuinely amenity-free location -- worth one retry before
    # treating it as real. A retry after a partial result is not: those are
    # plausible genuine misses that the wider second pass already handles.
    if all(place is None for place in nearest.values()):
        nearest = _search_categories(lat, lon, CATEGORY_TAGS.keys(), NEARBY_RADIUS_METERS)

    missing = [key for key, place in nearest.items() if place is None]
    if missing:
        wide_results = _search_categories(lat, lon, missing, WIDE_RADIUS_METERS)
        nearest.update(wide_results)

    return nearest


def _search_categories(lat, lon, category_keys, radius_m):
    query = _build_overpass_query(lat, lon, radius_m, category_keys)
    payload = _run_overpass_query(query)

    nearest = {category_key: None for category_key in category_keys}
    for element in payload.get("elements", []):
        tags = element.get("tags", {})
        point = element.get("center") or element
        element_lat, element_lon = point.get("lat"), point.get("lon")
        if element_lat is None or element_lon is None:
            continue

        distance = _haversine_meters(lat, lon, element_lat, element_lon)
        for category_key in category_keys:
            if not _matches_category(tags, category_key):
                continue
            current = nearest[category_key]
            if current is None or distance < current["meters"]:
                nearest[category_key] = {
                    "meters": distance,
                    "bearing": _bearing_degrees(lat, lon, element_lat, element_lon),
                    "name": tags.get("name") or "",
                }

    return nearest


def _matches_category(tags, category_key):
    return any(tags.get(osm_key) in values for osm_key, values in CATEGORY_TAGS[category_key])


def _build_overpass_query(lat, lon, radius_m, category_keys):
    clauses = []
    for category_key in category_keys:
        for osm_key, values in CATEGORY_TAGS[category_key]:
            pattern = "|".join(values)
            clauses.append(f'node["{osm_key}"~"^({pattern})$"](around:{radius_m},{lat},{lon});')
            clauses.append(f'way["{osm_key}"~"^({pattern})$"](around:{radius_m},{lat},{lon});')
    body = "\n  ".join(clauses)
    return f"[out:json][timeout:{OVERPASS_QUERY_BUDGET_SECONDS}];\n(\n  {body}\n);\nout center;"


def _run_overpass_query(query):
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    request = urllib.request.Request(OVERPASS_URL, data=data, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=OVERPASS_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return {"elements": []}


def _haversine_meters(lat1, lon1, lat2, lon2):
    earth_radius_m = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * earth_radius_m * math.asin(math.sqrt(a))


def _bearing_degrees(lat1, lon1, lat2, lon2):
    """Initial compass bearing from point 1 to point 2: 0 = north, 90 = east."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)
    y = math.sin(delta_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _meters_to_minutes(distance_m):
    return round(distance_m * DETOUR_FACTOR / WALK_METERS_PER_MINUTE, 1)


# --- Real building footprints (for the 3D walkthrough) --------------------
#
# OpenStreetMap is the free, key-less source of real 3D building data: any
# way tagged building=* is a real footprint, and where mappers have added
# height or building:levels we get a real height too. That is the same data
# behind OSM Buildings and F4Map. Coverage is uneven -- plenty of towns have
# footprints but no height tags, and some have no buildings mapped at all --
# so heights fall back to a per-type estimate, and a location with no
# buildings at all falls back to the procedural city in world-stage.js.

BUILDINGS_RADIUS_METERS = 800  # ~10 minutes' walk out, the zone the score is about
BUILDINGS_MAX = 1400
METERS_PER_LEVEL = 3.2
DEFAULT_LEVELS = {"house": 1, "detached": 2, "garage": 1, "hut": 1, "shed": 1, "bungalow": 1}
DEFAULT_BUILDING_METERS = 9.0


def fetch_buildings(lat, lon, radius_m=BUILDINGS_RADIUS_METERS):
    """Return real OSM building footprints near a point, as local metre offsets.

    Each item is {"points": [[east_m, north_m], ...], "height": metres}, with
    east/north measured from (lat, lon). Returns [] when Overpass is
    unavailable or the area has no mapped buildings -- callers treat an empty
    list as "fall back to the procedural city".
    """
    query = (
        f"[out:json][timeout:{OVERPASS_QUERY_BUDGET_SECONDS}];\n"
        f"(way[\"building\"](around:{radius_m},{lat},{lon}););\n"
        "out geom;"
    )
    payload = _run_overpass_query(query)

    metres_per_deg_lat = 111320.0
    metres_per_deg_lon = 111320.0 * math.cos(math.radians(lat))

    buildings = []
    for element in payload.get("elements", []):
        geometry = element.get("geometry") or []
        if len(geometry) < 4:
            continue

        points = [
            [
                round((node["lon"] - lon) * metres_per_deg_lon, 2),
                round((node["lat"] - lat) * metres_per_deg_lat, 2),
            ]
            for node in geometry
            if node.get("lat") is not None and node.get("lon") is not None
        ]
        if len(points) < 4:
            continue
        if points[0] == points[-1]:
            points.pop()  # Three.js Shape closes the ring itself
        if len(points) < 3:
            continue

        buildings.append({"points": points, "height": _building_height(element.get("tags", {}))})
        if len(buildings) >= BUILDINGS_MAX:
            break

    return buildings


def _building_height(tags):
    """Best available height in metres: real height tag, else levels, else a default."""
    height = _first_float(tags.get("height"))
    if height is not None and 0 < height < 700:
        return round(height, 1)

    levels = _first_float(tags.get("building:levels"))
    if levels is not None and 0 < levels < 200:
        return round(levels * METERS_PER_LEVEL, 1)

    return DEFAULT_LEVELS.get(tags.get("building"), 0) * METERS_PER_LEVEL or DEFAULT_BUILDING_METERS


def _first_float(raw_value):
    """Parse a leading number out of an OSM tag ('12', '12.5 m', '4;6' -> 12/12.5/4)."""
    if not raw_value:
        return None
    number = ""
    for character in str(raw_value).strip():
        if character.isdigit() or (character == "." and "." not in number):
            number += character
        else:
            break
    try:
        return float(number)
    except ValueError:
        return None
