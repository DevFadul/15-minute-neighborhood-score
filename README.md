# 15-Minute Neighborhood Score

A console-based Python application for **SDG 11: Sustainable Cities and Communities**. It scores how
"walkable" a neighborhood is against the [15-minute city](https://en.wikipedia.org/wiki/15-minute_city)
standard — can a resident reach daily essentials within a 15-minute walk? — and helps users make more
sustainable, informed housing decisions by comparing neighborhoods side by side.

Built for **BIT2083 Fundamental of Computational Thinking: Python**, City University Malaysia.

## Features

- Record a named "neighborhood assessment": one-way walking time to the nearest Grocery, Healthcare,
  Education, Transit, Parks, and Retail location.
- Computes a weighted 0–100 walkability score and rating (Excellent / Good / Fair / Poor).
- Persists assessments to `data/assessments.json` across sessions.
- Generates targeted recommendations for the weakest-scoring categories.
- Compares two saved assessments side by side.
- Edit or delete existing assessments.
- Validated, menu-driven console interface — retries on invalid input instead of crashing.
- Optional web UI (Flask, sharing the same data and scoring logic as the console app):
  - A 3D rotating-globe landing page where typing a real address geocodes it (OpenStreetMap
    Nominatim + Overpass, no API key) and estimates real walk times from real nearby places —
    no fabricated data.
  - A first-person 3D "walk your neighborhood" view with live per-category distance/time as you move.
  - A card dashboard, live score preview while typing, hexagonal radar-chart score breakdowns,
    illustrative map-sketch panels, and a side-by-side compare view with a verdict that names which
    categories actually drove the result.

## Requirements

The console app needs only Python 3.10+ and the standard library — no `pip install` required.
The optional web UI additionally needs Flask (see below).

## Running the console app

```bash
python3 main.py
```

Run it from the project root so the `neighborhood_score` package is importable.

## Running the web UI

The web UI is a thin Flask layer over the same `neighborhood_score` package and the same
`data/assessments.json` — assessments created in one interface show up in the other.

```bash
python3 -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
python3 run_web.py
```

Then open http://127.0.0.1:5001 in a browser (5001, not 5000 — macOS's AirPlay Receiver claims
port 5000 on many systems). Fonts, HTMX, and the 3D globe/walkthrough (Three.js) are loaded from
CDNs, so an internet connection is needed at runtime — as is the landing page's address search,
which calls the free OpenStreetMap Nominatim/Overpass APIs.

## Deploying

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/DevFadul/15-minute-neighborhood-score)

The repo includes a `render.yaml` blueprint, so the button above configures everything
automatically on [Render](https://render.com)'s free tier: install `requirements.txt`, then run
`gunicorn run_web:app`. Free-tier notes: the service spins down after 15 minutes idle (the first
request after that takes ~30-50s to wake back up), and `data/assessments.json` resets on every
redeploy/restart since the free tier's filesystem isn't persistent — fine for demoing, not for
long-term storage.

To deploy anywhere else that runs Python: install `requirements.txt` and run
`gunicorn run_web:app --bind 0.0.0.0:$PORT`. The console app (`main.py`) doesn't need any of this —
it only reads/writes a local JSON file.

## Project structure

```
main.py                       # console entry point
run_web.py                    # web UI entry point
neighborhood_score/
    constants.py                # category weights, tier table, rating bands
    models.py                   # Assessment class (data entity)
    scoring.py                  # ScoreCalculator class (scoring algorithm)
    validation.py                # input-validation retry-loop helpers
    storage.py                   # JSON persistence + CRUD
    recommendations.py           # weak-category tips
    ui.py                        # console formatting/printing
    app.py                        # menu loop + handlers
web/
    __init__.py                 # Flask app factory
    routes.py                    # view functions -- delegate to neighborhood_score.*
    forms.py                      # server-side form validation
    geocoding.py                   # Nominatim + Overpass: real address -> real walk-time estimate
    icons.py                        # category icons/colors/letters shared across templates
    templates/                       # landing (3D globe), dashboard, world (3D walkthrough),
                                       # forms, detail, compare, about
    static/
        style.css                     # design tokens + shared component styles
        globe-stage.js                 # rotating-globe landing hero (Three.js)
        world-stage.js                  # first-person neighborhood walkthrough (Three.js)
data/
    assessments.json              # created at first run (gitignored)
    sample_assessments.json       # optional demo data -- copy to assessments.json to try the app pre-populated
docs/
    flowchart.png                 # program flowchart
    uml_class_diagram.png         # UML class diagram
    report.pdf                    # full project report
slides/
    presentation.pdf               # presentation slides
tests/
    manual_test_transcript.txt     # captured output from scripted test runs
```

## Trying it with sample data

To explore the app without starting from an empty history:

```bash
cp data/sample_assessments.json data/assessments.json
python3 main.py
```

## Documentation

- [Project report](docs/report.pdf) — SDG background, problem statement, objectives, design, implementation, testing, discussion, conclusion.
- [Presentation slides](slides/presentation.pdf)
- [Program flowchart](docs/flowchart.png)
- [UML class diagram](docs/uml_class_diagram.png)
- [Sample test transcript](tests/manual_test_transcript.txt)

## GitHub Repository

https://github.com/DevFadul/15-minute-neighborhood-score
