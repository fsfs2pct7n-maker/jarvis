#!/bin/bash
PORT=$(grep '^PORT=' "$(dirname "$0")/.env" 2>/dev/null | cut -d= -f2)
PORT=${PORT:-8000}
lsof -ti:"$PORT" | xargs kill -9 2>/dev/null
sleep 1
cd "$(dirname "$0")"
PYTHONUNBUFFERED=1 venv/bin/python -u main.py
