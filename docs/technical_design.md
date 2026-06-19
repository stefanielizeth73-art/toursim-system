# Technical Design

This document summarizes the current delivery architecture for TourSim. It is
intended for acceptance, handoff, and future maintenance.

## System Overview

TourSim is a Flask single-service application for a personalized tourism system.
It supports user accounts, scenic/campus places, food discovery, outdoor route
planning, indoor navigation, travel diaries, favorites, ratings, comments, media
preview, and a floating AI assistant.

The project is structured around one Flask entrypoint plus extracted helper
modules:

- `app.py`: Flask app creation, database bootstrapping, global configuration,
  dependency wiring, and the remaining route/collector/indoor page routes.
- `toursim/`: extracted business logic, repositories, algorithms, file helpers,
  and Blueprint route modules.
- `templates/`: Jinja pages.
- `static/`: page CSS, JavaScript, images, videos, preset avatars, route assets,
  and demo media.
- `data/`: curated CSV data, graph JSON, manual collector data, indoor data, and
  diary media used for local demonstration.

## Main Workflows

### User And Profile

Users register and log in through Flask sessions. Profile pages show user
activity, favorites, diaries, comments, and avatar state. Preset avatars are
stored in `static/images/avatars/`; runtime avatar uploads are not required for
the final handoff.

Relevant modules:

- `toursim/user_accounts.py`
- `toursim/avatars.py`
- `toursim/favorites.py`
- `toursim/routes/auth.py`

### Places And Recommendations

Places are loaded from `data/places.csv`. The place module supports keyword
search, tag search, type/city filtering, sorting, and Top-K recommendation.

The recommendation logic uses a score based on rating, popularity, and matched
interest tags. The implementation keeps only the best K candidates instead of
fully sorting the entire dataset, which matches the course-design requirement
for efficient Top-K selection.

Relevant modules:

- `toursim/places.py`
- `toursim/place_repository.py`
- `toursim/routes/places.py`
- `scripts/data/expand_demo_places.py`
- `scripts/data/fetch_places.py`

### Outdoor Route Planning

The route page defaults to the manual XMU graph in
`data/graphs/xmu_manual.json`. The source collector files live under
`data/manual/`. The app uses local graph data for routing and renders the map
with Gaode/AMap as the browser map canvas.

Route planning uses Dijkstra-style shortest path logic and supports map
serialization for the browser. Collector routes can create, delete, restore, and
rebuild POIs, facilities, edges, snap links, and road points.

Relevant modules:

- `toursim/route_algorithms.py`
- `toursim/route_repository.py`
- `toursim/manual_collector.py`
- `toursim/collector_repository.py`
- `static/route_map.js`
- `templates/route.html`
- `templates/route_collector.html`

### Indoor Navigation

Indoor navigation uses `data/indoor/manual_collector.json` as its source data.
The indoor module builds a floor-aware graph and supports indoor path planning,
vertical transitions, and collector editing.

Relevant modules:

- `toursim/indoor.py`
- `templates/indoor.html`
- `templates/indoor_collector.html`
- `static/indoor.css`
- `static/indoor_collector.js`

### Food Discovery

Food entries are built from curated food media and route-linked facilities. The
food page supports campus context, keyword/category filtering, detail pages,
favorites, and route handoff from food detail to route planning.

Relevant modules:

- `toursim/food_catalog.py`
- `toursim/food_repository.py`
- `toursim/routes/foods.py`
- `static/food_media/`

### Diaries, Media, And Video

Diary data is stored in SQLite. Diary media is stored under
`data/uploads/diaries/`. The current generated thumbnail version is
`_thumbs_v4`; older thumbnail generations are cleanup artifacts and are ignored.

Diary features include feed, search, detail page, comments, ratings, favorites,
compression preview, media preview, and optional image-to-video generation via
DashScope when `DASHSCOPE_API_KEY` is configured.

Relevant modules:

- `toursim/diary_repository.py`
- `toursim/diary_search.py`
- `toursim/diary_media.py`
- `toursim/diary_video.py`
- `toursim/routes/diaries.py`
- `toursim/routes/diary_media.py`

### AI Assistant

The AI assistant is exposed through `/api/assistant/chat` and
`/api/assistant/history`. It can run in local mode without an external model key
or model mode with a configured provider key. Model keys stay on the Flask
backend and are never rendered into browser HTML or JavaScript.

Relevant modules:

- `toursim/ai_assistant.py`
- `toursim/routes/assistant.py`
- `static/ai_assistant.js`
- `static/ai_assistant.css`

## Data Layout

Important delivery data:

- `data/places.csv`: curated place data.
- `data/facilities.csv`: curated facility data.
- `data/graphs/xmu_manual.json`: current outdoor route graph.
- `data/manual/xmu_collector_*.json`: manual collector source data.
- `data/indoor/manual_collector.json`: indoor collector source data.
- `data/uploads/diaries/`: demo diary media and current generated thumbnails.
- `static/food_media/`: food demo media.
- `static/place_media/`: place demo media.

Optional regeneration/support data:

- `scripts/data/`: data-fetching, expansion, and demo seeding scripts.
- `data/raw/` and `data/generated/`: crawler/intermediate output. These are not
  required for the clean handoff and may be recreated by scripts when needed.

## Configuration

Use `.env.example` as the template. Real `.env` values must remain local and
must not be committed.

Common optional keys:

- `SECRET_KEY`
- `AMAP_JS_KEY`
- `AMAP_SECURITY_JS_CODE`
- `AMAP_WEB_KEY`
- `DEEPSEEK_API_KEY` or `OPENAI_API_KEY`
- `DASHSCOPE_API_KEY`

## Verification

Recommended final checks:

```powershell
python -m compileall app.py init_db.py toursim tests
python -m pytest -q
git diff --check
git status --short
```

After running tests, remove regenerated `__pycache__/` and `.pytest_cache/`
directories before committing.

## Known Structure Debt

The project is suitable for acceptance, but these areas are still candidates for
future cleanup:

- `app.py` still contains route planning, collector API, indoor collector, and
  database bootstrapping.
- `static/style.css` is large and layered from multiple UI iterations.
- `static/route_map.js` contains route rendering and collector editing logic in
  one file.

These should be refactored only after the final acceptance version is frozen,
because route and collector behavior is high impact.
