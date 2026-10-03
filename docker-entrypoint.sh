#!/bin/sh
set -e

if [ ! -f /app/data/brain_783.npz ]; then
    python /app/scripts/fetch_data.py
    moodfly-build
fi

exec moodfly
