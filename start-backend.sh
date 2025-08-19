#!/bin/bash
set -euo pipefail

echo "Building images (backend, db)..."
docker compose build db backend

# Start only the DB first so we can run migrations
echo "Starting Postgres..."
docker compose up -d db

# Wait for DB to be ready using pg_isready inside the db container
echo "Waiting for DB to become available..."
for i in {1..60}; do
  if docker compose exec -T db pg_isready -U postgres -d postgres >/dev/null 2>&1; then
    echo "DB is ready."
    break
  fi
  if [ "$i" -eq 60 ]; then
    echo "ERROR: DB did not become ready in time." >&2
    docker compose logs db | tail -n 200 || true
    exit 1
  fi
  sleep 2
done

# Run Alembic migrations using a one-off backend container (no need for backend to be running yet)
echo "Applying alembic migrations..."
docker compose run --rm backend alembic upgrade head

# Now start the backend service
echo "Starting backend..."
docker compose up -d backend

echo "Backend running at: http://localhost:8000/docs"
