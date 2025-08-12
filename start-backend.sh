#!/bin/bash
set -e

echo "Building and starting Klaris Backend (FastAPI + Postgres)..."
docker compose build backend db
docker compose up -d backend db

echo "Waiting for DB to become available..."
sleep 5
echo "Applying alembic migrations..."
docker compose exec backend alembic upgrade head
echo "Backend running at: http://localhost:8000/docs"
