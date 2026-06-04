# Handoff Checklist

Use this checklist before project acceptance or live demonstration.

## Required Files

- `README.md`
- `.env.example`
- `requirements.txt`
- `render.yaml`
- `app.py`
- `init_db.py`
- `tourism.db` for local demonstration
- `data/graphs/`, `data/manual/`, `data/indoor/`
- `data/uploads/diaries/`
- `static/food_media/`
- `static/place_media/`
- `static/images/avatars/`
- `docs/数据结构课程设计-2026.pdf`

## Local Startup

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python init_db.py
python app.py
```

Open:

```text
http://127.0.0.1:5000/
```

## Demo Flow

1. Register or log in.
2. Open the home page and confirm the AI assistant launcher appears.
3. Open places and inspect filtering/detail pages.
4. Open route planning and run a route on the XMU manual graph.
5. Open foods and verify cards, filters, detail pages, and favorites.
6. Open diaries and verify feed, detail, comments, ratings, media, and compression controls.
7. Open indoor navigation and verify route planning.
8. Optional: open collector pages only when explaining data collection.

## Optional Environment

Copy `.env.example` to `.env` for local keys. Do not commit real keys.

- `SECRET_KEY`
- `AMAP_JS_KEY`
- `AMAP_SECURITY_JS_CODE`
- `AMAP_WEB_KEY`
- `DEEPSEEK_API_KEY` or `OPENAI_API_KEY`
- `DASHSCOPE_API_KEY` for diary image-to-video generation

## Verification

```powershell
python -m compileall app.py init_db.py tests toursim
python -m pytest -q
git diff --check
```

Expected result:

- Python compilation succeeds.
- Pytest passes.
- `git diff --check` has no errors. LF/CRLF warnings are acceptable on Windows.

## Notes

- `data/raw/` and `data/generated/` are not required for handoff.
- `static/uploads/avatars/` is runtime upload space. Preset avatars are in `static/images/avatars/`.
- Current diary thumbnails use `_thumbs_v3` for higher visible quality.
- Root-level `数据结构课程设计-2026.pdf` is intentionally not used; the retained copy is under `docs/`.
