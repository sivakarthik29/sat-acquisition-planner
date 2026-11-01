import os
from pathlib import Path

from app.tle import FIREFLY_IDS, load_satellites, parse_tle_text

from .conftest import FIXTURES, NOW

TEXT = (FIXTURES / "real_tles.txt").read_text()
SATS = parse_tle_text(TEXT)
BY_ID = {s.norad_id: f"{s.name}\n{s.line1}\n{s.line2}" for s in SATS}
IDS = list(BY_ID)


def fake_fetch(norad_id):
    return BY_ID[norad_id]


def broken_fetch(norad_id):
    raise OSError("network down")


def test_parse_handles_three_line_and_two_line_sets():
    """REQ-TLE-01: both element-set layouts parse."""
    assert [s.norad_id for s in SATS] == [62699, 62698, 65322]
    two_line = "\n".join(BY_ID[62698].split("\n")[1:])
    assert parse_tle_text(two_line)[0].norad_id == 62698
    assert parse_tle_text("garbage\nmore garbage") == []


def test_live_then_cache_then_stale_cache_then_demo(tmp_path: Path):
    """REQ-TLE-01: the loader falls back live -> fresh cache -> old cache -> synthetic demo, and says which it used."""
    live = load_satellites(tmp_path, "live", NOW, fake_fetch, IDS)
    assert live.source == "live" and len(live.satellites) == 3

    cached = load_satellites(tmp_path, "live", NOW, broken_fetch, IDS)     # fresh cache: no network call needed
    assert cached.source == "cache" and "Fresh" in cached.note

    cache_file = tmp_path / "tle_cache.txt"
    old = NOW - 3 * 3600
    os.utime(cache_file, (old, old))                                        # make the cache older than two hours
    stale = load_satellites(tmp_path, "live", NOW, broken_fetch, IDS)
    assert stale.source == "cache" and "older" in stale.note

    cache_file.unlink()
    demo = load_satellites(tmp_path, "live", NOW, broken_fetch, IDS)
    assert demo.source == "demo" and demo.satellites[0].name.startswith("DEMO")


def test_demo_mode_never_touches_the_network(tmp_path: Path):
    """REQ-TLE-01: SAT_SOURCE=demo returns synthetic orbits without calling fetch."""
    res = load_satellites(tmp_path, "demo", NOW, broken_fetch, FIREFLY_IDS)
    assert res.source == "demo" and len(res.satellites) == 6
