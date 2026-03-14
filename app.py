import os
import sys
import io

# Fix Windows Unicode encoding issue (charmap codec error for emoji etc.)
if sys.stdout and hasattr(sys.stdout, 'encoding') and sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'encoding') and sys.stderr.encoding and sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
os.environ['PYTHONUTF8'] = '1'

import json
import time
import base64
import secrets
import requests
from datetime import datetime
from flask import (
    Flask, render_template, request, jsonify,
    session, redirect, url_for
)

# ─────────────────────────────────────────────
#  ██████  CONFIG – PASTE YOUR API KEYS HERE
# ─────────────────────────────────────────────
OPENWEATHER_API_KEY   = os.getenv("weather api key")     
SPOTIFY_CLIENT_ID     =  os.getenv("SPOTIFY_CLIENT_ID")        
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI  = os.getenv("SPOTIFY_REDIRECT_URI")

# Flask secret key – change this to a random string in production
SECRET_KEY = secrets.token_hex(32)

# Spotify OAuth scopes needed
SPOTIFY_SCOPES = (
    "streaming "
    "user-read-email "
    "user-read-private "
    "user-read-playback-state "
    "user-modify-playback-state "
    "user-read-currently-playing"
)

# ─────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = SECRET_KEY

# ─────────────────────────────────────────────
#  HELPER – WEATHER LOGIC
# ─────────────────────────────────────────────

# Dynamic mood logic using time of day and temperature instead of a static map

def get_season(month: int) -> str:
    if month in (12, 1, 2):
        return "Winter"
    elif month in (3, 4, 5):
        return "Summer"
    elif month in (6, 7, 8, 9):
        return "Monsoon"
    else:
        return "Autumn"

def parse_weather(data: dict) -> dict:
    weather_main = data["weather"][0]["main"]
    weather_desc = data["weather"][0]["description"].title()
    icon_code    = data["weather"][0]["icon"]
    temp_c       = round(data["main"]["temp"] - 273.15, 1)
    humidity     = data["main"]["humidity"]
    city         = data.get("name", "Unknown")
    country      = data.get("sys", {}).get("country", "")

    now    = datetime.now()
    month  = now.month
    month_name = now.strftime("%B")
    season = get_season(month)

    is_day = 'd' in icon_code
    mood, vibe = "Chill", "Every day is a music day 🎵"

    if weather_main == "Clear":
        if is_day:
            if temp_c > 35:
                mood, vibe = "Chill", "Too hot outside, chill inside 🥵"
            else:
                mood, vibe = "Party", "Sunny vibes, let's celebrate! ☀️"
        else:
            mood, vibe = "Romantic", "Clear starry night ✨"
    elif weather_main == "Clouds":
        if is_day:
            mood, vibe = "Chill", "Cloudy skies, cozy feels 🌥️"
        else:
            mood, vibe = "Sad", "Cloudy night, introspective vibes ☁️"
    elif weather_main in ("Rain", "Drizzle"):
        mood, vibe = "Romantic", "Rainy weather, perfect for love songs 🌧️"
    elif weather_main == "Thunderstorm":
        mood, vibe = "Workout", "Thunder energy! Go beast mode! ⚡"
    elif weather_main == "Snow":
        mood, vibe = "Classic", "Snowfall classics for a white winter 🌨️"
    elif weather_main in ("Mist", "Fog", "Haze"):
        if is_day:
            mood, vibe = "Chill", "Misty/Hazy day, relax and calm 🌫️"
        else:
            mood, vibe = "Sad", "Foggy night, lay back and think 🌁"
    elif weather_main in ("Smoke", "Dust", "Sand", "Ash"):
        mood, vibe = "Sad", "Dusty/Smoky atmosphere 🌪️"
    elif weather_main in ("Squall", "Tornado"):
        mood, vibe = "Workout", "Extreme weather, pump up the volume! 🌪️"

    return {
        "city"         : city,
        "country"      : country,
        "temperature"  : temp_c,
        "humidity"     : humidity,
        "condition"    : weather_main,
        "description"  : weather_desc,
        "icon_code"    : icon_code,
        "weather_icon" : f"https://openweathermap.org/img/wn/{icon_code}@2x.png",
        "month"        : month_name,
        "season"       : season,
        "mood"         : mood,
        "vibe"         : vibe,
    }

# ─────────────────────────────────────────────
#  HELPER – SPOTIFY AUTH
# ─────────────────────────────────────────────

def get_client_credentials_token():
    """Fallback token using Client Credentials (no user login needed for search)."""
    cached = session.get("cc_token")
    cached_exp = session.get("cc_token_exp", 0)
    if cached and time.time() < cached_exp:
        return cached

    creds = base64.b64encode(
        f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()
    ).decode()
    resp = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={"Authorization": f"Basic {creds}",
                 "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "client_credentials"},
        timeout=10,
    )
    if resp.status_code != 200:
        return None
    token_data = resp.json()
    session["cc_token"]     = token_data["access_token"]
    session["cc_token_exp"] = time.time() + token_data.get("expires_in", 3600) - 60
    return token_data["access_token"]

def get_user_token():
    """Return user OAuth access token, refreshing if expired."""
    access_token = session.get("access_token")
    expires_at   = session.get("token_expires_at", 0)

    if access_token and time.time() < expires_at:
        return access_token

    # Try refresh
    refresh_token = session.get("refresh_token")
    if not refresh_token:
        return None

    creds = base64.b64encode(
        f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()
    ).decode()
    resp = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={"Authorization": f"Basic {creds}",
                 "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        timeout=10,
    )
    if resp.status_code != 200:
        session.pop("access_token", None)
        return None

    token_data = resp.json()
    session["access_token"]     = token_data["access_token"]
    session["token_expires_at"] = time.time() + token_data.get("expires_in", 3600) - 60
    if "refresh_token" in token_data:
        session["refresh_token"] = token_data["refresh_token"]
    return token_data["access_token"]

def best_token():
    """Return user token if available, fall back to client credentials."""
    return get_user_token() or get_client_credentials_token()

# ─────────────────────────────────────────────
#  HELPER – BUILD SPOTIFY SEARCH QUERY
# ─────────────────────────────────────────────

MOOD_GENRE_MAP = {
    "Romantic" : ["romance", "love songs", "bollywood romantic"],
    "Party"    : ["party", "dance", "upbeat hits"],
    "Chill"    : ["chill", "lo-fi", "acoustic chill"],
    "Sad"      : ["sad songs", "heartbreak", "melancholic"],
    "Workout"  : ["workout", "pump up", "gym beats"],
    "Classic"  : ["classic hits", "timeless classics", "oldies"],
    "All"      : ["top hits", "popular"],
}

LANGUAGE_MAP = {
    "Hindi"   : "hindi",
    "English" : "english",
    "Tamil"   : "tamil",
    "Telugu"  : "telugu",
}

GENERATION_MAP = {
    "90s"         : "90s",
    "2000s"       : "2000s",
    "GenZ"        : "genz",
    "Trending"    : "trending",
    "New Release" : "new release 2024",
}

def build_search_query(mood, singer, language, generation, variant=0):
    genre_terms = MOOD_GENRE_MAP.get(mood, MOOD_GENRE_MAP["All"])
    # variant cycles through available genre terms to give different results on Refresh
    genre = genre_terms[variant % len(genre_terms)]

    parts = [genre]
    if language and language != "All":
        parts.append(LANGUAGE_MAP.get(language, language))
    
    # Ignore placeholders like 'any', 'all', 'any artist'
    if singer:
        s_lower = singer.lower().strip()
        if s_lower not in ("all", "any", "", "any artist"):
            parts.append(singer)
            
    if generation and generation != "All":
        parts.append(GENERATION_MAP.get(generation, generation))

    return " ".join(parts)

# ─────────────────────────────────────────────
#  ROUTES
# ─────────────────────────────────────────────

@app.route("/")
def home():
    return render_template("index.html")


# ── Weather ──────────────────────────────────

@app.route("/api/weather")
def api_weather():
    city = request.args.get("city", "").strip()
    lat  = request.args.get("lat")
    lon  = request.args.get("lon")

    if OPENWEATHER_API_KEY == "YOUR_OPENWEATHERMAP_API_KEY":
        return jsonify({"error": "OpenWeatherMap API key not configured. Please edit app.py and add your key."}), 503

    try:
        if city:
            url    = "https://api.openweathermap.org/data/2.5/weather"
            params = {"q": city, "appid": OPENWEATHER_API_KEY}
        elif lat and lon:
            url    = "https://api.openweathermap.org/data/2.5/weather"
            params = {"lat": lat, "lon": lon, "appid": OPENWEATHER_API_KEY}
        else:
            return jsonify({"error": "Provide 'city' or 'lat' and 'lon' query parameters."}), 400

        resp = requests.get(url, params=params, timeout=10)

        if resp.status_code == 404:
            return jsonify({"error": f"City '{city}' not found. Please check the spelling."}), 404
        if resp.status_code == 401:
            return jsonify({"error": "Invalid OpenWeatherMap API key."}), 401
        if resp.status_code == 429:
            return jsonify({"error": "Weather API rate limit reached. Please try again later."}), 429
        if resp.status_code != 200:
            return jsonify({"error": "Weather service unavailable."}), 502

        return jsonify(parse_weather(resp.json()))

    except requests.exceptions.ConnectionError:
        return jsonify({"error": "No internet connection."}), 503
    except requests.exceptions.Timeout:
        return jsonify({"error": "Weather request timed out."}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Music Recommendations ──────────────────

@app.route("/api/recommend")
def api_recommend():
    mood       = request.args.get("mood",       "Chill")
    singer     = request.args.get("singer",     "")
    language   = request.args.get("language",   "Hindi")
    generation = request.args.get("generation", "Trending")

    if SPOTIFY_CLIENT_ID == "YOUR_SPOTIFY_CLIENT_ID":
        return jsonify({"error": "Spotify API credentials not configured. Please edit app.py and add your keys."}), 503

    token = best_token()
    if not token:
        return jsonify({"error": "Could not obtain Spotify token. Check your Client ID and Secret."}), 503

    variant = int(request.args.get("variant", 0))
    query = build_search_query(mood, singer, language, generation, variant)

    try:
        def do_search(tok):
            return requests.get(
                "https://api.spotify.com/v1/search",
                headers={"Authorization": f"Bearer {tok}"},
                params={"q": query, "type": "track", "limit": 10, "market": "IN"},
                timeout=10,
            )

        resp = do_search(token)

        if resp.status_code == 401:
            # Token expired – clear and retry once
            session.pop("access_token", None)
            session.pop("cc_token",     None)
            token = best_token()
            if token:
                resp = do_search(token)
            else:
                return jsonify({"error": "Spotify authentication failed."}), 401

        if resp.status_code == 429:
            return jsonify({"error": "Spotify rate limit reached."}), 429

        if resp.status_code == 403 and "registered" in resp.text.lower():
            session.clear()
            return jsonify({"error": "Dashboard Email Error: The Spotify account you logged in with doesn't match the one in your Dashboard. Please open an Incognito window and login again."}), 403

        if resp.status_code != 200:
            return jsonify({"error": f"Search failed: {resp.text}"}), 502

        items = resp.json().get("tracks", {}).get("items", [])

        # ── Deduplicate by normalized (name + primary artist) ──
        seen   = set()
        tracks = []
        for item in items:
            primary_artist = (item.get("artists") or [{}])[0].get("name", "").lower().strip()
            norm_key       = (item["name"].lower().strip(), primary_artist)
            if norm_key in seen:
                continue
            seen.add(norm_key)

            album_images = item.get("album", {}).get("images", [])
            album_art    = album_images[0]["url"] if album_images else ""
            artists      = ", ".join(a["name"] for a in item.get("artists", []))
            duration_ms  = item.get("duration_ms", 0)
            duration_s   = duration_ms // 1000
            duration_fmt = f"{duration_s // 60}:{duration_s % 60:02d}"

            tracks.append({
                "id"          : item["id"],
                "name"        : item["name"],
                "artists"     : artists,
                "album"       : item.get("album", {}).get("name", ""),
                "album_art"   : album_art,
                "duration"    : duration_fmt,
                "duration_ms" : duration_ms,
                "preview_url" : item.get("preview_url"),
                "uri"         : item.get("uri"),
                "external_url": item.get("external_urls", {}).get("spotify", ""),
            })

            if len(tracks) == 10:
                break

        return jsonify({"tracks": tracks, "query": query})

    except requests.exceptions.Timeout:
        return jsonify({"error": "Spotify request timed out."}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Single Song Search ────────────────────────

@app.route("/api/search_single")
def api_search_single():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "Query parameter 'q' is required."}), 400

    token = best_token()
    if not token:
        return jsonify({"error": "Could not obtain Spotify token."}), 503

    try:
        resp = requests.get(
            "https://api.spotify.com/v1/search",
            headers={"Authorization": f"Bearer {token}"},
            params={"q": q, "type": "track", "limit": 1, "market": "IN"},
            timeout=10,
        )

        if resp.status_code == 401:
            session.pop("access_token", None)
            session.pop("cc_token", None)
            token = best_token()
            if token:
                resp = requests.get(
                    "https://api.spotify.com/v1/search",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"q": q, "type": "track", "limit": 1, "market": "IN"},
                    timeout=10,
                )
            else:
                return jsonify({"error": "Spotify authentication failed."}), 401

        if resp.status_code == 429:
            return jsonify({"error": "Spotify rate limit reached."}), 429

        if resp.status_code != 200:
            return jsonify({"error": f"Search failed: {resp.text}"}), 502

        items = resp.json().get("tracks", {}).get("items", [])
        if not items:
            return jsonify({"error": f"No track found for '{q}'"}), 404

        item = items[0]
        album_images = item.get("album", {}).get("images", [])
        album_art    = album_images[0]["url"] if album_images else ""
        artists      = ", ".join(a["name"] for a in item.get("artists", []))
        duration_ms  = item.get("duration_ms", 0)
        duration_s   = duration_ms // 1000
        duration_fmt = f"{duration_s // 60}:{duration_s % 60:02d}"

        track = {
            "id"          : item["id"],
            "name"        : item["name"],
            "artists"     : artists,
            "album"       : item.get("album", {}).get("name", ""),
            "album_art"   : album_art,
            "duration"    : duration_fmt,
            "duration_ms" : duration_ms,
            "preview_url" : item.get("preview_url"),
            "uri"         : item.get("uri"),
            "external_url": item.get("external_urls", {}).get("spotify", ""),
        }
        return jsonify({"track": track})

    except requests.exceptions.Timeout:
        return jsonify({"error": "Spotify request timed out."}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Spotify OAuth ────────────────────────────

@app.route("/login")
def login():
    if SPOTIFY_CLIENT_ID == "YOUR_SPOTIFY_CLIENT_ID":
        return jsonify({"error": "Spotify credentials not configured."}), 503

    state = secrets.token_hex(16)
    session["oauth_state"] = state

    params = {
        "response_type": "code",
        "client_id"    : SPOTIFY_CLIENT_ID,
        "scope"        : SPOTIFY_SCOPES,
        "redirect_uri" : SPOTIFY_REDIRECT_URI,
        "state"        : state,
        "show_dialog"  : "false",
    }
    auth_url = "https://accounts.spotify.com/authorize?" + "&".join(
        f"{k}={requests.utils.quote(str(v))}" for k, v in params.items()
    )
    return redirect(auth_url)

@app.route("/callback")
def callback():
    error = request.args.get("error")
    if error:
        return redirect(f"/?auth=error&msg={error}")

    code  = request.args.get("code", "")
    state = request.args.get("state", "")

    if state != session.get("oauth_state"):
        return redirect("/?auth=error&msg=state_mismatch")

    creds = base64.b64encode(
        f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()
    ).decode()

    try:
        resp = requests.post(
            "https://accounts.spotify.com/api/token",
            headers={"Authorization": f"Basic {creds}",
                     "Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type"  : "authorization_code",
                "code"        : code,
                "redirect_uri": SPOTIFY_REDIRECT_URI,
            },
            timeout=10,
        )
        if resp.status_code != 200:
            return redirect(f"/?auth=error&msg=token_exchange_failed")

        token_data = resp.json()
        session["access_token"]     = token_data["access_token"]
        session["refresh_token"]    = token_data.get("refresh_token", "")
        session["token_expires_at"] = time.time() + token_data.get("expires_in", 3600) - 60

        # Fetch user profile
        profile_resp = requests.get(
            "https://api.spotify.com/v1/me",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
            timeout=10,
        )
        if profile_resp.status_code != 200:
            return redirect(f"/?auth=error&msg=Profile fetch failed: {profile_resp.text}")
            
        profile = profile_resp.json()
        session["user_name"]   = profile.get("display_name", "Listener")
        session["user_image"]  = (profile.get("images") or [{}])[0].get("url", "")
        session["user_product"]= profile.get("product", "free")  # "premium" or "free"

        return redirect("/?auth=success")

    except Exception as e:
        return redirect(f"/?auth=error&msg={str(e)}")

# ── Token Endpoint (for Spotify SDK) ────────

@app.route("/api/token")
def api_token():
    token = get_user_token()
    if not token:
        return jsonify({"error": "Not authenticated"}), 401
    return jsonify({
        "access_token" : token,
        "product"      : session.get("user_product", "free"),
    })

# ── User Info ────────────────────────────────

@app.route("/api/me")
def api_me():
    if not session.get("access_token"):
        return jsonify({"logged_in": False})
    return jsonify({
        "logged_in"   : True,
        "name"        : session.get("user_name", "Listener"),
        "image"       : session.get("user_image", ""),
        "product"     : session.get("user_product", "free"),
    })

# ── Logout ──────────────────────────────────

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ── Player Proxy (optional for Spotify Web API control) ─────

@app.route("/api/player", methods=["POST"])
def api_player():
    token = get_user_token()
    if not token:
        return jsonify({"error": "Not authenticated"}), 401

    action  = request.json.get("action")   # play, pause, next, previous, volume
    payload = request.json.get("payload", {})

    endpoints = {
        "play"    : ("PUT",  "https://api.spotify.com/v1/me/player/play"),
        "pause"   : ("PUT",  "https://api.spotify.com/v1/me/player/pause"),
        "next"    : ("POST", "https://api.spotify.com/v1/me/player/next"),
        "previous": ("POST", "https://api.spotify.com/v1/me/player/previous"),
        "volume"  : ("PUT",  "https://api.spotify.com/v1/me/player/volume"),
    }

    if action not in endpoints:
        return jsonify({"error": "Unknown action"}), 400

    method, url = endpoints[action]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    try:
        params = {}
        body   = None
        if action == "volume":
            params = {"volume_percent": payload.get("volume_percent", 50)}
        elif action == "play" and payload:
            device_id = payload.pop("device_id", None)
            if device_id:
                params["device_id"] = device_id
            if payload:
                body = json.dumps(payload)

        resp = requests.request(method, url, headers=headers, params=params, data=body, timeout=10)

        if resp.status_code in (200, 204):
            return jsonify({"status": "ok"})
        return jsonify({"error": resp.text}), resp.status_code

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":


    print("\n" + "=" * 55)
    print("  [*] Moodwave Music Player")
    print("=" * 55)
    print("  >> Open:  http://localhost:5000")
    print()
    print("  [!] Before starting, make sure you have set:")
    print("      OPENWEATHER_API_KEY      (app.py line 16)")
    print("      SPOTIFY_CLIENT_ID        (app.py line 17)")
    print("      SPOTIFY_CLIENT_SECRET    (app.py line 18)")
    print("      Redirect URI in Spotify Dashboard:")
    print("      http://localhost:5000/callback")
    print("=" * 55 + "\n")
    app.run(debug=True, host="0.0.0.0", port=5000)

