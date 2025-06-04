#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "Flask",
#   "Jinja2",
#   "pydantic",
# ]
# ///

import json
import sqlite3
import logging
import argparse
from pathlib import Path
from typing import List, Optional, Dict, Tuple
from collections import defaultdict
from dataclasses import dataclass
from pydantic import BaseModel, TypeAdapter

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
logger = logging.getLogger(__name__)

# --- Models ---
class SongData(BaseModel):
    song: str
    artist: str
    this_week: int
    last_week: Optional[int]
    peak_position: int
    weeks_on_chart: int

class Chart(BaseModel):
    date: str
    data: List[SongData]

@dataclass
class SongStats:
    first_date: Optional[str] = None
    peak_position: Optional[int] = None
    peak_date: Optional[str] = None
    weeks_on_chart: int = 0

# --- Functions ---
def load_charts(json_path: Path) -> List[Chart]:
    logger.info(f"Loading charts from {json_path}")
    with json_path.open(encoding="utf-8") as f:
        raw_data = json.load(f)
    return TypeAdapter(List[Chart]).validate_python(raw_data)

def aggregate_song_stats(charts: List[Chart]) -> Dict[Tuple[str, str], SongStats]:
    logger.info("Aggregating song statistics across charts")
    SongName = str
    SongArtist = str
    SongStatsKey = Tuple[SongName, SongArtist]

    song_stats: Dict[SongStatsKey, SongStats] = defaultdict(SongStats)

    for chart in charts:
        for song in chart.data:
            key = (song.song.strip(), song.artist.strip())
            entry = song_stats[key]

            if entry.first_date is None or chart.date < entry.first_date:
                entry.first_date = chart.date

            if entry.peak_position is None or song.this_week < entry.peak_position:
                entry.peak_position = song.this_week
                entry.peak_date = chart.date

            entry.weeks_on_chart += 1

    logger.info(f"Aggregated stats for {len(song_stats)} songs")
    return song_stats

def create_database(db_path: Path) -> sqlite3.Connection:
    logger.info(f"Creating SQLite database at {db_path}")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS songs")
    cursor.execute("""
        CREATE TABLE songs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            song TEXT,
            artist TEXT,
            first_date TEXT,
            peak_position INTEGER,
            peak_date TEXT,
            weeks_on_chart INTEGER
        )
    """)
    conn.commit()
    return conn

def insert_song_stats(conn: sqlite3.Connection, song_stats: Dict[Tuple[str, str], SongStats]):
    logger.info("Inserting aggregated song data into database")
    cursor = conn.cursor()
    for (song_name, artist_name), stats in song_stats.items():
        cursor.execute("""
            INSERT INTO songs (
                song, artist, first_date, peak_position, peak_date, weeks_on_chart
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            song_name,
            artist_name,
            stats.first_date,
            stats.peak_position,
            stats.peak_date,
            stats.weeks_on_chart
        ))
    conn.commit()
    logger.info("Data insertion complete")

def parse_args():
    parser = argparse.ArgumentParser(description="Create a SQLite database from Billboard Hot 100 JSON data.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("all.json"),
        help="Path to input JSON file (default: all.json)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("hot_100.sqlite"),
        help="Path to output SQLite database file (default: hot_100.sqlite)"
    )
    return parser.parse_args()

def main():
    args = parse_args()

    charts = load_charts(args.input)
    song_stats = aggregate_song_stats(charts)

    conn = create_database(args.output)
    insert_song_stats(conn, song_stats)
    conn.close()

    logger.info(f"✅ Database created with {len(song_stats)} songs in '{args.output}'")

if __name__ == "__main__":
    main()
