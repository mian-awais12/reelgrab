import glob
import os
import re
import tempfile
import uuid

import yt_dlp
from flask import Flask, jsonify, request, send_file, send_from_directory, after_this_request
from flask_cors import CORS

app = Flask(__name__, static_folder=".")
CORS(app)

DL_DIR = os.path.join(tempfile.gettempdir(), "reelgrab")
os.makedirs(DL_DIR, exist_ok=True)


@app.get("/")
def index():
    return send_from_directory(".", "index.html")


@app.post("/api/info")
def info():
    url = (request.get_json(silent=True) or {}).get("url", "").strip()
    if not re.match(r"^https?://", url):
        return jsonify(error="Enter a valid link starting with http:// or https://"), 400
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "noplaylist": True}) as ydl:
            d = ydl.extract_info(url, download=False)
    except Exception:
        return jsonify(error="Could not find a video at this link."), 400

    heights = sorted(
        {f["height"] for f in d.get("formats", []) if f.get("height") and f.get("vcodec") != "none"},
        reverse=True,
    )
    return jsonify(
        title=d.get("title"),
        thumbnail=d.get("thumbnail"),
        duration=d.get("duration"),
        heights=heights,
    )


@app.post("/api/download")
def download():
    j = request.get_json(silent=True) or {}
    url, kind, height = j.get("url", ""), j.get("kind", "video"), j.get("height")
    if not re.match(r"^https?://", url):
        return jsonify(error="Invalid link."), 400

    token = uuid.uuid4().hex
    opts = {"quiet": True, "noplaylist": True, "outtmpl": os.path.join(DL_DIR, token + ".%(ext)s")}
    if kind == "audio":
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
    else:
        opts["format"] = (
            f"bestvideo[height<={int(height)}]+bestaudio/best[height<={int(height)}]"
            if height else "bestvideo+bestaudio/best"
        )
        opts["merge_output_format"] = "mp4"

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            d = ydl.extract_info(url, download=True)
    except Exception:
        return jsonify(error="Download failed. The site may not allow it."), 400

    files = glob.glob(os.path.join(DL_DIR, token + ".*"))
    if not files:
        return jsonify(error="File was not created."), 500
    path = files[0]
    ext = os.path.splitext(path)[1]
    safe = re.sub(r'[\\/:*?"<>|]', "", d.get("title") or "video")[:80] or "video"

    @after_this_request
    def cleanup(resp):
        try:
            os.remove(path)
        except OSError:
            pass
        return resp

    return send_file(path, as_attachment=True, download_name=safe + ext)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
