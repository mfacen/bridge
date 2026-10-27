#!/bin/bash
# critter-bridge launcher: creates the venv on first run, then starts the app.
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
    echo "first run: creating virtualenv..."
    python3 -m venv .venv
    .venv/bin/pip install -q -r requirements.txt
fi

exec .venv/bin/python run.py "$@"
