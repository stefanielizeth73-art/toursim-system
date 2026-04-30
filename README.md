# TourSim System

A Flask-based tourism simulation and recommendation system with scenic spots, food discovery, route planning, facilities lookup, and travel diaries.

## Features

- User registration and login
- Scenic spot browsing and detail pages
- Food browsing and recommendations
- Route planning
- Facilities lookup
- Travel diary publishing and rating

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

Open `http://127.0.0.1:5000`.

## Data and graph workflow

The course project is developed in the same order as the PPT requirements:
recommendation data first, then route graphs, facilities, diaries, and food.

Fetch candidate place data:

```powershell
python scripts/data/fetch_places.py --limit 20
```

Build a candidate internal graph and facility table from OpenStreetMap:

```powershell
python scripts/data/build_osm_graph.py --place "北京邮电大学沙河校区, 北京, 中国" --max-edges 300
```

Generated files are written under `data/generated/` and raw API responses under
`data/raw/`. Review generated data before merging it into `data/places.csv`,
`data/route_graph.json`, or `data/facilities.csv`.

More details are in:

- `docs/project_structure.md`
- `docs/module_sequence.md`
- `docs/data_and_graph_pipeline.md`

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

Because this repository is private, Render deployment works only after you connect the same GitHub account or grant Render access to this repo.

## Production notes

- `SECRET_KEY` is read from environment variables in production.
- The app can store SQLite data under `DATA_DIR`.
- Render free web services provide a stable URL, but their filesystem is not persistent by default.
- If you want user and diary data to survive restarts and redeploys, use a persistent disk or move to PostgreSQL.

More deployment details are in [DEPLOY_RENDER.md](./docs/deployment/DEPLOY_RENDER.md).
