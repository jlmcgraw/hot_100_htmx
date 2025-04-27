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
    """
    Scrapes YouTube's search page to get the first video's thumbnail,
    but links to the YouTube search results page instead of the specific video.

    Args:
        query (str): The search term (e.g. song title + artist)

    Returns:
        dict: A dictionary with 'thumbnail_url' and 'search_url', or empty dict if not found.
    """
    try:
        # Construct search URL
        search_url = YOUTUBE_SEARCH_URL + quote_plus(query)

        # Use realistic headers
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        }

        # Fetch HTML content
        response = requests.get(search_url, headers=headers, timeout=5)
        response.raise_for_status()

        # Look for the ytInitialData JSON blob
        match = re.search(r"var ytInitialData = ({.*?});</script>", response.text, re.DOTALL)
        if not match:
            return {}

        yt_json = match.group(1)
        data = json.loads(yt_json)

        # Traverse to find the first video thumbnail
        contents = (
            data.get("contents", {})
                .get("twoColumnSearchResultsRenderer", {})
                .get("primaryContents", {})
                .get("sectionListRenderer", {})
                .get("contents", [{}])[0]
                .get("itemSectionRenderer", {})
                .get("contents", [])
        )

        for item in contents:
            video = item.get("videoRenderer")
            if video and "videoId" in video:
                video_id = video["videoId"]
                thumbnail_url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
                return {
                    "thumbnail_url": thumbnail_url,
                    "search_url": search_url,  # ✅ link to full search page
                }

    except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
        print(f"[YT ERROR] Failed to look up '{query}': {type(e).__name__}: {e}")

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

@app.route('/thumbnail')
def thumbnail():
    song = request.args.get('song', '')
    artist = request.args.get('artist', '')
    query = f"{artist} {song}"

    info = get_youtube_info(query)

    if not info:
        return '<div style="width:120px; height:90px; background:#ccc;"></div>'

    thumbnail_url = info['thumbnail_url']
    search_url = info['search_url']

    return f'''
    <a href="{search_url}" target="_blank" rel="noopener">
      <img src="{thumbnail_url}" alt="YouTube Thumbnail" style="width:120px; height:90px;">
    </a>
    '''



if __name__ == "__main__":
    app.run(port=8000, debug=True)
