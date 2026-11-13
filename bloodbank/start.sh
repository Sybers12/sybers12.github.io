#!/usr/bin/env bash
# NBTS Blood Bank System - double-click launcher
# Starts the server and opens the browser. Close this window to stop.
set -e
cd "$(dirname "$0")"

if [ ! -d "$HOME/myenv" ]; then
  echo "Creating Python environment (first run only)..."
  python3 -m venv "$HOME/myenv"
fi
source "$HOME/myenv/bin/activate"

if ! python3 -c "import fastapi, sqlalchemy, uvicorn, reportlab" 2>/dev/null; then
  echo "Installing requirements (first run only)..."
  pip install -q -r requirements.txt
fi

if [ ! -f data/bloodbank.db ]; then
  echo "Seeding demo data (first run only)..."
  python3 seed.py
fi

URL="http://127.0.0.1:8500"
( sleep 4; xdg-open "$URL" >/dev/null 2>&1 ) &

echo ""
echo "=============================================="
echo "  Blood Bank System starting at $URL"
echo "  Login demo accounts, password: demo123"
echo "  (admin, manager, quality, recruiter, ...)"
echo "  Keep this window OPEN - closing it stops"
echo "  the system. Ctrl+C also stops it."
echo "=============================================="
echo ""
python3 run.py
