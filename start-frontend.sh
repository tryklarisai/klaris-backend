#!/bin/bash
set -e

echo "Building and starting Klaris Frontend (React + Nginx SPA)..."
docker compose build frontend
docker compose up -d frontend

echo "Frontend running at: http://localhost:3000"
