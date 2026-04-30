# Render deployment

This project is ready to deploy on Render and get a stable public URL like:

`https://your-service-name.onrender.com`

## Fastest path

1. Push this project to a GitHub repository.
2. Sign in to [Render](https://render.com/).
3. Create a new Web Service from that GitHub repo.
4. Render will detect `render.yaml` and use the included settings.
5. After the first deploy finishes, open the generated `onrender.com` URL.

## Important note about data

The URL is stable, but the default free web service filesystem is not persistent.

This app stores users and diaries in SQLite, so if you want server-side data to survive redeploys and restarts, do one of these:

- Attach a persistent disk on a paid Render plan and set `DATA_DIR` to the disk mount path.
- Move the app from SQLite to a hosted database such as PostgreSQL.

## Environment values already supported

- `SECRET_KEY`: Flask session key for production.
- `PORT`: injected by Render automatically.
- `DATA_DIR`: directory where `tourism.db` is stored.
- `DB_NAME`: optional database filename or absolute path.
