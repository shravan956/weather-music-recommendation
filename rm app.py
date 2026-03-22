import sys
import io
import os

# Load .env file for local development
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Fix Windows Unicode/charmap encoding error (emoji etc.)
if sys.stdout and hasattr(sys.stdout, 'encoding') and sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'encoding') and sys.stderr.encoding and sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
os.environ['PYTHONUTF8'] = '1'

from flask import Flask, render_template, request, jsonify
import requests
from datetime import datetime
import calendar
import re
import concurrent.futures

app = Flask(__name__, template_folder="templates", static_folder="static")

# ===== API KEYS (set these in Render dashboard / .env file) =====
WEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "use your own weather api key").strip()
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "use your own yt api key").strip()
# ================================================================

SINGERS = [
    "Arijit Singh", "Shreya Ghoshal", "Atif Aslam", "KK", "Sonu Nigam",
    "Armaan Malik", "Neha Kakkar", "Jubin Nautiyal", "Badshah", "Kishore Kumar"
]

LANGUAGES = ["Hindi", "English", "Tamil", "Telugu"]

CATEGORIES = {
    "All": "song",
    "Romantic": "romantic song",
    "Sad": "sad song",
    "Chill": "lofi chill song",
    "Party": "party song",
    "Workout": "workout song",
    "Classic": "old classic song",
    "Mix": "songs",
}

GENERATIONS = {
    "All": "",
    "90s": "90s hits",
    "2000s": "2000s hits",
    "GenZ": "genz viral song",
    "New Release": "new released song 2025",
    "Trendy": "trending viral song india"
}

WEATHER_TO_CATEGORY = {
    "Clear": "Party",
    "Rain": "Romantic",
    "Clouds": "Chill",
    "Snow": "Classic",
    "Thunderstorm": "Workout",
    "Haze": "Chill",
    "Mist": "Chill",
    "Smoke": "Classic",
    "Drizzle": "Romantic",
    "Fog": "Chill",
}


# ================= WEATHER HELPERS =================

def season_from_month(month: int) -> str:
    if month in (12, 1, 2):
        return "Winter"
    if month in (3, 4, 5):
        return "Summer"
    if month in (6, 7, 8, 9):
        return "Monsoon"
    return "Autumn"


def season_month_from_weather(w: dict):
    try:
        dt_utc = int(w.get("dt", 0))
        tz = int(w.get("timezone", 0))
        local_dt = datetime.utcfromtimestamp(dt_utc + tz)
        month_num = local_dt.month
    except Exception:
        month_num = datetime.now().month

    month_name = calendar.month_name[month_num]
    return season_from_month(month_num), month_name


def reverse_geocode(lat: float, lon: float) -> str:
    try:
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            "format": "jsonv2",
            "lat": lat,
            "lon": lon,
            "zoom": 18,
            "addressdetails": 1
        }
        r = requests.get(
            url,
            params=params,
            headers={"User-Agent": "weather-music-app/1.0"},
            timeout=15
        )
        data = r.json()
        addr = data.get("address", {}) or {}

        for key in ["neighbourhood", "suburb", "quarter", "hamlet", "village", "town", "city", "county", "state"]:
            if addr.get(key):
                return addr.get(key)

        dn = data.get("display_name")
        if dn:
            return dn.split(",")[0].strip()
    except Exception:
        pass

    return ""


def get_weather(city: str):
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"q": city, "appid": WEATHER_API_KEY, "units": "metric"}
    return requests.get(url, params=params, timeout=15).json()


def get_weather_by_coords(lat: float, lon: float):
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"lat": lat, "lon": lon, "appid": WEATHER_API_KEY, "units": "metric"}
    return requests.get(url, params=params, timeout=15).json()


def yt_get(url, params):
    r = requests.get(url, params=params, timeout=25)
    print(f"[YT] HTTP {r.status_code} => {url.split('/')[-1]}")
    data = r.json()
    if "error" in data:
        err = data["error"]
        code = err.get("code", "?")
        msg  = err.get("message", str(err))
        print(f"[ERROR] YouTube API {code}: {msg}")
    return data


def parse_duration_seconds(iso: str) -> int:
    """Parse ISO 8601 duration PT#H#M#S → total seconds."""
    m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso or "")
    if not m:
        return 0
    h = int(m.group(1) or 0)
    mi = int(m.group(2) or 0)
    s = int(m.group(3) or 0)
    return h * 3600 + mi * 60 + s


# ================= UPDATED fetch_songs WITH GENERATION =================

def _fetch_single_query(q, target, YOUTUBE_API_KEY, singer, category, generation):
    search_url = "https://www.googleapis.com/youtube/v3/search"
    search_params = {
        "part": "snippet",
        "q": q,
        "key": YOUTUBE_API_KEY,
        "maxResults": 20,
        "type": "video",
        "safeSearch": "moderate",
        "regionCode": "IN",
        "order": "viewCount" if generation == "Trendy" else "relevance"
    }

    sdata = yt_get(search_url, search_params)
    if "error" in sdata:
        print(f"[YT ERROR] {sdata['error']}")
        return []
    items = sdata.get("items", [])

    results = []
    for it in items:
        vid = it.get("id", {}).get("videoId")
        if not vid:
            continue

        snippet = it.get("snippet", {})

        # Skip live broadcasts
        if snippet.get("liveBroadcastContent") in ("live", "upcoming"):
            continue

        # Skip obvious non-music content
        title_lower = snippet.get("title", "").lower()
        skip_keywords = ["interview", "news", "episode", "podcast", "reaction", "review", "tutorial", "cricket", "match"]
        if any(kw in title_lower for kw in skip_keywords):
            continue

        results.append({
            "video_id": vid,
            "title": snippet.get("title", ""),
            "channel": snippet.get("channelTitle", ""),
            "singer": singer,
            "category": category,
            "generation": generation,
            "embeddable": True
        })
    return results

def fetch_songs(singer: str, language: str, category: str, generation: str = "All", target: int = 40, exclude_ids: list = None):
    query_tag = CATEGORIES.get(category, "song")
    gen_tag = GENERATIONS.get(generation, "")

    import random

    # Official Indian music labels — their videos are ALWAYS embeddable
    music_labels = ["T-Series", "Sony Music India", "Zee Music Company", "Tips Official", "Saregama Music", "YRF Music"]
    random.shuffle(music_labels)

    suffixes = ["audio", "lyrical video", "full song", "official video", "audio jukebox"]
    random.shuffle(suffixes)

    queries = [
        f"{singer} {language} {query_tag} {gen_tag} {music_labels[0]} {suffixes[0]}",
        f"{singer} {query_tag} {gen_tag} {music_labels[1]} {suffixes[1]}",
        f"{singer} {language} {query_tag} {gen_tag} official {suffixes[2]}",
        f"{singer} {gen_tag} {music_labels[2]} {suffixes[3]}",
        f"{query_tag} {language} {gen_tag} {music_labels[3]} {suffixes[4]}",
    ]

    songs = []
    seen = set(exclude_ids or [])

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_query = {executor.submit(_fetch_single_query, q, target, YOUTUBE_API_KEY, singer, category, generation): q for q in queries}
        for future in concurrent.futures.as_completed(future_to_query):
            try:
                results = future.result()
                for song in results:
                    vid = song["video_id"]
                    if vid not in seen:
                        seen.add(vid)
                        songs.append(song)
                        if len(songs) >= target:
                            return songs
            except Exception as e:
                print(f"[ERROR] Thread execution failed: {e}")

    return songs


# ================= ROUTES =================

@app.route("/", methods=["GET", "POST"])
def home():
    error = None
    playlist = []
    weather_info = None

    selected_language = "Hindi"
    selected_singer = SINGERS[0]
    selected_category = "All"
    selected_generation = "All"

    if request.method == "POST":
        city = request.form.get("city", "").strip()
        lat_str = request.form.get("lat", "").strip()
        lon_str = request.form.get("lon", "").strip()
        selected_language = request.form.get("language", "Hindi").strip()
        selected_singer = request.form.get("singer", SINGERS[0]).strip()
        selected_category = request.form.get("category", "All").strip()
        selected_generation = request.form.get("generation", "All").strip()

        if not city and not (lat_str and lon_str):
            city = "Mumbai"

        w = {}
        if city:
            w = get_weather(city)
        elif lat_str and lon_str:
            try:
                lat = float(lat_str)
                lon = float(lon_str)
                w = get_weather_by_coords(lat, lon)
                city = reverse_geocode(lat, lon) # set city based on GPS
            except ValueError:
                pass

        if "weather" in w:
            weather_main = w["weather"][0]["main"]
            season, month = season_month_from_weather(w)

            weather_info = {
                "city": w.get("name", city) or "Your Location",
                "weather": weather_main,
                "temp": w["main"]["temp"],
                "suggested": WEATHER_TO_CATEGORY.get(weather_main, "Chill"),
                "season": season,
                "month": month,
            }

            effective_category = selected_category
            if selected_category == "All" and weather_info.get("suggested"):
                effective_category = weather_info["suggested"]

            playlist = fetch_songs(
                selected_singer,
                selected_language,
                effective_category,
                selected_generation,
                target=40
            )

            if not playlist:
                error = "No songs found. (Check YouTube quota / key restrictions)."
        else:
            error = "City not found / Weather API error."

    return render_template(
        "index.html",
        singers=SINGERS,
        languages=LANGUAGES,
        categories=list(CATEGORIES.keys()),
        generations=list(GENERATIONS.keys()),
        selected_language=selected_language,
        selected_singer=selected_singer,
        selected_category=selected_category,
        selected_generation=selected_generation,
        playlist=playlist,
        weather_info=weather_info,
        error=error,
        year=datetime.now().year
    )


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    data = request.get_json(force=True)

    city = (data.get("city") or "").strip()
    singer = data.get("singer", SINGERS[0])
    language = data.get("language", "Hindi")
    category = data.get("category", "All")
    generation = data.get("generation", "All")
    target = int(data.get("target", 40))
    exclude_ids = data.get("exclude_ids", [])

    weather_info = None
    if city:
        w = get_weather(city)
        if "weather" in w:
            weather_main = w["weather"][0]["main"]
            season, month = season_month_from_weather(w)

            weather_info = {
                "city": w.get("name", city),
                "weather": weather_main,
                "temp": w["main"]["temp"],
                "suggested": WEATHER_TO_CATEGORY.get(weather_main, "Chill"),
                "season": season,
                "month": month,
            }

    effective_category = category
    if category == "All" and weather_info and weather_info.get("suggested"):
        effective_category = weather_info["suggested"]

    songs = fetch_songs(singer, language, effective_category, generation, target=target, exclude_ids=exclude_ids)

    return jsonify({"songs": songs, "weather_info": weather_info, "used_category": effective_category})


@app.route("/api/refresh_coords", methods=["POST"])
def api_refresh_coords():
    data = request.get_json(force=True)

    try:
        lat = float(data.get("lat"))
        lon = float(data.get("lon"))
    except (TypeError, ValueError):
        return jsonify({"songs": [], "weather_info": None, "error": "Invalid coordinates"}), 400

    singer = data.get("singer", SINGERS[0])
    language = data.get("language", "Hindi")
    category = data.get("category", "All")
    generation = data.get("generation", "All")
    target = int(data.get("target", 40))
    exclude_ids = data.get("exclude_ids", [])

    weather_info = None
    w = get_weather_by_coords(lat, lon)

    if "weather" in w:
        weather_main = w["weather"][0]["main"]
        exact_loc = reverse_geocode(lat, lon)
        season, month = season_month_from_weather(w)

        weather_info = {
            "city": w.get("name", "Your Location"),
            "location": exact_loc if exact_loc else w.get("name", "Your Location"),
            "weather": weather_main,
            "temp": w["main"]["temp"],
            "suggested": WEATHER_TO_CATEGORY.get(weather_main, "Chill"),
            "season": season,
            "month": month,
            "lat": lat,
            "lon": lon
        }

    effective_category = category
    if category == "All" and weather_info and weather_info.get("suggested"):
        effective_category = weather_info["suggested"]

    songs = fetch_songs(singer, language, effective_category, generation, target=target, exclude_ids=exclude_ids)

    return jsonify({"songs": songs, "weather_info": weather_info, "used_category": effective_category})


@app.route("/api/search_yt")
def api_search_yt():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "Query required"}), 400
    search_url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": q,
        "key": YOUTUBE_API_KEY,
        "maxResults": 5,
        "type": "video",
        "safeSearch": "moderate",
        "regionCode": "IN",
        "videoDuration": "medium",
    }
    try:
        data = yt_get(search_url, params)
        items = data.get("items", [])
        for it in items:
            vid = it.get("id", {}).get("videoId")
            if vid:
                title = it.get("snippet", {}).get("title", q)
                return jsonify({"video_id": vid, "title": title})
        return jsonify({"error": "No video found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)