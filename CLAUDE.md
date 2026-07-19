# CLAUDE.md

Guidance for AI assistants (and humans) working in this repository.

## What this repo is

Two loosely related things live here under one roof:

1. **UVB-76 Transmission Database** — a public, static, searchable archive of
   documented voice transmissions from the UVB-76 ("The Buzzer") shortwave
   station on 4625 kHz. This is the primary purpose of the repo. Raw data lives
   in `data/` as markdown registers; a build step turns it into JSON consumed by
   a static site in `docs/` (served via GitHub Pages at
   `vincent-suniverse.github.io/public-project/`).
2. **`radio_monitor/`** — a *separate*, self-contained Python package: an ADS-B
   aircraft-transponder monitoring pipeline (OpenSky Network API → SQLite). It
   shares nothing with the UVB-76 code except the repository. Treat it as its own
   project.

Keep these two concerns separate. A change to the transmission database should
not touch `radio_monitor/`, and vice versa.

## Layout

```
data/                       Raw UVB-76 register markdown (the source of truth)
  UVB76_MASTER_REGISTER_V4.md          ~1230 transmissions, 2020–2026
  UVB76_NACHTRAG_*.md / UVB76_*_2026.md  dated supplements
docs/                       Static GitHub Pages site
  index.html                Frontend (loads transmissions.json)
  transmissions.json        GENERATED — do not hand-edit
scripts/
  parse_registers.py        data/*.md  ->  docs/transmissions.json
  telegram_ingest.py        Pulls new transmissions from Telegram into data/ + json
radio_monitor/              Standalone ADS-B pipeline (see below)
tests/                      pytest suite for radio_monitor
.github/workflows/          CI automation (see below)
pyproject.toml              Packaging + tooling config for radio_monitor
```

## UVB-76 database workflow

The register markdown files in `data/` are the source of truth. The website is
generated from them.

- **Data format** — each transmission line is
  `DATE TIME CALLSIGN COMMAND_BLOCK CODEWORD TARGET_BLOCK_1 TARGET_BLOCK_2`
  inside `## YYYY-MM` code-fenced sections. Optional trailing `[notes]`.
  Multi-word variants (DOPPEL, TRIPLE, QUADRUPEL) carry several codeword+block
  pairs. See the README for the full spec and `scripts/parse_registers.py` for
  the authoritative parsing rules.
- **Rebuild the site JSON** after editing any register:
  ```bash
  python scripts/parse_registers.py
  ```
  This regenerates `docs/transmissions.json`. Never edit that file by hand — it
  is overwritten on every build.
- **Adding transmissions** — append to the appropriate register in `data/`,
  matching the existing month sections and line format exactly, then rebuild.

## radio_monitor pipeline

A cleanly layered stdlib-plus-`requests` pipeline. Data flows one direction:

```
poller.poll()  ->  parser.parse_response()  ->  storage.Storage  (SQLite)
                    orchestrated by pipeline.Pipeline, driven by cli
```

- `config.py` — frozen `Config` dataclass, all knobs overridable via `RM_*`
  environment variables (`RM_DB_PATH`, `RM_POLL_INTERVAL`, bounding box
  `RM_LAT_MIN`…`RM_LON_MAX`, etc.). Construct with `Config.from_env()`.
- `models.py` — frozen, slotted dataclasses (`Transmission`, `PollResult`).
- `poller.py` — HTTP with retry + exponential backoff; raises `PollerError`.
- `parser.py` — tolerant: malformed OpenSky state vectors are skipped and
  logged, never fatal. Expects 17-field vectors.
- `storage.py` — SQLite schema with `UNIQUE(icao24, last_contact)` for dedup;
  tracks each fetch in a `poll_runs` table.
- `pipeline.py` — `run_once()` / `run_continuous()`; records run status.
- `cli.py` — entrypoint (`radio-monitor` console script).

Run it:
```bash
pip install -e ".[dev]"
python -m radio_monitor.cli run --once     # single poll
python -m radio_monitor.cli run            # continuous loop
python -m radio_monitor.cli stats          # summary from the DB
```

## Development

```bash
pip install -e ".[dev]"   # or: pip install -r requirements.txt
pytest                    # tests live in tests/, cover radio_monitor
ruff check .              # lint; line-length 99, target py310
```

- Python **3.10+**. Every module uses `from __future__ import annotations` and
  modern type hints (`str | None`, `list[...]`). Match that style.
- The radio_monitor pipeline depends only on the stdlib plus `requests`. Do not
  add heavy dependencies without a clear reason.
- Add or update tests under `tests/` for any change to `radio_monitor`.

## CI / automation (`.github/workflows/`)

- **build-json.yml** — on any push touching `data/*.md` or
  `scripts/parse_registers.py`, rebuilds `docs/transmissions.json` and commits
  it back. This means you usually don't need to commit the regenerated JSON
  yourself on the default branch — but do rebuild and commit it on feature
  branches so the site preview is correct.
- **telegram-ingest.yml** — scheduled every 30 min (and manual dispatch); runs
  `scripts/telegram_ingest.py` to fetch new transmissions. It is a no-op unless
  the `TELEGRAM_BOT_TOKEN` secret is set, so it fails gracefully in forks.

## Conventions

- Keep the UVB-76 data pipeline pure-Python and dependency-light so it runs in
  CI without setup.
- Preserve the exact register line format — the parser and the historical data
  both depend on it.
- License: MIT.
