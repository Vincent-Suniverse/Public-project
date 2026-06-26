from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    api_url: str = "https://opensky-network.org/api/states/all"
    db_path: str = "data/transmissions.db"
    poll_interval_seconds: int = 30
    request_timeout_seconds: int = 15
    max_retries: int = 3
    retry_backoff_base: float = 2.0
    lat_min: float = 46.0
    lat_max: float = 55.0
    lon_min: float = 5.0
    lon_max: float = 17.0
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> Config:
        defaults = cls()
        return cls(
            api_url=os.getenv("RM_API_URL", defaults.api_url),
            db_path=os.getenv("RM_DB_PATH", defaults.db_path),
            poll_interval_seconds=int(
                os.getenv("RM_POLL_INTERVAL", str(defaults.poll_interval_seconds))
            ),
            request_timeout_seconds=int(
                os.getenv("RM_REQUEST_TIMEOUT", str(defaults.request_timeout_seconds))
            ),
            max_retries=int(
                os.getenv("RM_MAX_RETRIES", str(defaults.max_retries))
            ),
            retry_backoff_base=float(
                os.getenv("RM_RETRY_BACKOFF", str(defaults.retry_backoff_base))
            ),
            lat_min=float(os.getenv("RM_LAT_MIN", str(defaults.lat_min))),
            lat_max=float(os.getenv("RM_LAT_MAX", str(defaults.lat_max))),
            lon_min=float(os.getenv("RM_LON_MIN", str(defaults.lon_min))),
            lon_max=float(os.getenv("RM_LON_MAX", str(defaults.lon_max))),
            log_level=os.getenv("RM_LOG_LEVEL", defaults.log_level),
        )
