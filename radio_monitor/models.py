from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Transmission:
    icao24: str
    callsign: str | None
    origin_country: str
    time_position: int | None
    last_contact: int
    longitude: float | None
    latitude: float | None
    baro_altitude: float | None
    on_ground: bool
    velocity: float | None
    true_track: float | None
    vertical_rate: float | None
    geo_altitude: float | None
    squawk: str | None
    spi: bool
    position_source: int

    @property
    def dedup_key(self) -> tuple[str, int]:
        return (self.icao24, self.last_contact)


@dataclass(frozen=True, slots=True)
class PollResult:
    timestamp: int
    transmissions: list[Transmission]
    request_duration_ms: float
