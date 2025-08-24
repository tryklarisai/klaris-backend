# KlarisAI Pilot - Multi-Tenant Backend & Frontend

## Overview

This project is a production-grade, fully dockerized proof-of-concept for a multi-tenant AI platform with FastAPI (Python), React (TypeScript), and Postgres (with pgvector).

### Stack
- **Backend:** Python 3.11, FastAPI 0.111.0, SQLAlchemy 2.0+, Alembic, Pydantic 2
- **Frontend:** React 18 + TypeScript
- **Database:** Postgres 15 + pgvector (ankane/pgvector)

All service configuration and secrets are environment-variable driven.

---
## Features Developed (Pilot, Phase 0.2)
- Production-grade `/api/v1/tenants` API for onboarding and admin management.
- Strong validation, modular code, clear error handling.
- All hardcoded values use constants, easy to change.
- Docker Compose orchestration for backend, frontend, and database.

---
## Local Development & Running

### Prerequisites
- [Docker](https://www.docker.com/) (v20+ recommended)
- [Docker Compose](https://docs.docker.com/compose/) (v2+ syntax; install with Docker Desktop)

### 1. Start All Services
```
docker compose up --build
```
- **Backend:** http://localhost:8000
- **Frontend:** http://localhost:3000
- **Postgres:** localhost:5432 (default user/pass: postgres/postgres)

### 2. Apply Database Migrations
In a new terminal, run:
```
docker compose exec backend alembic upgrade head
```
This creates/updates the database schema for tenants.

---
## API Usage & Examples

### Swagger & OpenAPI UI
- Visit http://localhost:8000/docs for interactive API docs and to test endpoints.

### Key Endpoints

#### Create Tenant
```
POST /api/v1/tenants
Content-Type: application/json
{
  "name": "My Tenant",
  "plan": "pilot",
  "credit_balance": 1000,
  "settings": {"data_retention_days": 365}
}
```
- **Returns:** tenant object with tenant_id

#### Get Tenant
```
GET /api/v1/tenants/{tenant_id}
```

#### List Tenants
```
GET /api/v1/tenants
```

### Business Context Layer (BCL)

- Upload document (CSV/XLSX/TXT)
```
POST /api/v1/bcl/documents/upload
Headers: Authorization: Bearer <JWT> (or X-API-Key + X-Tenant-ID in dev)
Body: multipart/form-data { file }
```

- Import business glossary (CSV/XLSX)
```
POST /api/v1/bcl/glossary/import
Headers: Authorization: Bearer <JWT> (or X-API-Key + X-Tenant-ID in dev)
Body: multipart/form-data { file }
```

- Ground a query into relevant terms and evidence
```
POST /api/v1/bcl/ground
Headers: Authorization: Bearer <JWT>
Body: { "query": "total revenue last quarter", "top_k_terms": 5, "top_k_evidence": 5 }
```

- CRUD Mappings
```
GET /api/v1/bcl/terms/{term_id}/mappings
POST /api/v1/bcl/terms/{term_id}/mappings
PUT /api/v1/bcl/mappings/{mapping_id}
DELETE /api/v1/bcl/mappings/{mapping_id}
```

### Frontend

- New page: `/bcl` with tabs for Upload, Glossary, and Ground
  - Uses the above APIs with JWT from login

---
## Environment Variables
- `DATABASE_URL` (default: `postgresql://postgres:postgres@db:5432/postgres`)
- Override as needed for local/dev/prod

---
## Linting & Formatting
Run linter (inside backend container or locally):
```
ruff .
```

---
## Notes & Security
- No hardcoded credentials (except in default dev Docker Compose)
- All API validation and magic numbers/constants are centralized in `backend/constants.py`
- For production: use a secrets manager and configure container/user permissions

---
## Troubleshooting
- If `db` service fails on port 5432: ensure no local Postgres instance is running
- Re-run migrations after any Alembic/model changes
- For more logs: `docker compose logs <service>`

---
## License
Proprietary – KlarisAI pilot use only.

## Manual Setup Commands
DROP TABLE IF EXISTS alembic_version;
CREATE TABLE alembic_version (
    version_num VARCHAR(64) NOT NULL
);


npm install @mui/material @mui/icons-material @emotion/react @emotion/styled axios react-router-dom@6

