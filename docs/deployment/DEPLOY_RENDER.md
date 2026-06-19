# Render deployment

This project is ready to deploy on Render and get a stable public URL like:

`https://your-service-name.onrender.com`

## Fastest path

1. Push this project to a GitHub repository.
2. Sign in to [Render](https://render.com/).
3. Create a new Web Service from that GitHub repo.
4. Render will detect `render.yaml` and use the included settings.
5. After the first deploy finishes, open the generated `onrender.com` URL.

Before pushing, run the local verification commands in
`docs/acceptance_checklist.md` and make sure `.env`, `tourism.db`, caches, and
local screenshots are not staged.

## Persistent data on Render

This project now uses a Render persistent disk in `render.yaml`:

- Disk name: `toursim-data`
- Mount path: `/var/data`
- SQLite path: `/var/data/tourism.db`
- Runtime upload path: `/var/data/uploads`

On first boot, if `/var/data/tourism.db` does not exist, the app copies the repository `tourism.db` into the disk. It also seeds missing diary media and generated videos from `data/uploads/` into `/var/data/uploads` without overwriting files that already exist on the disk.

Render persistent disks require a paid instance type. If the service remains on a free plan, user password changes, diary edits, comments, generated videos, and uploaded media can still be lost on restart or redeploy.

For a larger production deployment, move the app from SQLite to a hosted database such as PostgreSQL.

## Environment values already supported

- `SECRET_KEY`: Flask session key for production.
- `PORT`: injected by Render automatically.
- `DATA_DIR`: directory where `tourism.db` is stored. Render uses `/var/data`.
- `DB_NAME`: optional database filename or absolute path. Render uses `tourism.db`.
- `UPLOAD_DATA_DIR`: directory where runtime diary uploads and generated videos are stored. Render uses `/var/data/uploads`.
- `AMAP_JS_KEY`, `AMAP_SECURITY_JS_CODE`, `AMAP_WEB_KEY`: map keys for route collection and display.
- `DEEPSEEK_API_KEY` or `OPENAI_API_KEY`: optional model provider key for the AI assistant.
- `DASHSCOPE_API_KEY`: optional key for diary image-to-video generation.
