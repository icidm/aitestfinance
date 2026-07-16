#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"

echo "================================"
echo " Inditex Incident Dashboard"
echo "================================"
echo ""

cd "$DIR/backend"

if [ ! -f "data.json" ]; then
  echo "[1/2] Generating seed data..."
  python3 seed.py
else
  echo "[1/2] Seed data already exists (delete data.json to regenerate)"
fi

echo "[2/2] Starting API server..."
echo ""
echo "  Dashboard: http://localhost:8000"
echo "  API:      http://localhost:8000/api/stats"
echo "  Docs:     http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop"
echo ""

python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info
