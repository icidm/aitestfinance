#!/bin/sh
set -e
# Wait for postgres if DATABASE_URL_SYNC points to postgres
for i in 1 2 3 4 5; do
  if python -c "import psycopg2,os; psycopg2.connect(os.getenv('DATABASE_URL_SYNC','sqlite:///./app.db'))" 2>/dev/null; then
    break
  fi
  # If sqlite, break immediately
  if echo "$DATABASE_URL_SYNC" | grep -q "sqlite"; then
    break
  fi
  sleep 2
done
alembic upgrade head || echo "alembic upgrade failed, continuing"
exec python -m uvicorn main:app --host 0.0.0.0 --port 8000
