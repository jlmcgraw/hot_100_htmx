import sys
from pathlib import Path
import pydantic

# Provide a minimal TypeAdapter for older pydantic versions
if not hasattr(pydantic, "TypeAdapter"):
    class DummyTypeAdapter:
        def __init__(self, _):
            pass
        def validate_python(self, data):
            return data
    pydantic.TypeAdapter = DummyTypeAdapter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from create_database import Chart, SongData, aggregate_song_stats


def test_aggregate_song_stats_basic():
    chart1 = Chart(
        date="2024-01-08",
        data=[
            SongData(
                song="Test Song",
                artist="Artist",
                this_week=10,
                last_week=None,
                peak_position=10,
                weeks_on_chart=1,
            )
        ],
    )
    chart2 = Chart(
        date="2024-01-01",
        data=[
            SongData(
                song="Test Song",
                artist="Artist",
                this_week=5,
                last_week=10,
                peak_position=5,
                weeks_on_chart=2,
            )
        ],
    )

    stats = aggregate_song_stats([chart1, chart2])
    key = ("Test Song", "Artist")
    assert key in stats
    song_stat = stats[key]
    assert song_stat.first_date == "2024-01-01"
    assert song_stat.peak_position == 5
    assert song_stat.weeks_on_chart == 2
