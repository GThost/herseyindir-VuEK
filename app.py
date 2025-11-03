from flask import Flask, request, jsonify, send_file, render_template, Response
from flask_cors import CORS
import yt_dlp
import os, uuid, time, glob, subprocess, sys

app = Flask(__name__)

# CORS
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=False)

@app.after_request
def add_cors_headers(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp

@app.route("/<path:_any>", methods=["OPTIONS"])
def cors_preflight(_any):
    return ("", 204)

# Teşhis logları
print("yt-dlp version:", getattr(yt_dlp, "version", None) and yt_dlp.version.__version__, flush=True)
try:
    ff_out = subprocess.check_output(["ffmpeg", "-version"]).decode().splitlines()[0]
    print(ff_out, flush=True)
except Exception as e:
    print("FFmpeg NOT FOUND:", e, flush=True)

TMPDIR = "/tmp/kgdl"
os.makedirs(TMPDIR, exist_ok=True)

def _safe_title(t):
    t = t or str(uuid.uuid4())
    return "".join(c for c in t if c.isalnum() or c in (" ", "-", "_")).rstrip()

def _ffmpeg_available():
    try:
        subprocess.check_output(["ffmpeg", "-version"])
        return True
    except Exception:
        return False

def _get_url_from_request():
    if request.is_json:
        data = request.get_json(silent=True) or {}
        u = (data.get("url") or "").strip()
        if u: return u
    return (request.form.get("url") or request.args.get("url") or "").strip()

def _normalize_youtube_url(u: str) -> str:
    try:
        from urllib.parse import urlparse, parse_qs
        u = u.strip()
        p = urlparse(u)
        if "youtu.be" in p.netloc:
            vid = p.path.strip("/").split("/")[0]
            return f"https://www.youtube.com/watch?v={vid}"
        if p.path.startswith("/shorts/") or p.path.startswith("/embed/") or p.path.startswith("/live/"):
            vid = p.path.split("/")[2] if p.path.count("/") >= 2 else p.path.split("/")[1]
            return f"https://www.youtube.com/watch?v={vid}"
        qs = parse_qs(p.query)
        if "v" in qs:
            return f"https://www.youtube.com/watch?v={qs['v'][0]}"
        return u
    except Exception:
        return u

def _common_ydl_opts(outtmpl_base):
    opts = {
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
        "noplaylist": True,
        "quiet": True,
        "concurrent_fragment_downloads": 1,
        "outtmpl": outtmpl_base,
        "retries": 3,
        "fragment_retries": 3,
        "nocheckcertificate": True,
        "prefer_ffmpeg": True,
    }
    if os.path.exists("cookies.txt"):
        opts["cookiefile"] = "cookies.txt"
        opts["extractor_args"] = {"youtube": {"player_client": ["web"]}}
    return opts

# ---------- ROUTES ----------

@app.route("/ping")
def ping():
    return "pong", 200

# ✅ Ana sayfa: SADECE index.html render eder (fallback yok!)
@app.route("/")
def home():
    return render_template("index.html")

# ✅ Test sayfası: ana sayfayı bozmadan burada deney yap
@app.route("/test")
def test():
    html = """
<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>KG Test – Downloader</title>
<style>
body{font-family:system-ui;background:#0b1220;color:#e6eefc;display:grid;place-items:center;min-height:100vh;margin:0}
.card{width:min(720px,92vw);background:#121a2e;border:1px solid #21304f;border-radius:16px;padding:20px;box-shadow:0 10px 30px rgba(0,0,0,.3)}
h1{margin:0 0 10px;color:#8efc8a}
input{width:100%;padding:12px;border-radius:10px;border:1px solid #2b3b61;background:#0e1628;color:#fff}
.row{display:flex;gap:8px;margin:12px 0}
button{flex:1;padding:12px;border:0;border-radius:10px;cursor:pointer}
.g{background:#2ecc71;color:#082015}
.b{background:#4aa3ff;color:#061225}
.btn{display:block;width:100%;margin-top:8px;background:#22335a;color:#d6e6ff}
small{opacity:.8}
#msg{margin-top:8px;font-weight:600}
</style>
<div class="card">
  <h1>KG Test – Downloader</h1>
  <small>Bu sayfa same-origin; POST çağrıları log'a düşer.</small>
  <input id="url" placeholder="YouTube URL (https://youtu.be/...)" />
  <div class="row">
    <button class="g" id="mp4Btn">🎬 MP4 İndir</button>
    <button class="b" id="mp3Btn">🎵 MP3 Formatları</button>
  </div>
  <div id="formats"></div>
  <div id="msg"></div>
</div>
<script>
const msg = (s, ok=null)=>{
  const el = document.getElementById("msg");
  el.textContent = s||"";
  el.style.color = ok===true ? "#8efc8a" : ok===false ? "#ff7a7a" : "#e6eefc";
};
function downloadBlob(blob, name){
  const a=document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name||"download";
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(()=>URL.revokeObjectURL(a.href),1500);
}
function norm(u){
  try{
    const url = new URL(u.trim());
    if(url.hostname.includes("youtu.be")){
      const id = url.pathname.replace(/^\\/+/,"").split("/")[0];
      return "https://www.youtube.com/watch?v="+id;
    }
    if(url.pathname.startsWith("/shorts/") || url.pathname.startsWith("/embed/") || url.pathname.startsWith("/live/")){
      const id = url.pathname.split("/")[2] || url.pathname.split("/")[1];
      return "https://www.youtube.com/watch?v="+id;
    }
    const v = url.searchParams.get("v");
    return v ? "https://www.youtube.com/watch?v="+v : u.trim();
  }catch{ return u.trim(); }
}
document.getElementById("mp4Btn").onclick = async ()=>{
  try{
    msg("⏳ MP4 indiriliyor...");
    const u = norm(document.getElementById("url").value);
    const r = await fetch("/indir", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ url: u })
    });
    if(!r.ok){ msg("❌ MP4 hata: "+await r.text(), false); return; }
    const blob = await r.blob();
    downloadBlob(blob, "video.mp4");
    msg("✅ MP4 indirildi.", true);
  }catch(e){ msg("❌ MP4 fetch hata: "+e.message, false); }
};
document.getElementById("mp3Btn").onclick = async ()=>{
  try{
    msg("⏳ Ses formatları alınıyor...");
    const u = norm(document.getElementById("url").value);
    const r = await fetch("/ses-formatlari", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ url: u })
    });
    if(!r.ok){ msg("❌ Format hatası: "+await r.text(), false); return; }
    const data = await r.json();
    const list = (data.formats||[]).filter(f=>f.abr).sort((a,b)=>(b.abr||0)-(a.abr||0));
    const box = document.getElementById("formats"); box.innerHTML="";
    if(!list.length){ msg("❌ Ses formatı bulunamadı.", false); return; }
    msg("🎧 Bitrate seç:");
    list.forEach(f=>{
      const b=document.createElement("button");
      b.className="btn";
      b.textContent=(f.abr||"?")+" kbps";
      b.onclick = async ()=>{
        try{
          msg("⏳ MP3 hazırlanıyor...");
          const r2 = await fetch("/indir-mp3", {
            method:"POST",
            headers:{"Content-Type":"application/json"},
            body: JSON.stringify({ url: u, format_id: String(f.format_id), title: f.title||"audio" })
          });
          if(!r2.ok){ msg("❌ MP3 hata: "+await r2.text(), false); return; }
          const blob = await r2.blob();
          const safe=(f.title||"audio").replace(/[\\\\/:*?"<>|]/g,"").trim()||"audio";
          downloadBlob(blob, safe+".mp3");
          msg("✅ MP3 indirildi.", true);
        }catch(e){ msg("❌ MP3 fetch hata: "+e.message, false); }
      };
      box.appendChild(b);
    });
  }catch(e){ msg("❌ Format hata: "+e.message, false); }
};
</script>
"""
    return Response(html, mimetype="text/html")

@app.route("/ses-formatlari", methods=["POST"])
def ses_formatlari():
    print("POST /ses-formatlari", request.json if request.is_json else dict(request.form), flush=True)
    url = _normalize_youtube_url(_get_url_from_request())
    if not url:
        return jsonify({"formats": [], "error": "URL eksik"}), 400
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "noplaylist": True, **({"cookiefile": "cookies.txt"} if os.path.exists("cookies.txt") else {})}) as ydl:
            info = ydl.extract_info(url, download=False)
        title = info.get("title", "audio")
        sesler = []
        for f in info.get("formats", []):
            if f.get("vcodec") == "none" and f.get("acodec") != "none":
                sesler.append({"format_id": f["format_id"], "abr": int(f.get("abr", 0) or 0) or None, "ext": f.get("ext"), "title": title})
        sesler.sort(key=lambda x: (x["abr"] or 0), reverse=True)
        return jsonify({"formats": sesler})
    except yt_dlp.utils.DownloadError as e:
        s = str(e)
        if "Sign in to confirm you're not a bot" in s or "confirm your age" in s or "age" in s.lower():
            return jsonify({"error": "YouTube bu içerik için giriş/yaş doğrulaması istiyor. cookies.txt olmadan indirilemez."}), 403
        return jsonify({"error": s}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/indir", methods=["POST"])
def indir():
    print("POST /indir", request.json if request.is_json else dict(request.form), flush=True)
    url = _normalize_youtube_url(_get_url_from_request())
    if not url:
        return jsonify({"error": "URL eksik"}), 400
    stamp = int(time.time() * 1000)
    base = os.path.join(TMPDIR, f"kg_{stamp}")
    outtmpl = base + ".%(ext)s"
    ydl_opts = _common_ydl_opts(outtmpl)
    ydl_opts.update({"format": "bv*+ba/best", "merge_output_format": "mp4"})
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = _safe_title(info.get("title"))
        cand = sorted(glob.glob(base + ".*"), key=os.path.getmtime)
        if not cand:
            return jsonify({"error": "Çıktı dosyası bulunamadı"}), 500
        mp4s = [p for p in cand if p.lower().endswith(".mp4")]
        outpath = (mp4s[-1] if mp4s else cand[-1])
        return send_file(outpath, as_attachment=False, download_name=f"{title}.mp4")
    except yt_dlp.utils.DownloadError as e:
        s = str(e)
        if "Sign in to confirm you're not a bot" in s or "confirm your age" in s or "age" in s.lower():
            return jsonify({"error": "Video giriş/yaş doğrulaması istiyor. cookies.txt olmadan indirilemez."}), 403
        if "Private" in s or "copyright" in s.lower():
            return jsonify({"error": "Video erişime kapalı veya telif korumalı."}), 403
        return jsonify({"error": s}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/indir-mp3", methods=["POST"])
def indir_mp3():
    print("POST /indir-mp3", request.json if request.is_json else dict(request.form), flush=True)
    if not _ffmpeg_available():
        return jsonify({"error": "FFmpeg bulunamadı. Sunucuda MP3 dönüştürme yapılamaz."}), 500
    url = _normalize_youtube_url(_get_url_from_request())
    format_id = None; title = "audio"
    if request.is_json:
        body = request.get_json(silent=True) or {}
        format_id = body.get("format_id")
        title = _safe_title(body.get("title", "audio"))
    else:
        format_id = request.form.get("format_id")
        title = _safe_title(request.form.get("title", "audio"))
    if not url or not format_id:
        return jsonify({"error": "Eksik bilgi"}), 400
    stamp = int(time.time() * 1000)
    base = os.path.join(TMPDIR, f"kg_{stamp}")
    outtmpl = base + ".%(ext)s"
    ydl_opts = _common_ydl_opts(outtmpl)
    ydl_opts.update({
        "format": str(format_id),
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "0"}],
    })
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        mp3_path = base + ".mp3"
        if not os.path.exists(mp3_path):
            mp3s = sorted(glob.glob(base + ".mp3") + glob.glob(base + "*.mp3"), key=os.path.getmtime)
            if not mp3s: return jsonify({"error": "MP3 oluşturulamadı (FFmpeg/postprocessor)."}), 500
            mp3_path = mp3s[-1]
        return send_file(mp3_path, as_attachment=False, download_name=f"{title}.mp3")
    except yt_dlp.utils.DownloadError as e:
        s = str(e)
        if "Sign in to confirm you're not a bot" in s or "confirm your age" in s or "age" in s.lower():
            return jsonify({"error": "Video giriş/yaş doğrulaması istiyor. cookies.txt olmadan indirilemez."}), 403
        return jsonify({"error": s}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
