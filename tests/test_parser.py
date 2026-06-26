from radio_monitor.parser import parse_response


def _make_state_vector(
    icao24: str = "abc123",
    callsign: str = "DLH1234 ",
    country: str = "Germany",
    time_position: int = 1700000000,
    last_contact: int = 1700000001,
    lon: float = 11.5,
    lat: float = 48.1,
    baro_alt: float = 10000.0,
    on_ground: bool = False,
    velocity: float = 250.0,
    true_track: float = 90.0,
    vertical_rate: float = 0.0,
    sensors: list | None = None,
    geo_alt: float = 10050.0,
    squawk: str = "1000",
    spi: bool = False,
    position_source: int = 0,
) -> list:
    return [
        icao24, callsign, country, time_position, last_contact,
        lon, lat, baro_alt, on_ground, velocity, true_track,
        vertical_rate, sensors or [0], geo_alt, squawk, spi, position_source,
    ]


class TestParseResponse:
    def test_parses_valid_state(self):
        raw = {"time": 1700000000, "states": [_make_state_vector()]}
        result = parse_response(raw, 42.0)

        assert result.timestamp == 1700000000
        assert len(result.transmissions) == 1

        t = result.transmissions[0]
        assert t.icao24 == "abc123"
        assert t.callsign == "DLH1234"
        assert t.origin_country == "Germany"
        assert t.baro_altitude == 10000.0
        assert t.on_ground is False

    def test_strips_and_lowercases_icao(self):
        raw = {"time": 0, "states": [_make_state_vector(icao24=" ABC123 ")]}
        result = parse_response(raw, 0.0)
        assert result.transmissions[0].icao24 == "abc123"

    def test_handles_null_callsign(self):
        raw = {"time": 0, "states": [_make_state_vector(callsign=None)]}
        result = parse_response(raw, 0.0)
        assert result.transmissions[0].callsign is None

    def test_skips_malformed_state(self):
        raw = {"time": 0, "states": [[1, 2, 3]]}
        result = parse_response(raw, 0.0)
        assert len(result.transmissions) == 0

    def test_handles_empty_states(self):
        raw = {"time": 0, "states": None}
        result = parse_response(raw, 0.0)
        assert len(result.transmissions) == 0

    def test_multiple_states(self):
        raw = {
            "time": 0,
            "states": [
                _make_state_vector(icao24="a1", last_contact=100),
                _make_state_vector(icao24="b2", last_contact=101),
                _make_state_vector(icao24="c3", last_contact=102),
            ],
        }
        result = parse_response(raw, 0.0)
        assert len(result.transmissions) == 3
        assert {t.icao24 for t in result.transmissions} == {"a1", "b2", "c3"}
