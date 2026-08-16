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
    nearest_meters = _nearest_meters_per_category(lat, lon)
    return {
        category_key: (_meters_to_minutes(distance) if distance is not None else FALLBACK_MINUTES)
        for category_key, distance in nearest_meters.items()
    }


def _nearest_meters_per_category(lat, lon):
    nearest = _search_categories(lat, lon, CATEGORY_TAGS.keys(), NEARBY_RADIUS_METERS)

    # Every category coming back empty at a 1200m radius is a strong sign the
    # request itself failed (shared public Overpass instance timed out/errored)
    # rather than a genuinely amenity-free location -- worth one retry before
    # treating it as real. A retry after a partial result is not: those are
    # plausible genuine misses that the wider second pass already handles.
    if all(distance is None for distance in nearest.values()):
        nearest = _search_categories(lat, lon, CATEGORY_TAGS.keys(), NEARBY_RADIUS_METERS)

    missing = [key for key, distance in nearest.items() if distance is None]
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
            if nearest[category_key] is None or distance < nearest[category_key]:
                nearest[category_key] = distance

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


def _meters_to_minutes(distance_m):
    return round(distance_m * DETOUR_FACTOR / WALK_METERS_PER_MINUTE, 1)
