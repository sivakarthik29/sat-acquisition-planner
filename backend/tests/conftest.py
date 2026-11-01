"""Shared fixtures. The real orbit data is a small frozen snapshot of public Firefly element sets (epoch 19 Jul 2026),
so tests are deterministic and never touch the network. NOW is chosen next to that epoch."""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.demo import demo_satellites
from app.tle import parse_tle_text

NOW = datetime(2026, 7, 19, 20, 0, tzinfo=timezone.utc).timestamp()
DAY = 86400.0
FIXTURES = Path(__file__).parent / "fixtures"


class ConstantCloud:
    """Stand-in for the cloud-history service: every hour has the same cloud cover."""

    def __init__(self, pct: float):
        self.pct = pct

    def hourly_cloud(self, lat, lon, start, end):
        t = int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp())
        stop = int(datetime(end.year, end.month, end.day, tzinfo=timezone.utc).timestamp()) + 86400
        return {h: self.pct for h in range(t, stop, 3600)}


@pytest.fixture(scope="session")
def real_sats():
    return parse_tle_text((FIXTURES / "real_tles.txt").read_text())


@pytest.fixture(scope="session")
def demo_sats():
    return demo_satellites(NOW)
