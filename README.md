# PRISM — Frontend

Next.js 15 dashboard for the PRISM analytics platform by [Augmex Technologies](https://augmex.io).

PRISM connects to Google Analytics 4 and Google Search Console, warehouses the data, and uses Claude AI to generate plain-language insights and a conversational analytics chatbot.

> This repository contains the frontend only (`apps/web`). The API backend runs separately on a VPS.

---

## Quick start (local dev)

### Prerequisites

| Tool | Version |
|------|---------|
| Docker + Docker Compose | 24+ |
| Python | 3.12+ |
| Node.js | 22+ |
| pnpm | 9.15+ |
| uv | 0.5+ |

### 1. Clone and configure

```bash
git clone <repo-url> prism
cd prism
cp .env.example .env
# Fill in .env — at minimum set PRISM_TOKEN_ENCRYPTION_KEY, PRISM_JWT_SECRET,
# GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, ANTHROPIC_API_KEY
```

Generate a 32-byte encryption key:

```bash
python -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

### 2. Install dependencies

```bash
# Python backend
uv pip install -e "apps/api[dev]"

# Frontend
pnpm install
```

### 3. Start services

```bash
docker compose -f infra/docker/docker-compose.yml up -d
```

This starts: MySQL 8, Redis 7, FastAPI API, Celery worker, Celery beat, Next.js frontend.

### 4. Run database migrations

```bash
cd apps/api
alembic -c ../../infra/migrations/alembic.ini upgrade head
```

### 5. Verify

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| API health | http://localhost:8000/api/v1/health |
| API docs | http://localhost:8000/api/docs |

---

## Development workflow

### Backend only (no Docker)

```bash
# Terminal 1 — API
cd apps/api
uvicorn prism.main:app --reload --port 8000

# Terminal 2 — Worker
cd apps/api
celery -A prism.workers.celery_app:celery_app worker --loglevel=info

# Terminal 3 — Beat scheduler
cd apps/api
celery -A prism.workers.celery_app:celery_app beat --loglevel=info
```

MySQL and Redis still need to be running (use `docker compose up mysql redis`).

### Frontend only

```bash
cd apps/web
pnpm dev
```

### Running tests

```bash
# Backend
pytest apps/api/tests/ -v

# Frontend lint and typecheck
pnpm --filter prism-web lint
pnpm --filter prism-web typecheck
```

### Database migrations

```bash
# Create a new migration
alembic -c infra/migrations/alembic.ini revision --autogenerate -m "describe the change"

# Apply migrations
alembic -c infra/migrations/alembic.ini upgrade head

# Roll back one step
alembic -c infra/migrations/alembic.ini downgrade -1
```

---

## Repository structure

```
prism/
  apps/
    api/          FastAPI backend (Python 3.12, SQLAlchemy 2.0, Celery)
    web/          Next.js 15 frontend (TypeScript, Tailwind, shadcn/ui)
    worker/       Celery worker entrypoint
  packages/
    shared-types/ OpenAPI-generated TypeScript types
  infra/
    docker/       Docker Compose + Dockerfiles
    migrations/   Alembic migrations
  scripts/        One-off data scripts (backfill, seed)
  docs/           Architecture, API, data model, AI prompt docs
  .github/
    workflows/    CI (GitHub Actions)
```

---

## Build phases

| Phase | Scope | Status |
|-------|-------|--------|
| 0 | Foundations (this PR) | In progress |
| 1 | GA4 ingestion and overview dashboard | Pending |
| 2 | GSC ingestion and search page | Pending |
| 3 | AI insights engine | Pending |
| 4 | Chatbot agent | Pending |
| 5 | Custom report builder | Pending |
| 6 | Multi-property and tenancy hardening | Pending |
| 7 | Paid ads adapters (Google Ads, Meta) | Deferred |

---

## Stack

**Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Alembic, Pydantic v2, Celery, Redis, aiomysql, structlog, Anthropic SDK

**Frontend:** Next.js 15 (App Router), TypeScript, Tailwind CSS, shadcn/ui, Tremor, TanStack Query, Zustand, NextAuth

**Database:** MySQL 8.0 (utf8mb4)

**AI:** Claude via Anthropic SDK (narrative: `claude-sonnet-4-7-20251222`, cheap: `claude-haiku-4-5-20251001`)

**Infra:** Docker Compose (local), InMotion VPS + Apache (API/worker/DB), Vercel (frontend)

---

## Environment variables

See [.env.example](.env.example) for the full list with descriptions.

Critical variables to set before first run:

- `PRISM_TOKEN_ENCRYPTION_KEY` — 32-byte base64 key for encrypting Google refresh tokens
- `PRISM_JWT_SECRET` — JWT signing secret
- `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` — Google OAuth app credentials
- `ANTHROPIC_API_KEY` — Anthropic API key

---

## Docs

- [Architecture](docs/ARCHITECTURE.md)
- [Data model](docs/DATA_MODEL.md)
- [API reference](docs/API.md)
- [AI prompt reference](docs/AI_PROMPTS.md)
