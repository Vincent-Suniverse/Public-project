# radio-monitor

Monitoring pipeline that captures ADS-B aircraft transponder transmissions on 1090 MHz, structures them, and persists them to a local database.

## Architecture

```
┌────────────────┐     ┌────────┐     ┌────────┐     ┌───────────────┐     ┌─────────┐
│  ADS-B Source  │────▶│ Poller │────▶│ Parser │────▶│ Deduplication │────▶│ Storage │
│ (OpenSky API)  │     │        │     │        │     │               │     │(SQLite) │
└────────────────┘     └────────┘     └────────┘     └───────────────┘     └─────────┘
                          ▲                                                     │
                          │                                                     ▼
                    ┌───────────┐                                       ┌──────────────┐
                    │ Scheduler │                                       │  poll_runs    │
                    │(cron/loop)│                                       │  (audit log)  │
                    └───────────┘                                       └──────────────┘
```

Each pipeline stage is a separate module with a single responsibility:

| Stage | Module | Responsibility |
|---|---|---|
| **Poll** | `poller.py` | HTTP request with retry + exponential backoff |
| **Parse** | `parser.py` | Raw JSON → typed `Transmission` objects, input validation |
| **Deduplicate** | `storage.py` | `UNIQUE(icao24, last_contact)` constraint — DB-level idempotency |
| **Store** | `storage.py` | SQLite with WAL journaling for crash safety |
| **Orchestrate** | `pipeline.py` | Wires stages together, manages poll run lifecycle |

## Tech Stack

- **Python 3.10+** — standard library for most functionality
- **requests** — HTTP client for API polling
- **SQLite** (stdlib `sqlite3`) — embedded storage, zero external dependencies
- **pytest** — test suite
- **cron / systemd** — production scheduling (pipeline provides `--once` mode)

## Setup

```bash
git clone https://github.com/vincent-suniverse/public-project.git
cd public-project

python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
# or:
pip install -r requirements.txt
```

## Usage

**Single poll cycle** (suitable for cron):

```bash
python -m radio_monitor.cli run --once
```

**Continuous polling** (daemon mode):

```bash
python -m radio_monitor.cli run
```

**View statistics:**

```bash
python -m radio_monitor.cli stats
```

**Cron example** (poll every 60 seconds):

```cron
* * * * * cd /path/to/repo && .venv/bin/python -m radio_monitor.cli run --once >> /var/log/radio-monitor.log 2>&1
```

### Configuration

All settings are configurable via environment variables:

| Variable | Default | Description |
|---|---|---|
| `RM_API_URL` | OpenSky API | Data source endpoint |
| `RM_DB_PATH` | `data/transmissions.db` | SQLite database location |
| `RM_POLL_INTERVAL` | `30` | Seconds between polls (continuous mode) |
| `RM_REQUEST_TIMEOUT` | `15` | HTTP timeout in seconds |
| `RM_MAX_RETRIES` | `3` | Retry attempts per poll |
| `RM_LAT_MIN` / `RM_LAT_MAX` | `46.0` / `55.0` | Latitude bounding box |
| `RM_LON_MIN` / `RM_LON_MAX` | `5.0` / `17.0` | Longitude bounding box |
| `RM_LOG_LEVEL` | `INFO` | Logging verbosity |

## Data Model

### `transmissions`

Each row represents a single ADS-B state vector received from an aircraft:

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Auto-increment primary key |
| `poll_run_id` | INTEGER | Foreign key to the poll run that captured this record |
| `icao24` | TEXT | ICAO 24-bit transponder address (unique aircraft identifier) |
| `callsign` | TEXT | Flight callsign (nullable — not all aircraft broadcast one) |
| `origin_country` | TEXT | Country of registration |
| `time_position` | INTEGER | Unix timestamp of last position report |
| `last_contact` | INTEGER | Unix timestamp of last received message |
| `longitude` / `latitude` | REAL | Position in decimal degrees |
| `baro_altitude` / `geo_altitude` | REAL | Barometric / geometric altitude in meters |
| `on_ground` | INTEGER | Whether the aircraft is on the ground |
| `velocity` | REAL | Ground speed in m/s |
| `true_track` | REAL | Track angle in degrees (clockwise from north) |
| `vertical_rate` | REAL | Climb/descent rate in m/s |
| `squawk` | TEXT | Transponder squawk code |
| `spi` | INTEGER | Special Position Indicator flag |
| `position_source` | INTEGER | Source of position data (0=ADS-B, 1=ASTERIX, 2=MLAT) |

**Deduplication key:** `UNIQUE(icao24, last_contact)`

### `poll_runs`

Audit log tracking every pipeline execution:

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Auto-increment primary key |
| `timestamp` | INTEGER | Unix timestamp when the poll was initiated |
| `status` | TEXT | `started`, `completed`, or `failed` |
| `raw_count` | INTEGER | Number of raw state vectors received |
| `parsed_count` | INTEGER | Number successfully parsed |
| `new_count` | INTEGER | Number of new (non-duplicate) records stored |
| `duplicate_count` | INTEGER | Number rejected by dedup |
| `request_duration_ms` | REAL | HTTP request latency |
| `error_message` | TEXT | Error details if status is `failed` |
| `created_at` | TEXT | ISO 8601 wall-clock timestamp |

## Engineering Decisions

### Idempotency

Deduplication is enforced at the database level via a `UNIQUE(icao24, last_contact)` constraint with `INSERT OR IGNORE`. This guarantees idempotency regardless of application state — the same transmission inserted twice produces the same result as inserting it once. No in-memory bloom filters or caches that could drift.

### Crash Recovery

Every poll cycle begins by writing a `poll_runs` row with `status = 'started'` before any work happens. If the process crashes mid-cycle, the row remains in `started` state. On the next startup, the pipeline scans for orphaned runs and marks them as `failed`. This provides:

- A complete audit trail with no silent gaps
- Visibility into whether failures were transient (retry succeeded) or persistent
- The ability to detect and alert on crash loops via the `poll_runs` table

### WAL Journaling

SQLite is configured with `PRAGMA journal_mode=WAL` to ensure the database remains consistent even after an unclean shutdown. WAL mode also allows concurrent reads during writes, which matters if a separate process queries the data while the pipeline is running.

### Retry with Exponential Backoff

The poller retries failed HTTP requests with exponential backoff (`2^attempt` seconds). This handles transient network issues and API rate limiting without hammering the source. After all retries are exhausted, the failure is recorded in `poll_runs` and the pipeline moves on to the next cycle — it never blocks indefinitely.

### Separation of Concerns

Each pipeline stage is a pure function or a class with a narrow interface:

- `poll()` returns raw JSON — it knows nothing about parsing or storage
- `parse_response()` converts JSON to typed objects — it knows nothing about HTTP or SQL
- `Storage` handles persistence — it knows nothing about the data source

This makes each stage independently testable and replaceable. Swapping the data source (e.g., from OpenSky to a local RTL-SDR receiver) requires changing only the poller, not the parser or storage layer.

### Schema as Code

The database schema is defined as a SQL string inside `storage.py` and applied on every startup via `CREATE TABLE IF NOT EXISTS`. This eliminates external migration files for a project of this scale while still being idempotent — running the pipeline against an existing database is safe.

## Tests

```bash
pytest
```

## License

MIT
