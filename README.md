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

## Share temporarily from your own computer

```powershell
.\share_project.bat
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

After this project is pushed to GitHub, you can use this URL pattern:

```text
https://render.com/deploy?repo=<YOUR_GITHUB_REPO_URL>
```

Replace `<YOUR_GITHUB_REPO_URL>` with your public GitHub repository URL.

## Production notes

- `SECRET_KEY` is read from environment variables in production.
- The app can store SQLite data under `DATA_DIR`.
- Render free web services provide a stable URL, but their filesystem is not persistent by default.
- If you want user and diary data to survive restarts and redeploys, use a persistent disk or move to PostgreSQL.

More deployment details are in [DEPLOY_RENDER.md](./DEPLOY_RENDER.md).
