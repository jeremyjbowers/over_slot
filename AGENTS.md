# Agent notes for over_slot

Learnings for AI agents working in this repo. Verified July 2026.

## Project layout

- Django site lives in `overslot/` (app) + `config/` (settings packages: `config.dev.settings`, `config.prod.settings`). **There is no `manage.py`** — use `django-admin <command>` with the env activated.
- Activate the environment with `workon overslot` (virtualenvwrapper, only available in a login shell: `zsh -lic '...'`). The actual venv is `.venv/` in the repo root, so `.venv/bin/python` with `DJANGO_SETTINGS_MODULE=config.dev.settings` works too.
- Local dev server: `django-admin runserver` on port 8000, sometimes exposed via ngrok. The dev server typically runs with `VALKEY_URL=valkey://localhost:6379` set (check `ps eww <pid>`).

## Mock draft simulator — build pipeline (important)

The simulator page (`/my-mock-draft/`, template `overslot/templates/mock_draft_sim.html`) does **not** use Django static files. Everything is inlined:

- Sources of truth: `draftboard/js/draft.js`, `draftboard/css/draft.css`, CSVs in `draftboard/data/`.
- `node draftboard/build-data.js` (run from repo root) generates `draftboard/js/data.js` and inlines CSS + data + JS into the template between `{# BEGIN mock-draft-css #}` / `{# BEGIN mock-draft-data #}` / `{# BEGIN mock-draft-js #}` marker comments.
- **Never hand-edit the inlined blocks in `mock_draft_sim.html`** — edit `draftboard/js|css` and re-run the build script.
- `draftboard/index.html` is a standalone harness for the same JS/CSS (serves via any static server), but the production page wraps the sim in site chrome (`.mock-draft-viewport`, fixed 3.5rem nav) with different scroll constraints — verify layout bugs against the Django page, not just the standalone harness.

## Caching — the classic trap

`GET /my-mock-draft/` is cached as a **whole HTML string in Valkey** (key `overslot:my_mock_draft:html:v12`, see `KEY_MY_MOCK_DRAFT_HTML` in `overslot/cache_utils.py`, 1-hour timeout). This applies **in local dev too** whenever `VALKEY_URL` is set, so template/CSS/JS changes silently don't appear even after the build script + server reload. Multiple past commits ("still trying to overcome cache") were fighting this.

- Bust locally:

  ```bash
  VALKEY_URL=valkey://localhost:6379 DJANGO_SETTINGS_MODULE=config.dev.settings \
    .venv/bin/python -c "import django; django.setup(); from django.core.cache import cache; \
    from overslot.cache_utils import KEY_MY_MOCK_DRAFT_HTML; print(cache.delete(KEY_MY_MOCK_DRAFT_HTML))"
  ```

- In prod/admin there is a cache dashboard (`overslot/cache_admin_views.py`) that can clear the same key. Always clear it after deploying sim changes.
- Share URLs (`/my-mock-draft/s/…`, `/my-mock-draft/<uuid>/`) are `never_cache`d — only the landing page is cached.
- Before concluding a fix "didn't work", `curl` the page and grep for a string unique to your change.

## Verifying sim behavior headlessly

Playwright (chromium) works well against the local dev server:

1. `goto http://localhost:8000/my-mock-draft/`
2. `click #btn-start` (no teams selected is fine), then `click #btn-simulate-rest`
3. `waitForFunction` for `#draft` to have class `draft-finished`
4. Probe computed styles / `scrollTop`, use `mouse.wheel()` to test real scroll behavior (programmatic `scrollTop` can succeed while wheel input is broken — test both).

## Endgame scroll architecture (do not regress)

After the draft finishes (`#draft.draft-finished`), the design is **one vertical scroller: `#draft`**. The endgame summary (`#draft-complete`) and the full board (`#draft-body`/`#board`) sit inside it at natural height (`flex: 0 0 auto`, overflow visible).

Two CSS gotchas that caused the long-standing "can't scroll the pick list" bug (fixed July 2026):

1. **Overflow pairing:** `overflow-x: hidden` combined with `overflow-y: visible` makes the browser recompute `overflow-y` to `auto`. You cannot make an element a scroll container on one axis only with `visible` on the other. If a child of `#draft` must not trap scrolling, set `overflow: visible` on **both axes** (horizontal bleed is clipped by `#draft` itself, which keeps `overflow-x: hidden`).
2. **Wheel-event swallowing:** several elements (`#board`, `#draft-complete-inner`, etc.) get `overscroll-behavior-y: contain` for mobile. A scroll container with `contain` **swallows wheel/touch events instead of chaining to the parent scroller, even when it has nothing to scroll**. So an accidental scroll container (per gotcha 1) covering the page makes wheel scrolling dead everywhere while scrollbar-dragging and JS `scrollTop` still work.

During an active draft, `#board` is a legitimate internal scroller (`flex-1 overflow-y-auto`) — the overrides above apply only in the `.draft-finished` state.
