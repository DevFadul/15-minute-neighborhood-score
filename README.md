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

## Requirements

Python 3.10+ and the standard library only. No `pip install` required.

## Running the app

```bash
python3 main.py
```

Run it from the project root so the `neighborhood_score` package is importable.

## Project structure

```
main.py                       # entry point
neighborhood_score/
    constants.py                # category weights, tier table, rating bands
    models.py                   # Assessment class (data entity)
    scoring.py                  # ScoreCalculator class (scoring algorithm)
    validation.py                # input-validation retry-loop helpers
    storage.py                   # JSON persistence + CRUD
    recommendations.py           # weak-category tips
    ui.py                        # console formatting/printing
    app.py                        # menu loop + handlers
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

`[https://github.com/<your-username>/15-minute-neighborhood-score]`
