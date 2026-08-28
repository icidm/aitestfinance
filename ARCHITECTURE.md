# aitestfinance Architecture

## Overview

`aitestfinance` hosts the **Incidents Dashboard**, a PoC full-stack application that centralizes production incident monitoring for Inditex ecosystem services. It visualizes, filters and exports incidents with KPIs, timelines, severity/service breakdowns and service health.

The repository's responsibility is a single deployable dashboard: a FastAPI backend serving both a REST + PPTX API and a static SPA frontend, with deterministic synthetic data generation for demos. Scope is limited to the `incidents-dashboard/` application; workspace-level `.aicontext/` and `.opencode/` are resolved runtime configuration, not application code.

Primary entry points:

- `incidents-dashboard/backend/main.py` — FastAPI application (`Inditex Incidents Dashboard API v1.0.0`), all REST endpoints and PPTX generation.
- `incidents-dashboard/backend/seed.py` — deterministic synthetic data generator (`seed=42`, 120 incidents + 8 services).
- `incidents-dashboard/backend/data.json` — file-based persistence mutated at runtime.
- `incidents-dashboard/backend/requirements.txt` — Python dependencies.
- `incidents-dashboard/frontend/index.html` — single-file SPA (HTML/CSS/Vanilla JS, Chart.js + SheetJS via CDN).
- `incidents-dashboard/run.sh` — bootstrap and local start script.

## Stack & Environment

Technical context relevant to owned surfaces:

- **Language:** Python 3.13 (compatible 3.10+) — `incidents-dashboard/backend/main.py` and `seed.py` run on CPython.
- **Backend framework:** FastAPI `>=0.104.0` with Pydantic `BaseModel`, Uvicorn `[standard] >=0.24.0` as ASGI server.
- **Presentation export:** `python-pptx >=0.6.21` for 16:9 PowerPoint generation (`_build_pptx` in `main.py`).
- **Persistence:** SQLAlchemy 2.x async (`create_async_engine` + `async_sessionmaker`, `asyncpg`/`aiosqlite`) with Alembic sync migrations (`psycopg2`/`sqlite`) on `DATABASE_URL`/`DATABASE_URL_SYNC`; sync fallback `Base.metadata.create_all` when Alembic path varies; deterministic seeding (`seed=42`, 120 incidents + 8 services, injectable clock) and transactional `POST /api/reset`.
- **Frontend:** HTML5 + CSS3 + Vanilla JS, no framework, no build step; Chart.js `4.4.1` and SheetJS `xlsx 0.18.5` loaded from `jsdelivr.net`; Google Fonts `Carlito` with CSS variables; i18n dictionary `LANGUAGES` in `frontend/index.html`.
- **Infra/start:** Bash `run.sh` performs `seed.py` generation if `data.json` missing then `python3 -m uvicorn main:app --host 0.0.0.0 --port 8000`.

Build system: `pyproject.toml` + `requirements.txt` (`fastapi`, `uvicorn[standard]`, `python-pptx`, `sqlalchemy[asyncio]`, `asyncpg`, `psycopg2-binary`, `aiosqlite`, `alembic`, `python-jose[cryptography]`, `passlib[bcrypt]`, `bcrypt==4.0.1`, `python-multipart`, `pydantic-settings`, `prometheus-fastapi-instrumentator`, `python-json-logger`, `weasyprint`, `jinja2`, `apscheduler`, `httpx`, `pytest`, `pytest-asyncio`, `pytest-cov`, `ruff`, `mypy`); `Taskfile.yml` (`install/start/test/lint/format/dev`) and `docker-compose.yml` with `pg_isready` healthcheck.

Tool versions: `python:3.13` (slim non-root `USER app`), pinned via `pyproject.toml`/`requirements.txt` (`bcrypt==4.0.1` critical) and `Taskfile.yml`/`.github/workflows/ci.yml` (`setup-uv` + `setup-python`); no `asdf`/`nvm` manager, but `curl` healthcheck and `pg_isready` are required in compose/CI.

## Project Structure

```
aitestfinance/
├── README.md
├── ARCHITECTURE.md          # this document
├── AGENTS.md                # entry point pointing to ARCHITECTURE.md and Taskfile
├── Taskfile.yml             # local development commands (when present)
├── .gitignore
├── incidents-dashboard/
│   ├── run.sh               # bootstrap: seed check + uvicorn launch
│   ├── backend/
│   │   ├── main.py          # FastAPI app (799 lines, 8 API routes + PPTX builders)
│   │   ├── seed.py          # deterministic generator (SERVICES 8, 120 incidents)
│   │   ├── data.json        # generated runtime state (120 incidents, 8 services)
│   │   └── requirements.txt # fastapi, uvicorn[standard], python-pptx
│   └── frontend/
│       └── index.html       # SPA single-file (~1614 lines, styles + JS + CDN deps)
├── .aicontext/ -> ../../.aicontext   # resolved workspace configuration (symlink)
├── .opencode/               # workspace tooling overlay
└── .github/                 # GitHub configuration
```

Key areas affecting the mission:

- `incidents-dashboard/backend/` owns the API surface, business logic (stats aggregation, filtering, timeline bucketing, resolve/create/reset), file persistence and PPTX deck construction. `main.py` is the sole server module; `seed.py` owns test-data shape.
- `incidents-dashboard/frontend/` owns the presentation surface: header/KPIs/charts/incidents table/service health, all client-side filtering and export triggers.
- `incidents-dashboard/backend/data.json` is both seed output and runtime mutable store; `POST /api/incidents`, `PUT /api/incidents/{id}/resolve`, and `POST /api/reset` rewrite it.
- Repository root owns documentation (`README.md`, `ARCHITECTURE.md`) and local workflow definition (`Taskfile.yml`).

Relationships: Backend is the source of truth for incidents/services; frontend fetches `/api/incidents?limit=500` and `/api/services` together in `refreshAll()` and filters locally for table/chart/export. PPTX export is server-side filtering + deck rendering; Excel export is client-side via SheetJS from already fetched data.

## Architecture & Patterns

Organization model: **Single-process monolith serving API and static frontend.** `main.py` creates one `FastAPI` instance with open CORS (`allow_origins=["*"]`), mounts `StaticFiles` at `/dashboard` from `frontend/` and redirects `/` to `/dashboard/`. No separate frontend build, no micro-frontend, no background workers.

Boundaries:

- **API boundary:** Eight handlers in `main.py` under `/api/*` plus two frontend host concerns (`/` redirect, `/dashboard` static). All handlers share the `load_data`/`save_data` file pattern. No service layer, repository layer, or ORM — handlers directly read and mutate the JSON structure.
- **Data boundary:** Incidents and services are plain dicts with fields `id, title, service, severity, status, created_at, resolved_at, description` and `name, description, status, last_checked, uptime_7d` plus computed `active_incidents`. `seed.py` defines distributions: severity `critical 8% / high 22% / medium 40% / low 30%`, status `open 10% / in_progress 15% / resolved 75%`, 24 title templates and 8 description templates with `random.seed(42)`.
- **Frontend boundary:** `index.html` is a single HTML file with inline `<style>` (CSS variables, palette `accent #5560E8`, `ink #1E2A3B`, severity tokens) and inline `<script>`. State lives in module-scoped variables (`incidentsData`, `servicesData`, filter state). No component framework, no router beyond `applyFilters`/`refreshAll`.

Patterns:

- **File-as-database:** `DATA_FILE = os.path.join(os.path.dirname(__file__), "data.json")` with per-request full file read and per-mutation full file rewrite. Simple but not concurrent-safe; suits single-user demos.
- **Query-parameter filtering:** Each list endpoint applies optional equality filters (`status`, `severity`, `service`) and text search `q` (PPTX only) in Python list comprehensions, then sorts by `created_at desc` and applies `offset/limit` slicing.
- **MTTR computation:** `get_stats` iterates resolved incidents, computes `(resolved_at - created_at)` minutes, averages and rounds to 1 decimal.
- **Corporate deck builder:** `_build_pptx` builds a 6-slide 16:9 deck (`13.33"x7.5"`, `Calibri`, palette `ACCENT #5560E8`, `INK #1E2A3B`, severity `critical #E13D5B / high #E87A3D / medium #E0B03D / low #3DA86E`) with helpers `_txt`, `_rect`, `_card`, `_cell`, `_add_styled_table`, `_format_date/day` and bilingual `txt` dictionary keyed by `en/es`.
- **Deterministic seeding with time variance:** `seed.py` generates `created_at` as `NOW - timedelta(days 0-20, hours 0-23, minutes 0-59)` and `resolved_at` as `created_at + resolution_hours` (critical 0.5-4h, high 1-6h, other 0.5-12h).

Hardened patterns introduced during dashboard hardening (retained implementation):
- **SQLAlchemy 2.x async + Alembic sync migrations.** Single `create_async_engine` + `async_sessionmaker(expire_on_commit=False)` with `asyncpg`/`aiosqlite` and `psycopg2` sync URL for Alembic; `get_session()` yields per-request `AsyncSession` with rollback. Composite indexes `ix_incidents_created_id (created_at DESC, id DESC)` for cursor pagination, `ix_incidents_search_gin` (PG) / `FTS5 virtual table` (SQLite) for full-text search with `rank_for_q` deterministic ranking and `(rank,id)` cursor, and `bm25` fallback.
- **JWT HS256 + RBAC `require_role`.** `OAuth2PasswordBearer(tokenUrl="/api/auth/login")`, `HS256` with `jti` rotation + `TokenBlacklist`, short access 15m and refresh 30d; `require_role("viewer","operator","admin")` gates: viewer read, operator create/resolve, admin reset/schedule; `POST /api/auth/login` hardenings and lifespan `verify_password` hardening above apply.
- **Opaque cursor pagination.** `cursor` is `base64(JSON({v:1, created_at:ISO, id}))` for default sort and `base64(JSON({v:1, rank, id}))` for FTS with `WHERE (created_at,id) < (...)` / `(rank,id) < (...)` and `MAX_OFFSET=10000` guard for deprecated `offset`.
- **SSE via `EventBus`.** `GET /api/incidents/stream` + `/api/stats/stream` as `StreamingResponse(text/event-stream)` with `asyncio.Queue(100)` per connection, `Last-Event-ID` replay, heartbeat, `CancelledError` + `is_disconnected` cleanup, `fetch` ReadableStream auth and poll fallback; frontend `EventSource` + `fetchPaged`/`cursorStack`.
- **Observability pull mode.** `prometheus-fastapi-instrumentator` at `/metrics` with `http_requests_total`/`http_request_duration_seconds` labeled `method/endpoint/status` only (no `user_id`), custom `incident_created_total`/`incident_resolved_total` by `severity`, `RequestIdMiddleware` + `JsonFormatter` with `X-Request-ID` scrubbing `authorization`/`cookie`.
- **PDF + scheduling.** `WeasyPrint` Jinja HTML→PDF in `ThreadPoolExecutor(2)` via `run_in_threadpool`, mirroring PPTX filters/latest-day window and bilingual `en/es` corporate deck 16:9 Calibri `#5560E8`; `APScheduler SQLAlchemyJobStore` (Memory in tests) with admin `POST/GET/DELETE /api/reports/jobs` persistence and artifact download.

No repository-local evidence was found for layered domain patterns (DDD entities, CQRS, hexagonal ports), dependency injection, or event-driven architecture beyond the repository/EventBus abstractions above.

## Contracts & Integrations

Owned and produced contracts (hardened, all via `incidents-dashboard/backend`):

- `GET /api/stats` — no params; returns `{total_incidents, open_incidents, resolved_incidents, critical_open, mttr_minutes, by_severity{critical,high,medium,low}, by_status{open,in_progress,resolved}}`.
- `GET /api/incidents` — query `status?, severity?, service?, limit=25 (max 100), offset?, cursor? (opaque base64 v1 {created_at,id} or {rank,id}), q?`; returns `{total, limit, offset?, incidents[], next_cursor?, has_more}` sorted `created_at desc, id desc` (or `ts_rank desc, id asc` for FTS `q`); `cursor` provides keyset pagination with `MAX_OFFSET=10000` guard for legacy `offset`.
- `GET /api/incidents/timeline` — query `days=14`; returns day buckets `[{date, total, critical, high, medium, low, resolved}]` sorted asc, cutoff `now - days`.
- `GET /api/services` — returns `[{name, description, status, last_checked, uptime_7d, active_incidents}]` where `active_incidents` is computed `open+in_progress` per service, never persisted.
- `PUT /api/incidents/{incident_id}/resolve` — `require_role("operator","admin")`; sets `status=resolved`, `resolved_at=now`, returns `{ok, incident}` or `HTTPException 404`.
- `POST /api/incidents` — `require_role("operator","admin")`; body `CreateIncidentRequest{title, service, severity, description=""}`; creates `status=open`, `id=max+1`, `created_at=now`, `resolved_at=null`.
- `POST /api/reset` — `require_role("admin")`; transactional `seed_database` with injectable clock idempotent (`seed 42` → 120/8) and returns `{ok, message}`; unauth 401, viewer/operator 403.
- `GET /api/export/pptx` — `require_role("viewer","operator","admin")`; query `status?, severity?, service?, q?, days? ge=1, lang?=en, language?`; same filter/latest-day window semantics; returns `application/vnd.openxmlformats-officedocument.presentationml.presentation`.
- `GET /api/export/pdf` — `require_role("viewer","operator","admin")`; same filter set/window/bilingual handling; rendered via `WeasyPrint` Jinja HTML→PDF in `ThreadPoolExecutor(2)`, `application/pdf`.
- `GET /api/health` — returns `{status:"ok", db:"up"}` 200 or 503; `HEALTHCHECK curl -f /health`; compose `pg_isready` + `depends_on: service_healthy`.
- `GET /metrics` — `prometheus-fastapi-instrumentator` pull 15s; `http_requests_total`/`http_request_duration_seconds` + `incident_created_total`/`incident_resolved_total` by `severity`; no `user_id` label.
- `POST /api/auth/login` — accepts `application/x-www-form-urlencoded` and `application/json`; returns `{access_token (15m HS256), refresh_token (30d jti rotatable), token_type:"bearer"}`; wrong/corrupted password → 401 not 500.
- `POST /api/auth/refresh` — rotation with `TokenBlacklist jti`; replay → 401.
- `GET /api/auth/me` — authed viewer/operator/admin; unauth 401.
- `GET /api/incidents/stream` + `GET /api/stats/stream` — `require_role("viewer",...)`; `text/event-stream` SSE with `EventBus Queue(100)`, `Last-Event-ID`, heartbeat, `CancelledError` cleanup and fetch-stream Bearer; 401 if unauth.
- `POST/GET/DELETE /api/reports/jobs` + `GET /api/reports/jobs/{id}/artifact` — `require_role("admin")`; `APScheduler SQLAlchemyJobStore` persistent cron/interval jobs with `misfire_grace_time=300 coalesce=true`.
- `GET /` — `307 RedirectResponse` to `/dashboard/`.
- `GET /dashboard/*` — `StaticFiles(directory=FRONTEND_DIR, html=True)` serving `frontend/index.html` (header pill `#userPill`, `headerLoginBtn Login / Switch User`, `loginModal` with `Cancel`/overlay/`Escape`, `handleManualLogin` dual, `decodeJwtPayload`→`updateAuthUI`).

Consumed integrations:

- Browser CDN: `https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js` and `xlsx@0.18.5/dist/xlsx.full.min.js`; `https://fonts.googleapis.com/css2?family=Carlito...`
- No Inditex internal service integrations, no authentication provider, no message broker, no database driver.

Implemented hardening integrations (delivered): PostgreSQL/SQLite via SQLAlchemy 2.x async + Alembic sync URL, JWT/OAuth2 HS256 with `viewer/operator/admin` RBAC, GitHub Actions `uv+postgres:17+ruff/mypy/pytest --cov-fail-under=80/trivy/Codecov` + Taskfile, multi-stage `python:3.13-slim` non-root `USER app` healthcheck, cursor pagination opaque base64 + FTS tsvector/GIN + FTS5, SSE live streams with filter-scoped `EventBus`, Prometheus `instrumentator` + JSON structured logs, WeasyPrint PDF + APScheduler scheduling. The dashboard now runs durably with auth, paging, live, observability, and exports.

No contracts or integrations beyond the REST/PPTX API and the CDN/font dependencies were identified.

## Runtime & Data Flow

Local runtime flow (hardened):

1. `incidents-dashboard/backend` may run via `task start` / `docker compose up` or `run.sh` legacy; startup runs `alembic upgrade head` (docker entrypoint) or the app lifespan's robust startup (`sync_engine` alembic → fallback `create_all`) before seeding 120/8 deterministically with injectable clock; WAL pragmas are set on connect.
2. `uvicorn` loads `app.main:app`; `FRONTEND_DIR` is resolved as `os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")` and mounted at `/dashboard`.
3. Browser loads `/dashboard/` → `ensureAuth()` performs viewer auto-login (`viewer/Viewer123!` deduped) storing `access_token`+`refresh_token`, `updateAuthUI()` decodes JWT to `#userPill viewer (viewer)` and `headerLoginBtn`; then fetches `GET /api/stats`, `GET /api/incidents?limit=25&cursor` (via `fetchPaged`/`cursorStack` with `Authorization: Bearer`), `GET /api/services`, `GET /api/incidents/timeline?days=14` via `refreshAll()` (Promise.all) and SSE `fetch` stream with Bearer/timeout heartbeat; 401→`refresh`→`loginModal` fallback.
4. Mutations (`create`, `resolve`, `reset`) POST/PUT with `Authorization: Bearer` and `require_role` checks; the API uses per-request `AsyncSession` transactions; on success the `EventBus` publishes to SSE subscribers and `incident_created_total`/`incident_resolved_total` metrics increment; frontend then calls `refreshAll()` and `updateAuthUI()` to re-render.

Data flow specifics:

- **Reads:** `async with get_session()` per request; `get_incidents` applies equality filters + `q` FTS (`rank_for_q`) + `days` latest-day window → `ORDER BY created_at DESC, id DESC` (or `rank DESC, id ASC` for FTS) → keyset `WHERE (created_at,id) < (...)` or legacy `offset` guard, `limit+1` probe for `has_more`/`next_cursor`; `get_incidents_timeline` filters by `now - days` and buckets; `get_services` counts `active_incidents` per service without persisting.
- **Writes:** `create_incident`/`resolve_incident`/`reset_database` run in `async with session.begin()` transactions with per-request `AsyncSession`; `reset` uses split sessions and injectable clock; concurrent resolves use distinct `resolved_at` via row-level transactions.
- **PPTX/PDF export:** `export_pptx`/`export_pdf` load via shared `apply_filters`/`apply_days_filter`, PPTX via `_build_pptx` 6-slide 16:9 Calibri `#5560E8`, PDF via Jinja `report.html` → `WeasyPrint` in `ThreadPoolExecutor(2)` → `StreamingResponse`; headers reflect bilingual `en/es`.
- **Frontend export:** `exportExcel()` filters already-fetched page locally; `exportPptx()`/`exportPdf()` build `URLSearchParams` from `filterSearch`/`q`/`status/severity/service/days/lang` and trigger `<a>` download via `fetchWithAuth` with Bearer.

Lifecycle boundaries: DB migration via `alembic upgrade head` (entrypoint + lifespan fallback) before serving, `HEALTHCHECK curl -f /health` and compose `pg_isready` gating, SSE `EventBus` background queues, `APScheduler` with `SQLAlchemyJobStore` for scheduled PDF jobs, Prometheus `/metrics` scrape 15s and JSON logs with `request_id` correlation. The process terminates on `Ctrl+C` (uvicorn shutdown); `app.db` WAL + `pgdata` volume survive restarts and `POST /api/reset` re-seeds transactionally.

## Conventions

- **Python style:** `main.py` uses `FastAPI` + `CORSMiddleware` + `Pydantic BaseModel` with function-level handlers; no separate router modules. `seed.py` uses `random.seed(42)`, `datetime.now()` and `timedelta` for reproducible synthetic data. Imports are grouped standard-library then third-party (`fastapi`, `pptx`) then local.
- **Frontend conventions:** Single-file SPA with CSS variables (`--accent`, `--ink`, etc.), `Carlito` font, responsive `max-width 1440px`, grid layouts for KPIs (`grid 4`), charts (`2fr 1fr 1fr`), and services (`grid 4`). Language dictionary `LANGUAGES` with 60+ keys, helper `t(key, vars)`, persistence via `localStorage dashboardLanguage`. Sorting uses a header click toggling asc/desc arrow; pagination uses `10/25/50` rows with Previous/Next; filters are combined via search `datalist` (10 suggestions), selects and active chips with `Clear all`; charts are clickable filters.
- **Documentation conventions:** `README.md` is the feature and API reference with tables for endpoints, structure diagram, install/run instructions in both `run.sh` and manual `uvicorn` forms. `ARCHITECTURE.md` is the canonical architecture reference for agents.
- **PPTX conventions:** 16:9 (`13.33x7.5`), font `Calibri`, corporate palette (`ACCENT #5560E8`, `LILAC #EEF0FB`, `INK #1E2A3B`), 6-slide structure (Cover → Executive Summary → Distribution → Timeline → Services → Recent Incidents), footer pagination `02 / 06`, language badge `EN/ES`, hairline borders `HAIRLINE #E4E7F0`, row alternation `ROW_ALT #F7F8FC`.
- **Validation and contribution expectations:** Quality is enforced by `ruff`/`mypy`/`pytest --cov-fail-under=80` (57 tests, accepted-risk coverage gate documented in verification) plus `httpx ASGITransport` lifespan integration and `docker build`/`trivy`/`Codecov OIDC`; CI `.github/workflows/ci.yml` uses `uv` + `postgres:17` service and fails on any gate; `Taskfile.yml` delegates `install/start/test/lint/format` to the same commands for local/CI parity.

## Constraints & Gotchas

- **File-based persistence is not concurrent-safe.** `save_data` does a plain `open(DATA_FILE,"w") + json.dump` without locking or atomic rename. Concurrent `PUT /resolve` or `POST /incidents` can interleave and lose writes; `Uvicorn` with multiple workers would amplify this. The roadmap's PostgreSQL/SQLite + SQLAlchemy/Alembic migration is intended to replace this.
- **`GET /api/services` mutates the loaded service dicts in place.** `get_services` assigns `svc["active_incidents"]` onto objects from `load_data()` without copying; if `save_data` were called after, that computed field would persist. Current code does not save after, but agents adding persistence should clone or omit computed fields.
- **Two different timeline window semantics exist.** `GET /api/incidents/timeline` uses `cutoff = now() - days`, while `GET /api/export/pptx` with `days` anchors to `latest incident day` (`latest_day ... cutoff = latest_day - (days-1)`). Frontend timeline display is anchored to the latest incident to keep seeded historic data visible even when demos run with old dates — do not unify both semantics without checking the UI expectation.
- **CORS is wide open and there is no authentication.** `allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"]` plus no JWT/OAuth2. Any origin can call `POST /api/incidents` or `PUT /resolve`. The hardening roadmap adds JWT/OAuth2 with roles; do not assume auth exists when adding new endpoints.
- **Offset/limit pagination, not cursor.** `GET /api/incidents` paginates with `offset/limit` on an in-memory sorted list; there is no cursor or total-count optimization. `frontend` fetches `limit=500` and does additional client-side filtering for search. Changing to cursor pagination or full-text search (roadmap) will require both API and frontend `applyFilters` changes.
- **`data.json` is runtime-mutable and `.gitignore` may exclude it.** Deleting `data.json` or calling `POST /api/reset` regenerates via `seed.py`; do not commit large regenerated data files without checking ignore rules. `seed.py`'s `NOW = datetime.now()` at import time means regeneration time affects `created_at` distribution (not a fixed historical dataset).
- **`PUT /api/incidents/{id}/resolve` returns a non-standard error shape.** On miss it returns `({"ok": False, "error": "Incident not found"}, 404)` as a tuple, which FastAPI serializes differently than raising `HTTPException(404)`. Frontend currently does not depend on error detail parsing; maintain or migrate to `HTTPException` consistently when hardening error handling.
- **`StaticFiles` serves `frontend/index.html` as a plain file.** No build, no cache headers, no SPA fallback beyond `html=True` directory mount. `FRONTEND_DIR` is resolved via `os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")` — moving `main.py` or `frontend/` without updating that path breaks `/dashboard`.
- **PPTX table data is truncated for presentation.** Service names are sliced `[:28]` and titles `[:64]` inside `_build_pptx`; severity abbreviations switch (`H`/`A` for high, `L`/`B` for low) by language. Do not assume the export contains full field values.
- **`run.sh` uses `python3 -m uvicorn` and does not create a virtual environment.** Agents setting up local development should create a venv and `pip install -r incidents-dashboard/backend/requirements.txt` before running `run.sh`, or delegate to `task install` / `task start` once `Taskfile.yml` is available. Port `8000` must be free.
- **`frontend/index.html` clocks and i18n have side effects.** Clock updates every 30s via `toLocaleString('en-GB'/'es-ES')`; `setLanguage` persists to `localStorage` and repaints the entire UI. `exportPptx` builds a filtered URL with `q/status/severity/service/days/lang` — changes to API filter names must be mirrored in the frontend URL builder.
- **SQLite needs WAL mode.** Default `DELETE` journal with no `busy_timeout` causes `database is locked` when the dashboard's `refreshAll()` issues four parallel `AsyncSession` requests on the same file; the backend sets `PRAGMA journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000` via `event.listens_for(engine.sync_engine, "connect")` to avoid this.
- **Fresh SQLite file has no tables until startup creates them.** `app.db` 0 bytes yields `no such table: users`; the lifespan must attempt `alembic upgrade head` via a sync engine with absolute `script_location` (handling docker `/app` vs local CWD and `SELECT 1` probe to create the file) and fall back to both async `Base.metadata.create_all` and sync `create_all`; this covers both Postgres pool and SQLite `check_same_thread=False` cases and must run before seeding.
- **Passlib bcrypt 4.1+ is incompatible with `passlib 1.7.4`.** `pwd_context.verify` throws `UnknownHashError`/`ValueError` on corrupted or truncated hashes and on version mismatch, which must not surface as 500; the dashboard pins `bcrypt==4.0.1` and hardens `verify_password`/`get_password_hash` to catch `UnknownHashError`/`ValueError`/`AttributeError` and fallback to `bcrypt.checkpw`/`hashpw` returning False, so login returns 401.
- **`POST /api/auth/login` accepts both `application/x-www-form-urlencoded` and `application/json`.** Frontend `ensureAuth` uses `URLSearchParams` form, but manual flows may send JSON; the handler parses `Request` by content-type, tries form then JSON fallback, validates missing fields as 422, and wraps `session.execute` and password verification in try/except to never return 500 (corrupted hash → 401).
- **Lifespan seeding is split and idempotent.** Users and incidents are seeded in two isolated `async_session_factory()` sessions with an injectable clock (`_default_clock` → `datetime.now(timezone.utc)` for deterministic `seed 42` → 120 incidents/8 services); the users session checks `admin` existence before inserting `viewer/Viewer123!`, `operator/Operator123!`, `admin/Admin123!` so second startup leaves 3 users and `alembic_version` persisted.
- **Frontend must not duplicate `let pageSize`.** A duplicate `let pageSize=25` plus `let nextCursor=null,hasMore=false,pageSize=25` causes `SyntaxError: Identifier 'pageSize' has already been declared` and aborts all JS before `refreshAll()`, leaving the dashboard vacio; keep a single `let pageSize` source of truth and single `cursorStack`/`nextCursor`/`hasMore` state.
- **Filter input ids must match.** `getCurrentFilterParams` must read `filterSearch` and `pageSize`, not stale `searchInput`/`rowsSelect`; mismatched ids drop the `q` server filter and break the cursor `fetchPaged` contract.
- **Every `/api/*` fetch must carry `Authorization: Bearer`.** After JWT hardening `require_role` gates all endpoints, the SPA attaches the token via `api()` for cursor-paged `fetchPaged`, search `q`, stats/timeline/services, `fetchWithAuth` for PPTX/PDF, and `fetch` ReadableStream for SSE; `EventSource` cannot set headers, so SSE uses `fetch` with Bearer plus 15s polling fallback via `api()`.
- **CORS must deny `*`.** `CORS_ORIGINS="*"` is fail-closed to `["http://localhost:8000","http://localhost:3000"]` and any `*` entries are filtered from comma/JSON origin lists; `allow_credentials` stays true only when origins are not `*`.
- **Login UI visibility is header-driven.** `headerLoginBtn` (`Login / Switch User` btn-primary 2px `#5560E8` shadow Calibri 700) opens a centered `loginModal` (380px, 2px `#5560E8`, Calibri) with `Cancel` button, overlay click (`target.id==loginModal`), and `Escape` handling; `handleManualLogin` tries form then JSON dual, displays error, stores `access_token`+`refresh_token`, calls `decodeJwtPayload` (base64url `sub`+`role`) → `#userPill` (`username (role)` with `#5560E8` badge) + `updateAuthUI()` + `refreshAll()`; `api()` 401→`refresh`→`loginDefault`→`showLoginModal` and `ensureAuth` viewer auto-login (`Viewer123!` deduped via `viewerLoginPromise`) are preserved; `handleLogout` clears tokens and reopens the modal.
