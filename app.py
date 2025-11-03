from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import yt_dlp
import os, uuid, time, glob

app = Flask(__name__)
CORS(app)

# Sağlık testi için
@app.route("/ping")
def ping():
    return "pong", 200

# Railway'de güvenli yazma alanı
TMPDIR = "/tmp/kgdl"
os.makedirs(TMPDIR, exist_ok=True)

@app.route("/")
def home():
    try:
        return render_template("index.html")
    except Exception:
        return "KATAR GLOBAL Downloader", 200

def _safe_title(t):
    t = t or str(uuid.uuid4())
    return "".join(c for c in t if c.isalnum() or c in (" ", "-", "_")).rstrip()

def _common_ydl_opts(outtmpl_base):
    return {
        "extractor_args": {"youtube": {"player_client": ["android","web"]}},
        "noplaylist": True,
        "quiet": True,
        "concurrent_fragment_downloads": 1,
        "outtmpl": outtmpl_base,
        "retries": 3,
        "fragment_retries": 3,
        "nocheckcertificate": True,
    }

@app.route("/indir", methods=["POST"])
def indir():
    print("POST /indir", request.json, flush=True)  # ✅ Log için eklendi

    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "URL eksik"}), 400

    stamp = int(time.time()*1000)
    base = os.path.join(TMPDIR, f"kg_{stamp}")
    outtmpl = base + ".%(ext)s"

    ydl_opts = _common_ydl_opts(outtmpl)
    ydl_opts.update({
        "format": "bv*+ba/best",
        "merge_output_format": "mp4",
    })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = _safe_title(info.get("title"))
        cand = sorted(glob.glob(base + ".*"), key=os.path.getmtime)
        if not cand:
            return jsonify({"error": "Çıktı dosyası bulunamadı"}), 500
        mp4s = [p for p in cand if p.lower().endswith(".mp4")]
        outpath = (mp4s[-1] if mp4s else cand[-1])

        return send_file(outpath, as_attachment=False,
                         download_name=f"{title}.mp4")
    except yt_dlp.utils.DownloadError as e:
        s = str(e)
        if "Sign in to confirm your age" in s or "age" in s.lower():
            return jsonify({"error": "Video 18+ yaş doğrulaması istiyor, sunucudan indirilemez."}), 403
        if "Private" in s or "copyright" in s.lower():
            return jsonify({"error": "Video erişime kapalı veya telif korumalı."}), 403
        return jsonify({"error": s}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/ses-formatlari", methods=["POST"])
def ses_formatlari():
    print("POST /ses-formatlari", request.json, flush=True)  # ✅ Log

    data = request.json or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "URL eksik"}), 400
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "noplaylist": True}) as ydl:
            info = ydl.extract_info(url, download=False)
        title = info.get("title", "audio")
        sesler = []
        for f in info.get("formats", []):
            if f.get("vcodec") == "none" and f.get("acodec") != "none":
                sesler.append({
                    "format_id": f["format_id"],
                    "abr": int(f.get("abr", 0) or 0) or None,
                    "ext": f.get("ext"),
                    "title": title
                })
        sesler.sort(key=lambda x: (x["abr"] or 0), reverse=True)
        return jsonify({"formats": sesler})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/indir-mp3", methods=["POST"])
def indir_mp3():
    print("POST /indir-mp3", request.json, flush=True)  # ✅ Log

    data = request.json or {}
    url = (data.get("url") or "").strip()
    format_id = data.get("format_id")
    title = _safe_title(data.get("title", "audio"))

    if not url or not format_id:
        return jsonify({"error": "Eksik bilgi"}), 400

    stamp = int(time.time()*1000)
    base = os.path.join(TMPDIR, f"kg_{stamp}")
    outtmpl = base + ".%(ext)s"

    ydl_opts = _common_ydl_opts(outtmpl)
    ydl_opts.update({
        "format": str(format_id),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "0"
        }],
    })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        mp3s = sorted(glob.glob(base + ".mp3"), key=os.path.getmtime)
        if not mp3s:
            return jsonify({"error": "MP3 oluşturulamadı (FFmpeg var mı?)."}), 500
        mp3_path = mp3s[-1]
        return send_file(mp3_path, as_attachment=False,
                         download_name=f"{title}.mp3")
    except yt_dlp.utils.DownloadError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
