# Project Structure

TourSim is organized as a Flask single-service project. The repository keeps the code, templates, curated demo data, and deploy files needed for local demonstration and handoff. Runtime logs, temporary browser profiles, generated crawler output, and local database backups are intentionally excluded from the clean delivery tree.

```text
toursim_system/
|-- app.py                         # Flask app entrypoint, DB wiring, remaining route/collector/indoor pages, and blueprint registration
|-- init_db.py                     # SQLite schema initialization
|-- requirements.txt               # Python dependencies
|-- render.yaml                    # Render deployment configuration
|-- README.md                      # Project overview and run guide
|-- .env.example                   # Environment variable template, no real keys
|-- toursim/                       # Extracted helper modules imported by app.py
|   |-- ai_assistant.py            # AI assistant routing, RAG tool orchestration, prompts, and provider calls
|   |-- avatars.py                 # Preset avatar and upload-avatar helpers
|   |-- compression.py             # Diary compression helpers
|   |-- collector_repository.py    # Outdoor collector file storage, source signatures, and manual graph rebuilds
|   |-- diary_media.py             # Diary media paths, thumbnails, blur placeholders, and prewarm
|   |-- diary_repository.py        # Diary CRUD, ratings, comments, compression previews, and stats
|   |-- diary_search.py            # Diary search index, title/content filtering, and sorting
|   |-- diary_video.py             # Diary image-to-video payloads, DashScope calls, and downloads
|   |-- favorites.py               # User favorites, favorite lists, and activity statistics
|   |-- filesystem.py              # JSON and file signature helpers
|   |-- food_repository.py         # Food media payloads, candidate loading, and route-linked foods
|   |-- food_catalog.py            # Food category, scoring, ranking, and display helpers
|   |-- geo.py                     # Distance and polyline helpers
|   |-- indoor.py                  # Indoor route algorithms and collector normalization
|   |-- manual_collector.py        # Outdoor manual collector normalization and ID helpers
|   |-- pagination.py              # Pagination helpers
|   |-- place_repository.py        # Place CSV loading and place cover persistence
|   |-- places.py                  # Place filtering, matching, related-content, and recommendations
|   |-- routes/                    # Flask blueprints extracted from app.py
|   |   |-- assistant.py           # AI assistant API routes
|   |   |-- auth.py                # Login, registration, home, profile, and public user pages
|   |   |-- diaries.py             # Diary feed, search, detail, edit, favorite, comment, and video routes
|   |   |-- diary_media.py         # Diary media and generated-video file routes
|   |   |-- facilities.py          # Facility filter compatibility redirect route
|   |   |-- foods.py               # Food list, detail, and favorite routes
|   |   `-- places.py              # Places list, detail, cover upload, and recommend redirect routes
|   |-- route_algorithms.py        # Dijkstra, multi-target planning, and route serialization
|   |-- route_repository.py        # Route graph paths, cache, loading, and map serialization
|   |-- search.py                  # Shared search text normalization
|   `-- user_accounts.py           # User lookup, account updates, password checks, and avatar URLs
|
|-- data/
|   |-- places.csv                 # Curated scenic/campus place data
|   |-- facilities.csv             # Curated facility data
|   |-- graphs/                    # Delivery route graph data
|   |-- manual/                    # Manual route/facility/food collector source data
|   |-- indoor/                    # Indoor navigation collector data
|   `-- uploads/                   # Demo diary media and current generated thumbnails kept for presentation
|
|-- templates/                     # Jinja page templates
|-- static/
|   |-- images/                    # Shared images and preset avatars
|   |-- place_media/               # Scenic place media
|   |-- food_media/                # Demo food media kept for presentation
|   |-- videos/                    # Login hero HLS demo video
|   |-- vendor/                    # Vendored browser library assets
|   |-- *.css                      # Page and feature styles
|   `-- *.js                       # Page and feature interactions
|
|-- scripts/
|   |-- data/                      # Optional data crawling, expansion, and demo seeding scripts
|   `-- share/                     # Temporary local sharing scripts
|
|-- docs/
|   |-- deployment/                # Deployment notes
|   |-- research/                  # Research notes
|   |-- project_structure.md       # This file
|   |-- technical_design.md        # Consolidated module, data pipeline, and recommendation notes
|   |-- acceptance_checklist.md    # Local acceptance smoke-test checklist
|   |-- handoff_checklist.md       # Handoff verification checklist
|   |-- course design PDF          # Original course-design requirement file
|   |-- midterm report docx        # Midterm project report
|   `-- referenced_diary_media_paths.txt # Reference diary media list
|
`-- tests/                         # Pytest regression tests
```

## Runtime And Generated Files

The following paths are not required in the clean handoff and are ignored by Git:

- `.env`: local secrets and API keys.
- `tourism.db`: local SQLite runtime database.
- `output/`, `tmp/`, `.pytest_cache/`, `.playwright-cli/`, `__pycache__/`: logs, screenshots, browser profiles, and verification artifacts.
- `data/raw/` and `data/generated/`: crawler and intermediate candidate outputs. Scripts can recreate them when needed.
- `static/uploads/`: runtime upload area. Preset avatars now live in `static/images/avatars/`.
- `data/uploads/diaries/*/_thumbs/`, `_thumbs_v2/`, and `_thumbs_v3/`: old diary thumbnail generations. Current thumbnails use `_thumbs_v4`.

The following paths are retained as source handoff support, but are not needed at runtime:

- `scripts/data/`: Python data maintenance scripts (`fetch_places.py`, `expand_demo_places.py`, `seed_demo_diaries.py`) plus `place_seeds.csv`. These are useful for rebuilding or extending demo data.
- `docs/research/`: historical research notes kept for traceability.

## Current Structure Notes

- `app.py` is now smaller but still a meaningful maintainability risk because it contains route planning pages, collector API routes, indoor collector wiring, and DB bootstrapping in one file. The extraction waves moved avatars, user accounts, favorites, filesystem helpers, pagination, diary compression, diary repository/media/video helpers, diary page routes, AI assistant orchestration, search helpers, place matching, place repository/media persistence, diary search, route graph loading, route algorithms, indoor route logic, food repository/ranking helpers, collector normalization, collector repository/graph rebuild logic, and multiple Blueprint route groups into `toursim/`.
- `static/style.css` is also large and layered from several UI iterations. Future cleanup should split it by page or feature while preserving template links.
- Large JSON files under `data/graphs/`, `data/manual/`, and `data/indoor/` are business data rather than source code; do not split or delete them unless the route graph workflow changes.
