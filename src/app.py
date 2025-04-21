#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
# "Flask",
# "Jinja2",
# "pydantic",
# "beautifulsoup4",
# "requests",
# ]
# ///

import concurrent.futures
import json
import re
import sqlite3
from functools import lru_cache
from urllib.parse import quote_plus

import requests
from flask import Flask, render_template, request, g

app = Flask(__name__)
DATABASE = "data/hot_100.sqlite"
executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)


# --- Database access ---
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# --- YouTube Thumbnail Lookup ---
YOUTUBE_SEARCH_URL = "https://www.youtube.com/results?search_query="


@lru_cache(maxsize=512)
def get_youtube_info(query: str) -> dict:
    try:
        search_url = YOUTUBE_SEARCH_URL + quote_plus(query)
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(search_url, headers=headers, timeout=5)

        match = re.search(
            r"var ytInitialData = ({.*?});</script>", response.text, re.DOTALL
        )
        if not match:
            return {}

        yt_json = match.group(1)
        data = json.loads(yt_json)

        contents = data["contents"]["twoColumnSearchResultsRenderer"][
            "primaryContents"
        ]["sectionListRenderer"]["contents"][0]["itemSectionRenderer"]["contents"]

        for video in contents:
            if "videoRenderer" in video:
                video_id = video["videoRenderer"]["videoId"]
                return {
                    "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
                    "video_url": f"https://www.youtube.com/watch?v={video_id}",
                }
    except Exception as e:
        print(f"[ERROR] YouTube lookup failed for '{query}': {e}")
    return {}


def queue_thumbnail(song: str, artist: str):
    query = f"{artist} {song}"
    executor.submit(get_youtube_info, query)


# --- Routes ---
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/songs")
def songs():
    artist = request.args.get("artist", "").strip().lower()
    query = request.args.get("query", "").strip().lower()
    year = request.args.get("year", "").strip()
    peak = request.args.get("peak", "").strip()
    page = int(request.args.get("page", 1))
    per_page = 20
    offset = (page - 1) * per_page

    db = get_db()
    sql = """
        SELECT song, artist, first_date, peak_position, peak_date, weeks_on_chart,
        COUNT(*) OVER() AS total_count
        FROM songs
        WHERE 1=1
    """
    params = []

    if artist:
        sql += " AND LOWER(artist) LIKE ?"
        params.append(f"%{artist}%")
    if query:
        sql += " AND LOWER(song) LIKE ?"
        params.append(f"%{query}%")
    if year:
        sql += ' AND strftime("%Y", first_date) = ?'
        params.append(year)
    if peak:
        sql += " AND peak_position = ?"
        params.append(peak)

    sql += " ORDER BY first_date DESC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])

    rows = db.execute(sql, params).fetchall()

    # Background thumbnail warming (optional)
    for row in rows:
        queue_thumbnail(row["song"], row["artist"])

    # Get total count from any row (if rows exist)
    total_count = rows[0]["total_count"] if rows else 0
    has_more = (offset + per_page) < total_count

    return render_template(
        "songs.html", songs=rows, next_page=page + 1, has_more=has_more, total_count=total_count
    )

@app.route("/songsjson")
def songsjson():
    artist = request.args.get("artist", "").strip().lower()
    query = request.args.get("query", "").strip().lower()
    year = request.args.get("year", "").strip()
    peak = request.args.get("peak", "").strip()
    page = int(request.args.get("page", 1))
    per_page = 20
    offset = (page - 1) * per_page

    db = get_db()

    sql = """
        SELECT song, artist, first_date, peak_position, peak_date, weeks_on_chart,
        COUNT(*) OVER() AS total_count
        FROM songs
        WHERE 1=1
    """
    params = []

    if artist:
        sql += " AND LOWER(artist) LIKE ?"
        params.append(f"%{artist}%")
    if query:
        sql += " AND LOWER(song) LIKE ?"
        params.append(f"%{query}%")
    if year:
        sql += ' AND strftime("%Y", first_date) = ?'
        params.append(year)
    if peak:
        sql += " AND peak_position = ?"
        params.append(peak)

    sql += " ORDER BY first_date DESC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])

    rows = db.execute(sql, params).fetchall()
    # Convert rows to list of dicts
    data = [dict(row) for row in rows]

    # Convert to JSON string
    json_data = json.dumps(data, indent=2)

    return json_data

@app.route('/songs/count')
def songs_count():
    artist = request.args.get("artist", "").strip().lower()
    query = request.args.get("query", "").strip().lower()
    year = request.args.get("year", "").strip()
    peak = request.args.get("peak", "").strip()

    db = get_db()
    count_sql = 'SELECT COUNT(*) FROM songs WHERE 1=1'
    params = []

    if artist:
        count_sql += " AND LOWER(artist) LIKE ?"
        params.append(f"%{artist}%")
    if query:
        count_sql += " AND LOWER(song) LIKE ?"
        params.append(f"%{query}%")
    if year:
        count_sql += ' AND strftime("%Y", first_date) = ?'
        params.append(year)
    if peak:
        count_sql += " AND peak_position = ?"
        params.append(peak)

    total = db.execute(count_sql, params).fetchone()[0]

    return str(total)

@app.route("/thumbnail")
def thumbnail() -> str:
    song = request.args.get("song")
    artist = request.args.get("artist")

    if not song or not artist:
        return "", 400

    yt = get_youtube_info(f"{artist} {song}")

    return render_template(
        "thumbnail.html",
        thumbnail_url=yt.get("thumbnail_url"),
        video_url=yt.get("video_url"),
    )


if __name__ == "__main__":
    app.run(port=8000, debug=True)
