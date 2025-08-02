from flask import Flask, request, jsonify, send_file
import yt_dlp
import os
import uuid
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DOWNLOADS = "downloads"
os.makedirs(DOWNLOADS, exist_ok=True)

# Railway'de ffmpeg global kurulu, bu satıra gerek yok:
FFMPEG_PATH = "ffmpeg"  # Gerekirse elle güncellenebilir


@app.route("/")
def home():
    return "✅ API aktif. Her şeyi İndir servisi çalışıyor."


@app.route("/indir", methods=["POST"])
def indir():
    url = request.json.get("url")
    if not url:
        return jsonify({"error": "URL eksik"}), 400

    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get("title", str(uuid.uuid4()))
            safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).rstrip()
            filename = f"{safe_title}.mp4"
            outpath = os.path.join(DOWNLOADS, filename)

        ydl_opts = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best",
            "merge_output_format": "mp4",
            "outtmpl": outpath,
            "quiet": True,
            "ffmpeg_location": FFMPEG_PATH
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        return send_file(outpath, as_attachment=False)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/ses-formatlari", methods=["POST"])
def ses_formatlari():
    url = request.json.get("url")
    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get("title", "ses")
            sesler = []
            for f in info.get("formats", []):
                if (
                    f.get("vcodec") == "none" and
                    f.get("ext") == "webm" and
                    f.get("acodec") != "none"
                ):
                    abr = f.get("abr", 0)
                    sesler.append({
                        "format_id": f["format_id"],
                        "abr": int(abr) if abr else None,
                        "title": title
                    })
            return jsonify({"formats": sesler})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/indir-mp3", methods=["POST"])
def indir_mp3():
    url = request.json.get("url")
    format_id = request.json.get("format_id")
    title = request.json.get("title", "indirilen")

    if not url or not format_id:
        return jsonify({"error": "Eksik bilgi"}), 400

    safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).rstrip()
    webm_path = os.path.join(DOWNLOADS, f"{uuid.uuid4()}.webm")
    mp3_path = os.path.join(DOWNLOADS, f"{safe_title}.mp3")

    ydl_opts = {
        "format": format_id,
        "outtmpl": webm_path,
        "quiet": True,
        "ffmpeg_location": FFMPEG_PATH
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        os.system(f'{FFMPEG_PATH} -i "{webm_path}" -vn -ab 192k "{mp3_path}"')
        return send_file(mp3_path, as_attachment=False)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Railway port ayarı:
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
