# AI Test Finance — Incidents Dashboard

> PoC de dashboard de monitorización de incidencias en producción para el ecosistema Inditex. Visualiza, filtra y exporta incidencias de servicios críticos con KPIs, timeline y health checks en tiempo real.

[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-009688.svg)](https://fastapi.tiangolo.com/)
[![Uvicorn](https://img.shields.io/badge/Uvicorn-standard-499848.svg)](https://www.uvicorn.org/)
[![License: PoC](https://img.shields.io/badge/license-PoC-lightgrey.svg)](#licencia)

---

## Índice

- [Descripción](#descripción)
- [Stack Tecnológico](#stack-tecnológico)
- [Estructura del Proyecto](#estructura-del-proyecto)
- [Requisitos](#requisitos)
- [Instalación](#instalación)
- [Ejecución](#ejecución)
- [Endpoints API](#endpoints-api)
- [Frontend](#frontend)
- [Datos y Seed](#datos-y-seed)
- [Exportación](#exportación)
- [Internacionalización](#internacionalización)
- [Arquitectura](#arquitectura)
- [Limitaciones y Roadmap](#limitaciones-y-roadmap)
- [Licencia](#licencia)

---

## Descripción

**AI Test Finance / Incidents Dashboard** es una aplicación full-stack ligera que centraliza la monitorización de incidencias de servicios del grupo Inditex:

- **8 servicios simulados:** `IOP-Gateway`, `SINT-Inventory`, `RFID-Tracking`, `Zara-API`, `MassimoDutti-BFF`, `Bershka-Web`, `Oysho-Mobile`, `Stradivarius-Checkout`.
- **120 incidencias sintéticas** con severidad (`critical`, `high`, `medium`, `low`), estado (`open`, `in_progress`, `resolved`), timestamps y métricas de resolución.
- **Dashboard interactivo** con KPIs, línea temporal, distribución por severidad/servicio, tabla filtrable y panel de salud de servicios.
- **Exports ejecutivos:** Excel (cliente) y PowerPoint de 6 slides (servidor) con branding corporativo Inditex, bilingüe EN/ES.

Todo corre en un único proceso **FastAPI + Uvicorn** que sirve tanto la API REST como el frontend estático. Persistencia file-based (`data.json`) — ideal para demos y PoCs sin infraestructura adicional.

---

## Stack Tecnológico

| Capa | Tecnología | Detalle |
|------|------------|---------|
| **Lenguaje** | Python 3.13 | Probado con `cpython-3.13`; compatible 3.10+ |
| **Backend** | FastAPI `>=0.104.0` | Validación con Pydantic `BaseModel` |
| **Servidor ASGI** | Uvicorn `[standard]` `>=0.24.0` | |
| **Generación Office** | python-pptx `>=0.6.21` | PPTX 16:9 corporativo |
| **Persistencia** | `data.json` | File-based, sin BD |
| **Frontend** | HTML5 + CSS3 + Vanilla JS | Sin framework, sin build |
| **Gráficos** | Chart.js `4.4.1` | CDN `jsdelivr.net` |
| **Excel** | SheetJS `xlsx 0.18.5` | Export 100% cliente |
| **Estilos** | CSS Variables + Google Fonts `Carlito` (fallback Calibri) | Responsive 1440px max-width |
| **i18n** | Diccionario JS + parámetro `lang` en PPTX | `en` / `es` |
| **Infra** | Bash `run.sh`, CORS `*`, `StaticFiles` | |

> **Sin dependencias Node, sin Docker, sin tests automatizados** — PoC deliberadamente minimalista.

---

## Estructura del Proyecto

```
aitestfinance/
├── README.md                      # ← este fichero
├── AGENTS.md                      # reglas del runtime AI Context
├── incidents-dashboard/
│   ├── run.sh                     # bootstrap + arranque Uvicorn
│   ├── backend/
│   │   ├── main.py                # FastAPI app (799 líneas, 8 endpoints)
│   │   ├── seed.py                # generador determinista de datos
│   │   ├── data.json              # 120 incidencias + 8 servicios (generado)
│   │   ├── requirements.txt       # fastapi, uvicorn, python-pptx
│   │   └── __pycache__/
│   └── frontend/
│       └── index.html             # SPA single-file (1614 líneas)
└── .aicontext/                    # configuración resuelta (no versionado)
```

---

## Requisitos

- **Python** 3.10+ (recomendado 3.13) + `pip`
- **Bash** (macOS / Linux) para `run.sh` — en Windows usar `python -m uvicorn ...` manual
- **Puerto 8000** libre
- **Navegador moderno** con acceso a internet (Chart.js y SheetJS vía CDN)
- ~10 MB de disco

---

## Instalación

```bash
# 1. Clonar
git clone <repo-url> aitestfinance
cd aitestfinance

# 2. (Opcional) Crear entorno virtual
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. Instalar dependencias
pip install -r incidents-dashboard/backend/requirements.txt
# fastapi>=0.104.0
# uvicorn[standard]>=0.24.0
# python-pptx>=0.6.21
```

---

## Ejecución

### Opción A — Script automatizado (recomendado)

```bash
chmod +x incidents-dashboard/run.sh
./incidents-dashboard/run.sh
```

El script:
1. Genera `backend/data.json` con `seed.py` si no existe (`seed=42`, reproducible).
2. Imprime banner con URLs.
3. Lanza `uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info`.

### Opción B — Manual

```bash
cd incidents-dashboard/backend
pip install -r requirements.txt
python3 seed.py                          # regenera data.json
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
# o sin reload:
uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info
```

### URLs

| Recurso | URL |
|---------|-----|
| **Dashboard** | http://localhost:8000/ → redirige a http://localhost:8000/dashboard/ |
| **API Stats** | http://localhost:8000/api/stats |
| **Swagger Docs** | http://localhost:8000/docs |
| **ReDoc** | http://localhost:8000/redoc |
| **OpenAPI JSON** | http://localhost:8000/openapi.json |

### Reset de datos

```bash
# vía API
curl -X POST http://localhost:8000/api/reset

# o borrando el fichero
rm incidents-dashboard/backend/data.json
./incidents-dashboard/run.sh
```

---

## Endpoints API

`backend/main.py` — `FastAPI(title="Inditex Incidents Dashboard API", version="1.0.0")`, CORS abierto.

| Método | Ruta | Parámetros | Descripción | Respuesta |
|--------|------|------------|-------------|-----------|
| `GET` | `/api/stats` | — | KPIs globales | `{total_incidents, open_incidents, resolved_incidents, critical_open, mttr_minutes, by_severity, by_status}` — MTTR = media en minutos `resolved_at - created_at` |
| `GET` | `/api/incidents` | `status?`, `severity?`, `service?`, `limit=50`, `offset=0` | Listado filtrable, paginado, orden `created_at desc` | `{total, offset, limit, incidents[]}` |
| `GET` | `/api/incidents/timeline` | `days=14` | Buckets por día últimos N días | `[{date, total, critical, high, medium, low, resolved}]` asc |
| `GET` | `/api/services` | — | Servicios con `active_incidents` (open/in_progress) | `[{name, description, status, last_checked, uptime_7d, active_incidents}]` |
| `PUT` | `/api/incidents/{id}/resolve` | `id` path | Marca `resolved` + `resolved_at=now()` | `{ok, incident}` o `404` |
| `POST` | `/api/incidents` | JSON `{title, service, severity, description?}` | Crea incidencia `status=open`, `id=max+1` | objeto incidencia |
| `POST` | `/api/reset` | — | Ejecuta `seed.main()` | `{ok, message}` |
| `GET` | `/api/export/pptx` | `status?`, `severity?`, `service?`, `q?`, `days?`, `lang?` | Exporta PPTX filtrado + i18n. `q` busca en `id/title/service/description`, `days` ancla a última incidencia | `StreamingResponse` `application/vnd...presentationml.presentation` |
| `GET` | `/` | — | Redirect → `/dashboard/` | 307 |
| `GET` | `/dashboard/*` | — | Frontend estático | `index.html` |

> **Notas:** Sin autenticación, sin paginación por cursor, `save_data()` no thread-safe (PoC). Todos los filtros del PPTX son combinables.

**Ejemplo rápido:**

```bash
curl http://localhost:8000/api/stats | jq
curl "http://localhost:8000/api/incidents?severity=critical&limit=5" | jq
curl -X PUT http://localhost:8000/api/incidents/1/resolve | jq
curl -X POST http://localhost:8000/api/incidents \
  -H "Content-Type: application/json" \
  -d '{"title":"Checkout timeout","service":"Stradivarius-Checkout","severity":"high"}' | jq
```

---

## Frontend

`frontend/index.html` — SPA single-file (~1614 líneas) sin build, vanilla JS.

### Paleta

- `accent #5560E8`, `ink #1E2A3B`, `lilac #EEF0FB`
- Severidades: `critical #E13D5B`, `high #E87A3D`, `medium #E0B03D`, `low #3DA86E`

### Layout

- **Header sticky 64px:** marca `INDITEX | Incident Dashboard`, selector idioma (banderas SVG EN/ES), reloj live (actualizado cada 30s, `en-GB`/`es-ES`), botón Refresh + toast.
- **KPIs (grid 4):** Total Incidents · Open · MTTR (min) · Critical Open — con barra `accent` y hover.
- **Gráficos (grid 2fr 1fr 1fr):**
  - Timeline (línea, últimos 14 días, 4 datasets por severidad; leyenda clickeable → filtra severidad)
  - Doughnut By Severity (cutout 68%, slice clickeable)
  - Horizontal Bar By Service (barra clickeable)
- **Sección Incidents:** búsqueda con `datalist` (10 sugerencias), selects `severity/status/service`, chips activos con `×`, botones Apply / Excel / PPTX.
- **Tabla:** 7 columnas `ID / Title / Service / Severity / Status / Created / Action` — sortable (flecha asc/desc), paginada (`10/25/50` rows, Previous/Next, `first-last of total`), acción `Resolve`.
- **Services Health:** grid 4 columnas, `status-dot` (healthy/degraded/down) + `98.x% uptime — N active`.

### Lógica clave

- `API = ''` (mismo origen), `TIMELINE_WINDOW_DAYS = 14`
- `LANGUAGES` con 60+ claves `en/es`, `t(key, vars)`, `localStorage dashboardLanguage`
- `refreshAll()` → `Promise.all([/api/incidents?limit=500, /api/services])` + `applyFilters()`
- Filtrado **local** (no re-fetch) para tabla/charts; timeline anclado a última incidencia para que demos con datos antiguos sigan mostrando datos.
- `exportPptx()` construye `URLSearchParams` con filtros + `days` + `lang` y dispara descarga `<a>`.
- `exportExcel()` filtra local, ventana 14d, `XLSX.utils.json_to_sheet`, headers traducidos, `XLSX.writeFile(indidents_<date>.xlsx)`.
- `resolveIncident(id)` → `PUT /resolve` + toast + refresh.

### Interactividad

Filtros combinables (`search + severity + status + service`), chips `Clear all`, charts como filtros, paginación, ordenación, refresh, y export en un clic.

---

## Datos y Seed

**Generación determinista** (`seed.py`, `random.seed(42)`):

- **120 incidencias** — `created_at` en últimos 20 días (`days 0-20 + horas 0-23 + min 0-59`), `resolved_at` solo si `resolved` con `resolution_hours` según severidad (critical 0.5-4h, high 1-6h, resto 0.5-12h).
- **Distribución:** `critical 8%` · `high 22%` · `medium 40%` · `low 30%`; `open 10%` · `in_progress 15%` · `resolved 75%`.
- **24 plantillas de título** (`High latency on {service} endpoint GET /api/orders`, `5xx errors spiking…`, `Connection pool exhaustion…`) + 8 descripciones con `{time}`, `{percentage}`, `{eta_minutes}`.
- **8 servicios** con descripción + health roll: `>0.97 down` (3%), `>0.85 degraded` (12%), resto `healthy`, `uptime_7d 98.5–100%`.

**Campos:**

- Incidencia: `id, title, service, severity, status, created_at (ISO), resolved_at (ISO|null), description`
- Servicio: `name, description, status, last_checked (ISO), uptime_7d`

El fichero `backend/data.json` es mutable en runtime (`POST /incidents`, `PUT /resolve`, `POST /reset` lo reescriben).

---

## Exportación

### Excel (cliente, SheetJS)

- Filtrado local, ventana 14 días, headers traducidos según idioma seleccionado, `XLSX.writeFile(indidents_<date>.xlsx)`.

### PowerPoint (servidor, python-pptx)

`GET /api/export/pptx?...&lang=en|es` — 6 slides en **16:9** (`13.33"×7.5"`), fuente `Calibri`, paleta corporativa:

1. **Portada** — título, fecha, chips `total / open / services / resolution`, badge idioma.
2. **Resumen Ejecutivo** — 4 KPIs + callout.
3. **Distribución por Severidad** — barras + %.
4. **Timeline** — tabla 10 días con métricas por severidad.
5. **Servicios más afectados** — Top 10 + barras ponderadas.
6. **Detalle Recientes** — 18 últimas incidencias.

Helpers: `_build_pptx`, `_txt`, `_rect`, `_card`, `_cell`, `_add_styled_table`, `_format_date/day`. `Content-Disposition: incidents_dashboard_<timestamp>.pptx`.

---

## Internacionalización

- **Frontend:** diccionario `LANGUAGES` (`en`/`es`), `setLanguage()` persistido en `localStorage`, `applyTranslations()` repinta toda la UI, reloj con `toLocaleString`.
- **Backend PPTX:** query `lang` / `language` (`en` default) traduce títulos, headers y fechas del PowerPoint.

Cambio de idioma instantáneo tanto en dashboard como en exports.

---

## Arquitectura

```
┌─────────────────────────────────────────────┐
│  FastAPI (main.py)  :8000                   │
│  ┌─────────────┐  ┌──────────────────────┐  │
│  │ REST API    │  │ StaticFiles          │  │
│  │ /api/*      │  │ /dashboard → index   │  │
│  │ JSON + PPTX │  │ HTML/CSS/JS + CDN    │  │
│  └──────┬──────┘  └──────────────────────┘  │
│         │ load/save                         │
│  ┌──────▼──────┐  ┌──────────┐              │
│  │ data.json   │◄─┤ seed.py  │              │
│  └─────────────┘  └──────────┘              │
└─────────────────────────────────────────────┘
         ▲
         │ fetch (Chart.js, XLSX, PPTX)
┌────────┴────────┐
│ Browser SPA     │
│ index.html      │
└─────────────────┘
```

- **Monolito ligero PoC:** API + frontend en el mismo proceso, sin BD, sin cola, sin auth.
- **File-based persistence:** simple y reiniciable en 1 comando, no concurrent-safe (no apto para producción multi-instancia).
- **API-first + Static hosting:** despliegue cero-dependencia Node.
- **Filtrado en memoria:** tanto backend (PPTX) como frontend (tabla/charts) filtran en memoria para demos pequeñas/medias.

---

## Limitaciones y Roadmap

**Limitaciones actuales (PoC):**

- Persistencia en `data.json` — sin BD, sin concurrencia, sin migraciones.
- Sin autenticación / autorización / rate limiting.
- Sin tests automatizados, sin linter, sin CI, sin Dockerfile.
- CORS abierto (`allow_origins=["*"]`) — solo para demo.
- CDN externo requerido (Chart.js, SheetJS, Google Fonts).
- `data.json` no debería commitearse si se quiere estado limpio por entorno.

**Roadmap sugerido:**

- [ ] Migrar a PostgreSQL/SQLite + SQLAlchemy + Alembic
- [ ] Añadir auth (JWT / OAuth2) y roles
- [ ] Tests (`pytest`, `httpx`, coverage) + CI (GitHub Actions)
- [ ] Docker + docker-compose + healthchecks
- [ ] Paginación por cursor y búsqueda full-text
- [ ] WebSockets / SSE para updates en vivo
- [ ] Observabilidad (Prometheus, logs estructurados)
- [ ] Export PDF y scheduling de reportes

---

## Licencia

PoC interno — sin licencia pública definida. Uso restringido al ámbito del proyecto **AI Test Finance / Inditex**.

---

<p align="center">
  <sub>Generado para <code>repos/aitestfinance</code> · Dashboard PoC · FastAPI + Vanilla JS · 2026-08-27</sub>
</p>
