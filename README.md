# TourSim System

A Flask-based tourism simulation and recommendation system with scenic spots, food discovery, route planning, facilities lookup, and travel diaries.

## Features

- User registration and login
- Scenic spot browsing and detail pages
- Food browsing and recommendations
- Route planning
- Facilities lookup
- Travel diary publishing and rating
- Indoor navigation
- Floating AI travel assistant

## Local development

### Requirements

- Python 3.13

### Run locally

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`. If `FLASK_PORT` or `PORT` is set in `.env`,
use that port instead.

## Data and graph workflow

The course project is developed in the same order as the PPT requirements:
recommendation data first, then route graphs, facilities, diaries, and food.

Fetch candidate place data:

```powershell
python scripts/data/fetch_places.py --limit 20
```

For the XMU Xiang'an route module, Gaode/AMap is used only as the map canvas
for manual POI and road collection. Copy `.env.example` to `.env` and set
your local keys there:

```powershell
AMAP_JS_KEY=your_js_key
AMAP_SECURITY_JS_CODE=your_js_security_code
AMAP_WEB_KEY=your_web_key
```

### AI assistant

TourSim includes a floating AI travel assistant on the main logged-in pages.
It combines the existing local data and functions for places, campus food,
outdoor routes, facilities, indoor navigation, and travel diaries.

The assistant works in two modes:

- Local mode: if the selected provider key is empty, it still returns structured
  recommendations from the project's local data.
- Model mode: set the provider key in `.env`; the Flask server calls the model
  from the backend only, so the key is never rendered into browser HTML or JS.

Default DeepSeek V4 Pro 1M context `.env` values:

```powershell
AI_ASSISTANT_ENABLED=1
AI_PROVIDER=deepseek
AI_MODEL=deepseek-v4-pro
AI_REASONING_MODEL=deepseek-v4-pro
AI_BASE_URL=https://api.deepseek.com
AI_ROUTER_MODE=fast
AI_THINKING=disabled
AI_REASONING_EFFORT=low
DEEPSEEK_API_KEY=your_deepseek_api_key
```

To switch back to OpenAI, set `AI_PROVIDER=openai`, choose an OpenAI model, and
set `OPENAI_API_KEY`.

Open the collector:

```text
http://127.0.0.1:5000/route?collect=1
```

Click POIs and draw roads on the map. The backend saves collector files under
`data/manual/` and rebuilds `data/graphs/xmu_manual.json` automatically. The
route page defaults to this manual graph, and Dijkstra runs on the local
`nodes/edges` data. If your local server runs on another port, replace `5000`.

More details are in:

- `docs/project_structure.md`
- `docs/technical_design.md`
- `docs/acceptance_checklist.md`
- `docs/handoff_checklist.md`
- `docs/deployment/DEPLOY_RENDER.md`

## Project layout

```text
app.py                 Flask app entrypoint, DB wiring, remaining route/collector/indoor pages, and blueprint registration
init_db.py             SQLite schema initialization
toursim/               Extracted modules for AI assistant orchestration, blueprints, user/favorites, place/collector repositories, diary repository/media/video/routes, route graph loading/algorithms, food repository/ranking, indoor logic, search, avatars, compression, and file utilities
templates/             Jinja pages
static/                CSS, JavaScript, images, videos, and demo media
data/                  Curated CSV data, route graphs, collector data, indoor data, and diary media
scripts/               Optional data maintenance and sharing utilities
docs/                  Structure, deployment, technical design, acceptance, and handoff notes
tests/                 Pytest regression tests
```

`data/raw/` and `data/generated/` are optional crawler/intermediate outputs and
are not required for a clean handoff. They can be recreated by the data scripts
when needed.

`scripts/data/` contains optional Python data maintenance scripts for fetching
or expanding place data and reseeding demo diaries. They are not needed at
runtime, but are kept because the docs reference them for data regeneration.

## Verification

```powershell
python -m compileall app.py init_db.py toursim tests
python -m pytest -q
git diff --check
```

Before final submission, also open the main pages listed in
`docs/acceptance_checklist.md`.

## Share temporarily from your own computer

```powershell
.\scripts\share\share_project.bat
```

This creates a temporary public link while your computer stays online.

## Deploy to Render

This repo includes [render.yaml](./render.yaml), so it is ready for Render deployment.

### Standard deploy

1. Push this repo to GitHub.
2. In Render, create a new Web Service from the GitHub repo.
3. Render will read `render.yaml` automatically.
4. After deployment, you will get a stable URL like `https://your-service-name.onrender.com`.

### One-click deploy

This repo is now hosted at:

`https://github.com/stefanielizeth73-art/toursim-system`

You can open Render's deploy flow with:

```text
https://render.com/deploy?repo=https://github.com/stefanielizeth73-art/toursim-system
```

Render deployment works only after you connect the same GitHub account or grant Render access to the repo.

## Production notes

- `SECRET_KEY` is read from environment variables in production.
- The app can store SQLite data under `DATA_DIR`.
- Render free web services provide a stable URL, but their filesystem is not persistent by default.
- If you want user and diary data to survive restarts and redeploys, use a persistent disk or move to PostgreSQL.

More deployment details are in [DEPLOY_RENDER.md](./docs/deployment/DEPLOY_RENDER.md).
