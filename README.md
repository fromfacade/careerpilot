# CareerPilot

A local-first, autonomous-leaning job-search and application assistant. This repo currently
implements **Phase 1**: candidate profile + preferences, a configurable job source registry,
Greenhouse/Lever/Ashby discovery with normalization and dedup, transparent rule-based eligibility
and match scoring, and a dashboard wired to that real, persisted data.

**No autonomous submission code exists in this repo.** That is a later phase, gated on explicit
re-confirmation with the user and end-to-end testing — see `docs/architecture.md` and
`docs/implementation-plan.md` for what Phase 1 does and does not include.

For the full module map, data model, and the engineering non-negotiables (never fabricate
qualifications, no CAPTCHA/MFA bypass, no duplicate applications, emergency pause switch, etc.),
see:

- [`docs/architecture.md`](docs/architecture.md)
- [`docs/data-model.md`](docs/data-model.md)
- [`docs/implementation-plan.md`](docs/implementation-plan.md)

## Tech stack

- **Backend**: Python, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL, Pydantic v2, HTTPX, APScheduler, Pytest
- **Frontend**: React 19, TypeScript, Vite, Tailwind CSS v4
- **Automation**: none yet (Playwright form automation is a later phase)

## Prerequisites

Verified on Windows with these exact versions (other recent versions are likely fine, but this is
what was actually tested):

| Tool | Version used |
|---|---|
| Python | 3.11.9 |
| Node.js | 24.22.1 |
| npm | 11.19.1 |
| PostgreSQL | 17.11 |
| Git | 2.55.0 |

If you need to install any of these on Windows via `winget`:

```powershell
winget install -e --id Python.Python.3.11
winget install -e --id OpenJS.NodeJS.LTS
winget install -e --id PostgreSQL.PostgreSQL.17
winget install -e --id Git.Git
```

After installing PostgreSQL, make sure `C:\Program Files\PostgreSQL\17\bin` is on your `PATH`
(the installer usually does this; if `psql` isn't recognized in a new terminal, add it manually
via `[System.Environment]::SetEnvironmentVariable`).

## 1. Database setup

Create the application role and two databases (one for normal dev use, one dedicated to the
automated test suite — tests never touch your dev data):

```powershell
$env:PGPASSWORD = '<the postgres superuser password you set during install>'
psql -U postgres -h 127.0.0.1 -c "CREATE ROLE careerpilot LOGIN PASSWORD 'careerpilot_dev_password';"
psql -U postgres -h 127.0.0.1 -c "CREATE DATABASE careerpilot_dev OWNER careerpilot;"
psql -U postgres -h 127.0.0.1 -c "CREATE DATABASE careerpilot_test OWNER careerpilot;"
```

(If you use a different username/password, just update `backend/.env` accordingly in the next
step — nothing is hardcoded outside of that file.)

## 2. Backend setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt

Copy-Item .env.example .env
# Edit .env if you used different DB credentials/ports than the defaults above.

alembic upgrade head

# Optional: seed a handful of real, verified-reachable public job boards
# (Stripe/Greenhouse, Palantir/Lever, OpenAI+Notion+Ramp/Ashby) so there's
# something real to discover on first run. Safe to re-run — already-added
# sources are skipped, not duplicated.
python -m scripts.seed_job_sources

uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Leave this running. In a second terminal, verify it's actually up:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/health
# Expect: @{status=ok; database=ok}
```

## 3. Frontend setup

In a new terminal:

```powershell
cd frontend
Copy-Item .env.example .env
# Defaults to http://127.0.0.1:8000, matching the backend above.

npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). You should see the CareerPilot dashboard:
candidate profile, preferences, job source registry, discovery status, and the job list. If you
ran the seed script above, click **"Run discovery now"** to pull real jobs from those boards.

## 4. Running the tests

Backend (against the real `careerpilot_test` Postgres database — no mocked DB layer):

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest -q
```

Frontend type-check + production build:

```powershell
cd frontend
npm run build
```

## 5. Docker Compose (untested on this machine, provided for later/CI use)

A `docker-compose.yml` plus `backend/Dockerfile` and `frontend/Dockerfile` are included for
non-Windows dev parity and CI, but **Docker Desktop was not installed on the machine this project
was built on**, so this path has not been exercised end-to-end. The native setup above (steps
1–3) is the one that has actually been run and verified. If you have Docker available:

```powershell
docker compose up --build
```

Please verify it works (and update this note) before relying on it.

## Project layout

```
backend/        FastAPI app, SQLAlchemy models, Alembic migrations, services, adapters, tests
frontend/       React + TypeScript + Tailwind dashboard, typed API client
docs/           architecture.md, data-model.md, implementation-plan.md
docker-compose.yml, backend/Dockerfile, frontend/Dockerfile   (untested, see above)
```

## Current status

Phase 1 is implemented and its full test suite passes (92 backend tests; frontend type-checks and
builds cleanly). See `docs/implementation-plan.md` for the increment-by-increment checklist and
`docs/architecture.md` for where later-phase safety requirements (submission policy engine,
pause switch, audit logging) will attach once that work begins.
