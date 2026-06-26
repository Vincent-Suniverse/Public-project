import tempfile
from pathlib import Path

from radio_monitor.config import Config
from radio_monitor.models import Transmission
from radio_monitor.storage import Storage


def _make_transmission(**overrides) -> Transmission:
    defaults = dict(
        icao24="abc123",
        callsign="DLH1234",
        origin_country="Germany",
        time_position=1700000000,
        last_contact=1700000001,
        longitude=11.5,
        latitude=48.1,
        baro_altitude=10000.0,
        on_ground=False,
        velocity=250.0,
        true_track=90.0,
        vertical_rate=0.0,
        geo_altitude=10050.0,
        squawk="1000",
        spi=False,
        position_source=0,
    )
    defaults.update(overrides)
    return Transmission(**defaults)


class TestStorage:
    def _make_storage(self, tmp_path: Path) -> Storage:
        db_path = str(tmp_path / "test.db")
        config = Config(db_path=db_path)
        return Storage(config)

    def test_store_and_retrieve_stats(self, tmp_path):
        storage = self._make_storage(tmp_path)
        run_id = storage.begin_poll_run(1700000000)

        transmissions = [
            _make_transmission(icao24="a1", last_contact=100),
            _make_transmission(icao24="a2", last_contact=101),
        ]
        new, dup = storage.store_transmissions(run_id, transmissions)

        assert new == 2
        assert dup == 0

        stats = storage.stats()
        assert stats["total_transmissions"] == 2
        assert stats["unique_aircraft"] == 2
        storage.close()

    def test_deduplication(self, tmp_path):
        storage = self._make_storage(tmp_path)
        run_id = storage.begin_poll_run(1700000000)

        t = _make_transmission(icao24="abc", last_contact=100)
        new1, dup1 = storage.store_transmissions(run_id, [t])
        new2, dup2 = storage.store_transmissions(run_id, [t])

        assert new1 == 1
        assert dup1 == 0
        assert new2 == 0
        assert dup2 == 1
        storage.close()

    def test_poll_run_lifecycle(self, tmp_path):
        storage = self._make_storage(tmp_path)
        run_id = storage.begin_poll_run(1700000000)

        incomplete = storage.get_incomplete_runs()
        assert run_id in incomplete

        storage.complete_poll_run(
            run_id,
            raw_count=10,
            parsed_count=8,
            new_count=5,
            duplicate_count=3,
            request_duration_ms=120.0,
        )

        incomplete = storage.get_incomplete_runs()
        assert run_id not in incomplete

        stats = storage.stats()
        assert stats["completed_poll_runs"] == 1
        storage.close()

    def test_fail_poll_run(self, tmp_path):
        storage = self._make_storage(tmp_path)
        run_id = storage.begin_poll_run(1700000000)

        storage.fail_poll_run(run_id, "timeout")

        incomplete = storage.get_incomplete_runs()
        assert run_id not in incomplete

        stats = storage.stats()
        assert stats["failed_poll_runs"] == 1
        storage.close()
