from flask import Flask, request, jsonify, send_file, render_template
import yt_dlp
import os
import uuid
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DOWNLOADS = "downloads"
os.makedirs(DOWNLOADS, exist_ok=True)

@app.route("/")
def home():
    return render_template("index.html")

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
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
            "outtmpl": outpath,
            "quiet": True,
            "nocheckcertificate": True
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        return send_file(outpath, as_attachment=False)

    except yt_dlp.utils.DownloadError as e:
        if "Sign in to confirm your age" in str(e):
            return jsonify({"error": "Bu video YouTube tarafından yaş sınırlaması ile korunuyor. İndirme için oturum gerekli olduğu için desteklenmemektedir."}), 403
        else:
            return jsonify({"error": str(e)}), 500

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
        "quiet": True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        os.system(f'ffmpeg -i "{webm_path}" -vn -ab 192k "{mp3_path}"')

        return send_file(mp3_path, as_attachment=False)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
