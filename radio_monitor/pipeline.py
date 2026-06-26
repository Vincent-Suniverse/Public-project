from __future__ import annotations

import logging
import time

from .config import Config
from .parser import parse_response
from .poller import PollerError, poll
from .storage import Storage

logger = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._storage = Storage(config)

    def run_once(self) -> bool:
        run_id = self._storage.begin_poll_run(int(time.time()))

        try:
            raw, duration_ms = poll(self._config)
            result = parse_response(raw, duration_ms)

            new_count, dup_count = self._storage.store_transmissions(
                run_id, result.transmissions
            )

            raw_count = len(raw.get("states") or [])
            self._storage.complete_poll_run(
                run_id,
                raw_count=raw_count,
                parsed_count=len(result.transmissions),
                new_count=new_count,
                duplicate_count=dup_count,
                request_duration_ms=duration_ms,
            )

            logger.info(
                "Poll run %d: %d new, %d duplicates (of %d parsed)",
                run_id,
                new_count,
                dup_count,
                len(result.transmissions),
            )
            return True

        except PollerError as exc:
            self._storage.fail_poll_run(run_id, str(exc))
            logger.error("Poll run %d failed: %s", run_id, exc)
            return False

        except Exception as exc:
            self._storage.fail_poll_run(run_id, str(exc))
            logger.exception("Poll run %d unexpected error: %s", run_id, exc)
            return False

    def run_continuous(self) -> None:
        logger.info(
            "Starting continuous polling (interval=%ds)",
            self._config.poll_interval_seconds,
        )
        self._recover_incomplete_runs()

        while True:
            self.run_once()
            time.sleep(self._config.poll_interval_seconds)

    def _recover_incomplete_runs(self) -> None:
        incomplete = self._storage.get_incomplete_runs()
        if not incomplete:
            return

        logger.warning(
            "Found %d incomplete poll runs from previous session: %s",
            len(incomplete),
            incomplete,
        )
        for run_id in incomplete:
            self._storage.fail_poll_run(
                run_id, "Marked as failed during recovery — process crashed before completion"
            )
        logger.info("Marked %d orphaned runs as failed", len(incomplete))

    def stats(self) -> dict[str, int]:
        return self._storage.stats()

    def close(self) -> None:
        self._storage.close()
