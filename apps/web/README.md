# PRISM — Frontend

Next.js 15 dashboard for the PRISM analytics platform by [Augmex Technologies](https://augmex.io).

PRISM connects to Google Analytics 4 and Google Search Console, warehouses the data, and uses Claude AI to generate plain-language insights and a conversational analytics chatbot.

---

## Tech stack

- Next.js 15 (App Router)
- TypeScript (strict)
- Tailwind CSS
- Recharts
- TanStack Query
- NextAuth v5 (Google OAuth)

---

## Local development

### Prerequisites

- Node.js 22+
- pnpm 9.15+
- The PRISM API running at `http://localhost:8000`

### Setup

```bash
# Install dependencies
pnpm install

# Copy env file and fill in values
cp .env.example .env.local

# Start dev server
pnpm dev
```

Open [http://localhost:3000](http://localhost:3000).

### Environment variables

| Variable | Description |
|----------|-------------|
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |
| `NEXTAUTH_SECRET` | Random secret for NextAuth session signing |
| `NEXTAUTH_URL` | Full URL of this app (e.g. `http://localhost:3000`) |
| `NEXT_PUBLIC_API_BASE_URL` | PRISM API base URL (e.g. `http://localhost:8000`) |

---

## Deployment

Deployed on [Vercel](https://vercel.com). Connect this repository and set:

- **Root Directory:** `apps/web`
- **Framework Preset:** Next.js
- Add all environment variables from the table above in the Vercel dashboard.

---

## Pages

| Route | Description |
|-------|-------------|
| `/login` | Google sign-in |
| `/onboarding` | Link first GA4 property |
| `/properties/[id]/overview` | Traffic KPIs, trends, top pages, sources, devices |
| `/properties/[id]/search` | GSC queries, pages, opportunities *(Phase 2)* |
| `/properties/[id]/insights` | AI insight feed *(Phase 3)* |
| `/chat` | Conversational analytics chatbot *(Phase 4)* |
