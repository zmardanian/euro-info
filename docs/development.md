# Developer guide

## Setup

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-build.txt
.venv/bin/python app.py            # the app
.venv/bin/python -m euroinfo --help
```

`requirements.txt` lists what the app needs at runtime; `requirements-build.txt` pins the exact versions
used for releases plus PyInstaller and ruff.

## Layout

```
euroinfo/
  __init__.py        version (the only place it is written), app name, repository
  __main__.py        command line: GUI, --widget-json, --headlines, --version
  paths.py           XDG folders: config, data, cache, log
  settings.py        the one settings file (QSettings INI) and its 2.x migration
  logs.py            rotating log in ~/.cache/euro-info/euro-info.log
  core/              no Qt widgets; usable from tests, the widget and the terminal
    feeds.py         sources, RSS fetching, weather, rates, grouping, topics
    images.py        thumbnail download and disk cache
    quality.py       evidence labels, ranking, coverage audit (cached by content)
    reasoning.py     related coverage and the evidence map for AI analysis
    workspace.py     research library (SQLite), search syntax, export, backups
    ai.py            Ollama: model choice, service start/stop, streaming chat, model pull
    translation.py   off / local AI / Google translation and its cache
    updates.py       GitHub release check
    i18n.py          phrasebook for seven languages
    articles.py      article keys, saved stories, offline snapshot
    widget.py        JSON for the Plasma widget
    cli.py           terminal headlines
  ui/
    application.py   startup, single instance, fonts
    main_window.py   the window, views, filters, rendering, actions
    cards.py         story cards (update in place)
    dialogs.py       settings, diagnostics, sources, notes, coverage, model download
    reader.py        in-app reader (imports Qt WebEngine lazily)
    summary.py       AI analysis window
    jobs.py          background work on QThreadPool
    theme.py         design tokens and generated stylesheet
    icons.py         SVG icon set
    widgets.py       banner, AI status button
    common.py        shared state: language, theme, research library
plasma-widget/       KDE Plasma 6 widget (runs `euro-info --widget-json`)
packaging/install.sh per-user installer shipped inside the release
```

### Rules of thumb

- Network, disk and model work runs in `ui/jobs.py` workers, never on the interface thread.
- Cards update themselves (`set_saved`, `set_read`, `set_localized`, `set_image`); call `render_news()`
  only when the set or order of stories changes.
- Expensive per-article text work is cached by content (`functools.lru_cache`), never stored on the
  article dict, so copies of an article can never carry stale results.
- Every user-visible string goes through `tr()` and needs an entry in `core/i18n.py` for all six
  languages; a test fails otherwise.
- Broad `except Exception` is allowed only where a failure must be reported instead of crashing, and it
  must log or show the error.

## Tests

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests
.venv/bin/ruff check euroinfo tests app.py
```

`tests/support.py` points every XDG folder at a temporary directory, so tests never read or write your
real settings or library. GitHub Actions runs the same checks on every push (`.github/workflows/ci.yml`).

## Release

1. Update `__version__` in `euroinfo/__init__.py` and add a section to `CHANGELOG.md`.
2. `./build-linux.sh` (add `--appimage` for a single-file AppImage). It lints, tests, builds with
   PyInstaller, drops the bundled font libraries, assembles the app folder with `install.sh` and the
   widget, and writes `dist/SHA256SUMS.txt` with plain file names.
3. Tag `v<version>`, push, and attach the files from `dist/` to a GitHub release.
