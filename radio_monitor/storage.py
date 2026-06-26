from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from .config import Config
from .models import Transmission

logger = logging.getLogger(__name__)

SCHEMA = """\
CREATE TABLE IF NOT EXISTS transmissions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    poll_run_id     INTEGER NOT NULL,
    icao24          TEXT    NOT NULL,
    callsign        TEXT,
    origin_country  TEXT    NOT NULL,
    time_position   INTEGER,
    last_contact    INTEGER NOT NULL,
    longitude       REAL,
    latitude        REAL,
    baro_altitude   REAL,
    on_ground       INTEGER NOT NULL,
    velocity        REAL,
    true_track      REAL,
    vertical_rate   REAL,
    geo_altitude    REAL,
    squawk          TEXT,
    spi             INTEGER NOT NULL,
    position_source INTEGER NOT NULL,
    UNIQUE(icao24, last_contact)
);

CREATE TABLE IF NOT EXISTS poll_runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp           INTEGER NOT NULL,
    status              TEXT    NOT NULL DEFAULT 'started',
    raw_count           INTEGER,
    parsed_count        INTEGER,
    new_count           INTEGER,
    duplicate_count     INTEGER,
    request_duration_ms REAL,
    error_message       TEXT,
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_transmissions_icao24
    ON transmissions(icao24);
CREATE INDEX IF NOT EXISTS idx_transmissions_last_contact
    ON transmissions(last_contact);
CREATE INDEX IF NOT EXISTS idx_poll_runs_timestamp
    ON poll_runs(timestamp);
"""


class Storage:
    def __init__(self, config: Config) -> None:
        db_dir = Path(config.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(config.db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        logger.info("Storage initialized at %s", config.db_path)

    def begin_poll_run(self, timestamp: int) -> int:
        cursor = self._conn.execute(
            "INSERT INTO poll_runs (timestamp, status) VALUES (?, 'started')",
            (timestamp,),
        )
        self._conn.commit()
        run_id: int = cursor.lastrowid  # type: ignore[assignment]
        logger.debug("Started poll run %d (ts=%d)", run_id, timestamp)
        return run_id

    def store_transmissions(
        self, poll_run_id: int, transmissions: list[Transmission]
    ) -> tuple[int, int]:
        new_count = 0
        for t in transmissions:
            cursor = self._conn.execute(
                """INSERT OR IGNORE INTO transmissions (
                    poll_run_id, icao24, callsign, origin_country,
                    time_position, last_contact, longitude, latitude,
                    baro_altitude, on_ground, velocity, true_track,
                    vertical_rate, geo_altitude, squawk, spi, position_source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    poll_run_id,
                    t.icao24,
                    t.callsign,
                    t.origin_country,
                    t.time_position,
                    t.last_contact,
                    t.longitude,
                    t.latitude,
                    t.baro_altitude,
                    int(t.on_ground),
                    t.velocity,
                    t.true_track,
                    t.vertical_rate,
                    t.geo_altitude,
                    t.squawk,
                    int(t.spi),
                    t.position_source,
                ),
            )
            if cursor.rowcount > 0:
                new_count += 1

        self._conn.commit()
        dup_count = len(transmissions) - new_count
        return new_count, dup_count

    def complete_poll_run(
        self,
        poll_run_id: int,
        *,
        raw_count: int,
        parsed_count: int,
        new_count: int,
        duplicate_count: int,
        request_duration_ms: float,
    ) -> None:
        self._conn.execute(
            """UPDATE poll_runs SET
                status = 'completed',
                raw_count = ?,
                parsed_count = ?,
                new_count = ?,
                duplicate_count = ?,
                request_duration_ms = ?
            WHERE id = ?""",
            (raw_count, parsed_count, new_count, duplicate_count, request_duration_ms, poll_run_id),
        )
        self._conn.commit()

    def fail_poll_run(self, poll_run_id: int, error: str) -> None:
        self._conn.execute(
            "UPDATE poll_runs SET status = 'failed', error_message = ? WHERE id = ?",
            (error, poll_run_id),
        )
        self._conn.commit()

    def get_incomplete_runs(self) -> list[int]:
        cursor = self._conn.execute(
            "SELECT id FROM poll_runs WHERE status = 'started' ORDER BY id"
        )
        return [row[0] for row in cursor.fetchall()]

    def stats(self) -> dict[str, int]:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM transmissions"
        ).fetchone()
        total_transmissions = row[0] if row else 0

        row = self._conn.execute(
            "SELECT COUNT(*) FROM poll_runs WHERE status = 'completed'"
        ).fetchone()
        completed_runs = row[0] if row else 0

        row = self._conn.execute(
            "SELECT COUNT(*) FROM poll_runs WHERE status = 'failed'"
        ).fetchone()
        failed_runs = row[0] if row else 0

        row = self._conn.execute(
            "SELECT COUNT(DISTINCT icao24) FROM transmissions"
        ).fetchone()
        unique_aircraft = row[0] if row else 0

        return {
            "total_transmissions": total_transmissions,
            "completed_poll_runs": completed_runs,
            "failed_poll_runs": failed_runs,
            "unique_aircraft": unique_aircraft,
        }

    def close(self) -> None:
        self._conn.close()
