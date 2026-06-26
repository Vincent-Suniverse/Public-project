from __future__ import annotations

import logging
import time
from typing import Any

import requests

from .config import Config

logger = logging.getLogger(__name__)


class PollerError(Exception):
    pass


def poll(config: Config) -> tuple[dict[str, Any], float]:
    params: dict[str, Any] = {
        "lamin": config.lat_min,
        "lamax": config.lat_max,
        "lomin": config.lon_min,
        "lomax": config.lon_max,
    }

    last_error: Exception | None = None

    for attempt in range(1, config.max_retries + 1):
        try:
            start = time.monotonic()
            resp = requests.get(
                config.api_url,
                params=params,
                timeout=config.request_timeout_seconds,
            )
            duration_ms = (time.monotonic() - start) * 1000
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            logger.info(
                "Poll succeeded in %.0fms (attempt %d)", duration_ms, attempt
            )
            return data, duration_ms

        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < config.max_retries:
                backoff = config.retry_backoff_base ** attempt
                logger.warning(
                    "Poll attempt %d/%d failed: %s — retrying in %.1fs",
                    attempt,
                    config.max_retries,
                    exc,
                    backoff,
                )
                time.sleep(backoff)
            else:
                logger.error(
                    "Poll failed after %d attempts: %s", config.max_retries, exc
                )

    raise PollerError(
        f"All {config.max_retries} poll attempts failed"
    ) from last_error
