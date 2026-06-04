# Acceptance Checklist

This project should be verified with a local test account before handoff. Do not
commit real passwords or private API keys into the repository.

## Local Environment

- Create a local `.env` from `.env.example`.
- Initialize or verify `tourism.db`.
- Confirm diary uploads under `data/uploads/diaries/` are readable.
- Confirm preset avatars under `static/images/avatars/` are readable.
- Confirm food media under `static/food_media/` is available.

## Smoke Test Pages

- Login and register pages.
- Home dashboard.
- Places list and place detail.
- Route planner and route collector.
- Indoor navigation and indoor collector.
- Food list and food detail.
- Diary feed, diary search, diary detail, comments, ratings, favorites, and
  diary media preview.
- AI assistant launcher and chat endpoint.

## Commands

```powershell
python -m compileall app.py init_db.py toursim
python -m pytest -q
python app.py
```
