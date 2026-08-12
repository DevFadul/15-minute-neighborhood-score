"""Entry point for the web UI.

Run from the project root: python3 run_web.py
Shares data/assessments.json with the console app (main.py) via the same
neighborhood_score.storage module -- assessments created in either
interface are visible in both.
"""

from web import create_app

app = create_app()

if __name__ == "__main__":
    # Port 5000 is claimed by macOS AirPlay Receiver on many systems -- 5001 avoids the clash.
    app.run(debug=True, port=5001)
