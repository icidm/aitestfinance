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
- **Persistence:** File-based `incidents-dashboard/backend/data.json` (no database; synchronous `load_data`/`save_data` with `json.load`/`json.dump`).
- **Frontend:** HTML5 + CSS3 + Vanilla JS, no framework, no build step; Chart.js `4.4.1` and SheetJS `xlsx 0.18.5` loaded from `jsdelivr.net`; Google Fonts `Carlito` with CSS variables; i18n dictionary `LANGUAGES` in `frontend/index.html`.
- **Infra/start:** Bash `run.sh` performs `seed.py` generation if `data.json` missing then `python3 -m uvicorn main:app --host 0.0.0.0 --port 8000`.

Build system: No repository-local build system is declared (`stack: unknown`, `build_system: unknown`); no `pom.xml`, `package.json`, `pyproject.toml`, `.tool-versions`, `Makefile`, or `Taskfile` was present before generation. `requirements.txt` declares the three Python dependencies. No AMIGA project status applies.

Tool versions: No version-pin file exists in the repository. The only pinned versions are the minimum specifiers in `incidents-dashboard/backend/requirements.txt`. No repository-local evidence was found for a tool manager such as `asdf` or `nvm`.

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

No repository-local evidence was found for layered domain patterns (DDD entities, CQRS, hexagonal ports), dependency injection, or event-driven architecture.

## Contracts & Integrations

Owned and produced contracts (all defined in `incidents-dashboard/backend/main.py`):

- `GET /api/stats` — no params; returns `{total_incidents, open_incidents, resolved_incidents, critical_open, mttr_minutes, by_severity{critical,high,medium,low}, by_status{open,in_progress,resolved}}`.
- `GET /api/incidents` — query `status?, severity?, service?, limit=50, offset=0`; returns `{total, offset, limit, incidents[]}` sorted `created_at desc`.
- `GET /api/incidents/timeline` — query `days=14`; returns day buckets `[{date, total, critical, high, medium, low, resolved}]` sorted asc, cutoff `datetime.now() - timedelta(days)`.
- `GET /api/services` — returns `[{name, description, status, last_checked, uptime_7d, active_incidents}]` where `active_incidents` counts open/in_progress per service.
- `PUT /api/incidents/{incident_id}/resolve` — sets `status=resolved`, `resolved_at=now().isoformat()`, persists and returns `{ok, incident}` or `404`.
- `POST /api/incidents` — body `CreateIncidentRequest{title, service, severity, description=""}`; creates `status=open`, `id=max+1`, `created_at=now`, `resolved_at=null`.
- `POST /api/reset` — invokes `seed.main()` and returns `{ok, message}`.
- `GET /api/export/pptx` — query `status?, severity?, service?, q?, days? ge=1, lang?=en, language?`; `q` matches `id/title/service/description` case-insensitive; `days` windows from latest incident day (`latest_day - (days-1)` to `latest_day` inclusive); `lang/language` selects `en` vs `es`; returns `StreamingResponse` `application/vnd.openxmlformats-officedocument.presentationml.presentation` with `Content-Disposition: incidents_dashboard_<timestamp>.pptx`.
- `GET /` — `307 RedirectResponse` to `/dashboard/`.
- `GET /dashboard/*` — `StaticFiles(directory=FRONTEND_DIR, html=True)` serving `frontend/index.html`.

Consumed integrations:

- Browser CDN: `https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js` and `xlsx@0.18.5/dist/xlsx.full.min.js`; `https://fonts.googleapis.com/css2?family=Carlito...`
- No Inditex internal service integrations, no authentication provider, no message broker, no database driver.

Prospective hardening integrations (roadmap, not yet implemented): PostgreSQL/SQLite via SQLAlchemy + Alembic, JWT/OAuth2 with roles, GitHub Actions CI (pytest/httpx/coverage), Docker + docker-compose with healthchecks, cursor pagination + full-text search, WebSockets/SSE live updates, Prometheus + structured logs, PDF export + report scheduling. No repository-local evidence for these was found in current code.

No contracts or integrations beyond the REST/PPTX API and the CDN/font dependencies were identified.

## Runtime & Data Flow

Local runtime flow:

1. `incidents-dashboard/run.sh` checks `backend/data.json`; if absent, runs `python3 seed.py` to write 120 incidents and 8 services. It then launches `python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info` from `incidents-dashboard/backend/`.
2. `uvicorn` loads `main:app`; `FRONTEND_DIR` is resolved as `os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")` and mounted at `/dashboard`.
3. Browser loads `/dashboard/` → fetches `GET /api/stats`, `GET /api/incidents?limit=500`, `GET /api/services`, `GET /api/incidents/timeline?days=14` via `refreshAll()` (Promise.all). Timeline fetches are repeated in `refreshAll` and `applyFilters` depending on code path.
4. Mutations (`create`, `resolve`, `reset`) POST/PUT to the API, which `load_data` → mutate → `save_data` → return JSON; frontend then calls `refreshAll()` to re-render.

Data flow specifics:

- **Reads:** `load_data()` opens `data.json` per request. `get_incidents` filters, sorts desc, slices by offset/limit. `get_incidents_timeline` filters by `now - days` cutoff and buckets by `strftime("%Y-%m-%d")`. `get_services` counts `active_incidents` per service by scanning incidents.
- **Writes:** `create_incident` appends, `resolve_incident` mutates `status`/`resolved_at`, `reset_data` delegates to `seed.main()` which overwrites `data.json`.
- **PPTX export:** `export_pptx` loads, applies the same filters as the list endpoints plus `q` and `days` (days window is anchored to the *latest incident's day*, not `now`), builds the presentation via `_build_pptx` (metrics: total/open/resolved/in_progress/critical_open, MTTR, `by_severity`/`by_status`, 10-day timeline table, top-10 services, 18 recent incidents), writes to `io.BytesIO`, streams.
- **Frontend export:** `exportExcel()` filters the already-fetched `incidentsData` locally within `TIMELINE_WINDOW_DAYS=14` and uses `XLSX.utils.json_to_sheet` + `XLSX.writeFile(indidents_<date>.xlsx)`. `exportPptx()` builds `URLSearchParams` from current filter UI plus `days` and `lang` and triggers a download via an `<a>` navigation to `/api/export/pptx?...`.

Lifecycle boundaries: No background scheduler, no queue consumer, no database migration step, no healthcheck endpoint, no WebSocket/SSE upgrade. The process terminates on `Ctrl+C` (uvicorn shutdown). `data.json` survives restarts unless deleted or reset via `POST /api/reset`.

## Conventions

- **Python style:** `main.py` uses `FastAPI` + `CORSMiddleware` + `Pydantic BaseModel` with function-level handlers; no separate router modules. `seed.py` uses `random.seed(42)`, `datetime.now()` and `timedelta` for reproducible synthetic data. Imports are grouped standard-library then third-party (`fastapi`, `pptx`) then local.
- **Frontend conventions:** Single-file SPA with CSS variables (`--accent`, `--ink`, etc.), `Carlito` font, responsive `max-width 1440px`, grid layouts for KPIs (`grid 4`), charts (`2fr 1fr 1fr`), and services (`grid 4`). Language dictionary `LANGUAGES` with 60+ keys, helper `t(key, vars)`, persistence via `localStorage dashboardLanguage`. Sorting uses a header click toggling asc/desc arrow; pagination uses `10/25/50` rows with Previous/Next; filters are combined via search `datalist` (10 suggestions), selects and active chips with `Clear all`; charts are clickable filters.
- **Documentation conventions:** `README.md` is the feature and API reference with tables for endpoints, structure diagram, install/run instructions in both `run.sh` and manual `uvicorn` forms. `ARCHITECTURE.md` is the canonical architecture reference for agents.
- **PPTX conventions:** 16:9 (`13.33x7.5`), font `Calibri`, corporate palette (`ACCENT #5560E8`, `LILAC #EEF0FB`, `INK #1E2A3B`), 6-slide structure (Cover → Executive Summary → Distribution → Timeline → Services → Recent Incidents), footer pagination `02 / 06`, language badge `EN/ES`, hairline borders `HAIRLINE #E4E7F0`, row alternation `ROW_ALT #F7F8FC`.
- **Validation and contribution expectations:** No lint, format, type-check, or test harness is configured in the repository. `README.md` notes the absence of Node, Docker and automated tests as a deliberate PoC choice. Tooling for formatting, linting, or CI will be introduced with the hardening roadmap.

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
