from __future__ import annotations

import logging
from typing import Any

from .models import PollResult, Transmission

logger = logging.getLogger(__name__)

EXPECTED_FIELD_COUNT = 17


def parse_response(raw: dict[str, Any], request_duration_ms: float) -> PollResult:
    timestamp = raw.get("time", 0)
    states: list[list[Any]] = raw.get("states") or []

    transmissions: list[Transmission] = []
    for state in states:
        if not isinstance(state, list) or len(state) < EXPECTED_FIELD_COUNT:
            logger.debug("Skipping malformed state vector: %s", state[:3] if state else state)
            continue

        try:
            transmissions.append(
                Transmission(
                    icao24=str(state[0]).strip().lower(),
                    callsign=state[1].strip() if state[1] else None,
                    origin_country=str(state[2]),
                    time_position=_to_int(state[3]),
                    last_contact=int(state[4]),
                    longitude=_to_float(state[5]),
                    latitude=_to_float(state[6]),
                    baro_altitude=_to_float(state[7]),
                    on_ground=bool(state[8]),
                    velocity=_to_float(state[9]),
                    true_track=_to_float(state[10]),
                    vertical_rate=_to_float(state[11]),
                    geo_altitude=_to_float(state[13]),
                    squawk=str(state[14]).strip() if state[14] else None,
                    spi=bool(state[15]),
                    position_source=int(state[16]),
                )
            )
        except (ValueError, TypeError, IndexError) as exc:
            logger.debug("Skipping unparseable state vector: %s (%s)", state[:3], exc)

    logger.info(
        "Parsed %d transmissions from %d raw state vectors",
        len(transmissions),
        len(states),
    )
    return PollResult(
        timestamp=timestamp,
        transmissions=transmissions,
        request_duration_ms=request_duration_ms,
    )


def _to_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _to_int(value: Any) -> int | None:
    return None if value is None else int(value)
