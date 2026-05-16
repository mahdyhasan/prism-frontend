# PRISM

AI-powered analytics platform by [Augmex Technologies](https://augmex.io).

PRISM connects Google Analytics 4 and Google Search Console, warehouses data in MySQL, and uses Claude AI to generate plain-language insights, a daily brief, a conversational analytics chatbot, and automated pinned-question re-runs.

---

## What's inside

```
prism/
  apps/
    api/          FastAPI backend — Python 3.12, SQLAlchemy 2.0 async, Celery
    web/          Next.js 15 frontend — TypeScript, Tailwind CSS
  infra/
    docker/       Docker Compose + Dockerfiles
    migrations/   Alembic migrations (MySQL 8.0)
  packages/
    shared-types/ Shared TypeScript types
  scripts/        One-off data scripts (backfill, seed)
```

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2 |
| Task queue | Celery + Redis |
| Database | MySQL 8.0 |
| Frontend | Next.js 15 (App Router), TypeScript, Tailwind CSS, TanStack Query |
| Auth | NextAuth + Google OAuth |
| AI | Claude via Anthropic SDK (`claude-sonnet-4-7`, `claude-haiku-4-5`) |
| Hosting | VPS (API + worker + DB) + Vercel (frontend) |

---

## Features shipped

| Area | What PRISM does |
|---|---|
| **Data ingestion** | Nightly GA4 + GSC sync; cross-source `xs_page_daily` join table |
| **Overview dashboard** | Sessions, users, engagement, bounce rate, per-event conversion rates with deltas |
| **Pages report** | Traffic, conversion rate, engagement, GSC signals, Page Health score, Clarity frustration score |
| **Performance** | Core Web Vitals (PSI + CrUX): site-wide origin card, problem pages table, mobile vs desktop |
| **Search** | GSC clicks, impressions, CTR, position; top queries and pages; opportunities |
| **Insights** | Nightly detection: anomaly, trend, decay, cannibalization, opportunity, CWV regression, frustration |
| **Daily brief** | AI-narrated summary of the last 24 hours, generated at 07:00 UTC |
| **Chat agent** | Claude with 16 tools (GA4, GSC, cross-source, CWV, memory, actions) via SSE streaming |
| **Pinned questions** | Scheduled re-runs with structured JSON answers and prior-run diffing |
| **Actions panel** | AI queues GSC sitemap submit/delete; user confirms via HMAC-verified one-click |
| **Memory** | Automatic extraction of goals, hypotheses, and decisions from chat turns |
| **Microsoft Clarity** | Deep-link heatmaps + recordings from Pages; frustration score ingestion |

---

## Quick start

### Prerequisites

| Tool | Version |
|---|---|
| Docker + Docker Compose | 24+ |
| Python | 3.12+ |
| Node.js | 22+ |
| pnpm | 9.15+ |
| uv | 0.5+ |

### 1. Clone and configure

```bash
git clone <repo-url> prism
cd prism
cp apps/api/.env.example apps/api/.env
# Fill in apps/api/.env — see "Environment variables" below
```

Generate required secrets:

```bash
# Encryption key (32-byte base64)
python -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"

# JWT secret
python -c "import secrets; print(secrets.token_hex(32))"

# Actions HMAC secret
python -c "import secrets; print(secrets.token_hex(32))"
```

### 2. Install dependencies

```bash
# Python backend
cd apps/api && uv pip install -e ".[dev]" && cd ../..

# Frontend
pnpm install
```

### 3. Start infrastructure

```bash
docker compose -f infra/docker/docker-compose.yml up -d
```

Starts: MySQL 8, Redis 7, FastAPI, Celery worker, Celery beat, Next.js.

### 4. Run migrations

```bash
alembic -c infra/migrations/alembic.ini upgrade head
```

### 5. Verify

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| API health | http://localhost:8000/api/v1/health |
| API docs | http://localhost:8000/api/docs |

---

## Development

### Backend (no Docker)

```bash
# Terminal 1 — API
cd apps/api && uvicorn prism.main:app --reload --port 8000

# Terminal 2 — Worker
cd apps/api && celery -A prism.workers.celery_app:celery_app worker --loglevel=info

# Terminal 3 — Beat
cd apps/api && celery -A prism.workers.celery_app:celery_app beat --loglevel=info
```

MySQL and Redis must still be running: `docker compose up mysql redis -d`

### Frontend only

```bash
cd apps/web && pnpm dev
```

### Tests

```bash
# Backend
pytest apps/api/tests/ -v

# Frontend
pnpm --filter prism-web lint
pnpm --filter prism-web typecheck
```

### Migrations

```bash
# New migration
alembic -c infra/migrations/alembic.ini revision --autogenerate -m "description"

# Apply
alembic -c infra/migrations/alembic.ini upgrade head

# Roll back one
alembic -c infra/migrations/alembic.ini downgrade -1
```

---

## Nightly schedule (UTC)

| Time | Task |
|---|---|
| 03:00 | CWV page audits (PSI) |
| 03:30 | Microsoft Clarity sync |
| 04:00 | GA4 daily sync |
| 04:15 | CWV origin pull (CrUX) |
| 05:00 | GSC daily sync |
| 06:00 | Cross-source join + AI insights |
| 07:00 | Daily brief generation |
| 08:00 | Pinned question re-runs |
| Every 5 min | Expire stale actions |

---

## Environment variables

Copy `apps/api/.env.example` to `apps/api/.env` and fill in:

| Variable | Required | Description |
|---|---|---|
| `PRISM_TOKEN_ENCRYPTION_KEY` | Yes | 32-byte base64 key for encrypting Google tokens |
| `PRISM_JWT_SECRET` | Yes | JWT signing secret |
| `GOOGLE_OAUTH_CLIENT_ID` | Yes | Google OAuth client ID |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Yes | Google OAuth client secret |
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key |
| `ACTIONS_HMAC_SECRET` | Yes | HMAC secret for action confirmation tokens |
| `PSI_API_KEY` | No | Google PageSpeed Insights API key |
| `CRUX_API_KEY` | No | Chrome UX Report API key (same key as PSI) |
| `SENTRY_DSN` | No | Sentry DSN for error tracking |

Frontend variables go in `apps/web/.env.local` — see `apps/web/.env.example`.

---

## Contributing

1. Branch off `main`
2. Backend changes live in `apps/api/`, frontend in `apps/web/`
3. Run `pytest` and `pnpm lint` before opening a PR
4. Never commit `.env` files — use `.env.example` as the template
