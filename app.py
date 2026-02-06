# app.py
from flask import Flask, render_template, request, send_file, jsonify
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import yt_dlp
import os
import re
import zipfile
import uuid
import shutil
from threading import Thread

app = Flask(__name__)
app.secret_key = 'change-me-in-production'

# ── FFmpeg location ───────────────────────────────────────────────
FFMPEG_PATH = r"E:\Project\spotify-downloader\ffmpeg\bin"  # Change to your FFmpeg bin path

# ── Spotify API credentials ───────────────────────────────────────
CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "13572b1bb7ad4ce3b6a6633809aa7c89")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "642f1ebedfca4969a47f0978f29d041a")

sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET
))

# ── State for bulk progress ───────────────────────────────────────
download_progress = {}  # {progress_id: {total, completed, current_song, status, failed[]}}


def extract_playlist_id(url: str):
    if not url:
        return None
    m = re.search(r"(?:playlist/|playlist:)([a-zA-Z0-9]+)", url)
    return m.group(1) if m else None


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1F]', '', name)
    name = name.strip().rstrip('.')
    return name[:180] if len(name) > 180 else name


def get_all_playlist_tracks(playlist_id: str):
    songs = []
    limit = 100
    offset = 0
    while True:
        page = sp.playlist_items(
            playlist_id,
            offset=offset,
            limit=limit,
            fields="items(track(name,artists(name))),next"
        )
        for item in page.get("items", []):
            tr = item.get("track")
            if not tr:
                continue
            title = tr.get("name") or ""
            artists = ", ".join(a["name"] for a in (tr.get("artists") or []) if a and a.get("name"))
            if not title or not artists:
                continue
            songs.append({"title": title, "artist": artists})
        if not page.get("next"):
            break
        offset += limit
    return songs


def fetch_playlist_info(playlist_url: str):
    playlist_id = extract_playlist_id(playlist_url)
    if not playlist_id:
        return None, "Invalid Spotify playlist URL."

    try:
        meta = sp.playlist(playlist_id, fields="name,description")
        tracks = get_all_playlist_tracks(playlist_id)

        songs = []
        for idx, tr in enumerate(tracks, start=1):
            title = tr["title"]
            artist = tr["artist"]
            human_name = f"{title} - {artist}"
            filename = sanitize_filename(human_name) + ".mp3"
            search_query = f"{title} {artist} official audio"
            songs.append({
                "id": idx,
                "title": title,
                "artist": artist,
                "search_query": search_query,
                "filename": filename
            })

        return {
            "name": meta.get("name", "Playlist"),
            "description": meta.get("description") or "",
            "songs": songs,
            "total": len(songs)
        }, None

    except spotipy.exceptions.SpotifyException as e:
        if getattr(e, "http_status", None) == 403:
            return None, "Playlist is private."
        return None, f"Spotify error: {e}"


def download_single_song(song_query: str, output_folder: str, desired_filename: str):
    os.makedirs(output_folder, exist_ok=True)
    safe_name = sanitize_filename(os.path.splitext(desired_filename)[0])
    outtmpl = os.path.join(output_folder, safe_name + ".%(ext)s")

    ydl_opts = {
        "ffmpeg_location": FFMPEG_PATH,
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "default_search": "ytsearch",
        "outtmpl": outtmpl,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([song_query])
        final_path = os.path.join(output_folder, safe_name + ".mp3")
        if not os.path.exists(final_path):
            produced = [f for f in os.listdir(output_folder) if f.startswith(safe_name + ".")]
            if produced:
                final_path = os.path.join(output_folder, produced[0])
            else:
                return False, "File was not produced."
        return True, final_path
    except Exception as e:
        return False, str(e)


def download_songs_with_progress(songs, folder, progress_id):
    download_progress[progress_id] = {
        "total": len(songs),
        "completed": 0,
        "current_song": "",
        "status": "downloading",
        "failed": []
    }

    os.makedirs(folder, exist_ok=True)

    for song in songs:
        current = f"{song['title']} - {song['artist']}"
        download_progress[progress_id]["current_song"] = current
        ok, result = download_single_song(song["search_query"], folder, song["filename"])
        if ok:
            download_progress[progress_id]["completed"] += 1
        else:
            download_progress[progress_id]["failed"].append({
                "song": current,
                "error": result
            })

    download_progress[progress_id]["status"] = "completed"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/fetch-playlist", methods=["POST"])
def api_fetch_playlist():
    data = request.get_json(force=True) or {}
    playlist_url = (data.get("url") or "").strip()
    if not playlist_url:
        return jsonify({"error": "No URL provided"}), 400

    info, err = fetch_playlist_info(playlist_url)
    if err:
        return jsonify({"error": err}), 400
    return jsonify(info)


@app.route("/api/download-single", methods=["POST"])
def api_download_single():
    data = request.get_json(force=True) or {}
    query = data.get("query")
    filename = data.get("filename")
    title = data.get("title")
    artist = data.get("artist")

    if not query or not filename:
        return jsonify({"error": "Missing query or filename"}), 400

    temp_folder = f"temp_single_{uuid.uuid4().hex}"
    try:
        ok, result = download_single_song(query, temp_folder, filename)
        if not ok:
            return jsonify({"error": f"Download failed: {result}"}), 500

        path = result
        human_name = sanitize_filename(f"{title or ''} - {artist or ''}".strip(" -")) or "song"
        download_name = human_name + ".mp3"

        response = send_file(path, as_attachment=True, download_name=download_name)

        @response.call_on_close
        def _cleanup():
            shutil.rmtree(temp_folder, ignore_errors=True)

        return response
    except Exception as e:
        shutil.rmtree(temp_folder, ignore_errors=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/download-all", methods=["POST"])
def api_download_all():
    data = request.get_json(force=True) or {}
    songs = data.get("songs") or []
    if not songs:
        return jsonify({"error": "No songs provided"}), 400

    progress_id = uuid.uuid4().hex
    folder = f"songs_{progress_id}"

    Thread(target=download_songs_with_progress, args=(songs, folder, progress_id), daemon=True).start()

    return jsonify({"progress_id": progress_id})


@app.route("/api/download-progress/<progress_id>")
def api_download_progress(progress_id):
    prog = download_progress.get(progress_id)
    if not prog:
        return jsonify({"error": "Invalid progress ID"}), 404
    return jsonify(prog)


@app.route("/api/download-zip/<progress_id>")
def api_download_zip(progress_id):
    prog = download_progress.get(progress_id)
    if not prog:
        return jsonify({"error": "Invalid progress ID"}), 404
    if prog["status"] != "completed":
        return jsonify({"error": "Download not completed yet"}), 400

    folder = f"songs_{progress_id}"
    zip_path = f"{folder}.zip"

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for root, _, files in os.walk(folder):
                for f in files:
                    z.write(os.path.join(root, f), arcname=f)

        response = send_file(zip_path, as_attachment=True, download_name="playlist_songs.zip")

        @response.call_on_close
        def _cleanup():
            shutil.rmtree(folder, ignore_errors=True)
            os.remove(zip_path)
            download_progress.pop(progress_id, None)

        return response
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)
