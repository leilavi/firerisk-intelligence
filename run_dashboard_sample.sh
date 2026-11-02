#!/usr/bin/env sh
# SAMPLE MODE on macOS / Linux: the dashboard with a FICTIONAL building ("Acme Riverside Plaza").
# Never reads data/private/ (real data). Meta Muse Spark runs only with your own key: MODEL_API_KEY=... in .env
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install -q --upgrade pip
  .venv/bin/python -m pip install -q -r requirements.txt
fi
echo "Starting FireRisk Intelligence in SAMPLE MODE (fictional building)... http://127.0.0.1:8765"
exec .venv/bin/python -m firerisk.sample
