"""GoonHub downloader API. Public, extractable media only; no account credentials.

Run only on a trusted host or behind a rate-limited HTTPS proxy. See README.md.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

try:
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError
except ImportError:  # Unit tests can monkeypatch extraction without yt-dlp installed.
    YoutubeDL = None
    DownloadError = Exception

APP_VERSION = "1.0.2"
logger = logging.getLogger("goonhub.extractor")
ALLOWED_HOSTS = {
    "x": {"x.com", "www.x.com", "mobile.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com"},
    "instagram": {"instagram.com", "www.instagram.com", "m.instagram.com"},
    "facebook": {"facebook.com", "www.facebook.com", "m.facebook.com", "web.facebook.com", "fb.watch", "www.fb.watch"},
}
MAX_ITEMS = 12
MAX_BYTES = int(os.getenv("GOONHUB_MAX_BYTES", str(350 * 1024 * 1024)))
TTL = int(os.getenv("GOONHUB_TTL_SECONDS", "1800"))
ALLOWED_ORIGINS = [x.strip() for x in os.getenv("GOONHUB_ORIGINS", "https://jb0207813-cyber.github.io,http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080,http://127.0.0.1:8080").split(",") if x.strip()]
ROOT = Path(os.getenv("GOONHUB_TMP", tempfile.gettempdir())) / "goonhub-jobs"
ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="GoonHub API", version=APP_VERSION, docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=["GET", "POST", "DELETE"], allow_headers=["Content-Type"])
MAX_CONCURRENT_JOBS = max(1, min(2, int(os.getenv("GOONHUB_CONCURRENCY", "1"))))
executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_JOBS, thread_name_prefix="gh-download")
slots = threading.BoundedSemaphore(MAX_CONCURRENT_JOBS)
lock = threading.RLock()
analyses: dict[str, dict] = {}
jobs: dict[str, dict] = {}
requests_by_ip: dict[str, list[float]] = {}


class AnalyzeRequest(BaseModel):
    url: str = Field(min_length=12, max_length=2048)


class JobRequest(BaseModel):
    analysis_id: str = Field(min_length=12, max_length=100)
    media_indices: list[int] = Field(min_length=1, max_length=MAX_ITEMS)


def validate_url(raw: str) -> tuple[str, str]:
    """Strict platform URL validation, no credentials, ports or arbitrary hosts.

    yt-dlp can fetch additional URLs supplied by a platform; do not expose this
    service to untrusted traffic without network egress controls as well.
    """
    try:
        u = urlsplit(raw.strip())
        if u.scheme != "https" or u.username or u.password or u.port is not None:
            raise ValueError("Use a normal HTTPS post link")
        host = (u.hostname or "").lower().rstrip(".")
        kind = next((k for k, v in ALLOWED_HOSTS.items() if host in v), None)
        if kind is None:
            raise ValueError("Paste an X, Instagram or Facebook post link")
        if kind == "x" and not re.fullmatch(r"/[A-Za-z0-9_]{1,15}/status/\d+(?:/.*)?", u.path):
            raise ValueError("Paste a link to an individual X post")
        if kind == "instagram" and not re.fullmatch(r"/(?:p|reel|tv)/[A-Za-z0-9_-]+/?", u.path):
            raise ValueError("Paste a link to an Instagram post or Reel")
        if kind == "facebook" and (u.path in ("", "/") or ".." in u.path):
            raise ValueError("Paste a link to an individual Facebook post or video")
        if any(ord(c) < 32 for c in raw):
            raise ValueError("Invalid URL")
        return kind, urlunsplit(("https", host, u.path, u.query, ""))
    except (ValueError, UnicodeError) as exc:
        raise ValueError(str(exc) or "Invalid link") from exc


def cleanup_expired():
    now = time.time()
    with lock:
        for key, value in list(analyses.items()):
            if value["expires"] < now:
                analyses.pop(key, None)
        for key, value in list(jobs.items()):
            if value["expires"] < now and value["status"] not in {"queued", "working", "processing"}:
                shutil.rmtree(value["directory"], ignore_errors=True)
                jobs.pop(key, None)
        for ip, stamps in list(requests_by_ip.items()):
            recent = [s for s in stamps if now - s < 60]
            if recent:
                requests_by_ip[ip] = recent
            else:
                requests_by_ip.pop(ip, None)


def rate_limit(request: Request):
    ip = request.client.host if request.client else "unknown"
    with lock:
        now = time.time()
        current = [t for t in requests_by_ip.get(ip, []) if now - t < 60]
        if len(current) >= 15:
            raise HTTPException(429, "Too many requests. Try again in a minute.")
        current.append(now)
        requests_by_ip[ip] = current


def extractor_info(url: str) -> dict:
    if YoutubeDL is None:
        raise RuntimeError("yt-dlp is not installed on the backend")
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": False,
            "playlistend": MAX_ITEMS, "socket_timeout": 14, "retries": 1, "ignoreerrors": False,
            "extract_flat": False, "cachedir": False, "nopart": True}
    with YoutubeDL(opts) as ydl:
        result = ydl.extract_info(url, download=False)
        if not result:
            raise ValueError("No publicly accessible media was found")
        return ydl.sanitize_info(result)


def flatten_media(info: dict) -> list[dict]:
    if not isinstance(info, dict):
        return []
    entries = info.get("entries")
    parts = [p for p in entries if isinstance(p, dict)][:MAX_ITEMS] if isinstance(entries, list) else [info]
    media = []
    for index, part in enumerate(parts, 1):
        ext = str(part.get("ext") or "").lower()
        kind = "image" if ext in {"jpg", "jpeg", "png", "webp", "gif"} else "video"
        # Entries with neither formats nor image URL are not downloadable.
        if not part.get("formats") and not part.get("url") and not part.get("requested_formats"):
            continue
        media.append({"index": index, "kind": kind,
                      "thumbnail": part.get("thumbnail") or info.get("thumbnail"),
                      "duration": part.get("duration") if kind == "video" else None,
                      "width": part.get("width"), "height": part.get("height")})
    return media


@app.get("/api/v1/health")
def health():
    return {"ok": YoutubeDL is not None and shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None,
            "service": "goonhub", "version": APP_VERSION,
            "extractor": YoutubeDL is not None, "ffmpeg": bool(shutil.which("ffmpeg"))}



def classify_extraction_error(exc: Exception, platform: str) -> tuple[int, dict]:
    """Identify the *upstream failure*, not the visibility of the user's post.

    Never return or log raw extractor exceptions: they can contain full source URLs,
    cookie data, or request parameters. Only whitelisted categories leave the server.
    """
    problems = [exc, getattr(exc, "__cause__", None), getattr(exc, "__context__", None)]
    description = " | ".join(str(e) for e in problems if e is not None).lower()
    name = {"x": "X", "instagram": "Instagram", "facebook": "Facebook"}.get(platform, "The platform")

    cases = [
        (("this content isn't available to everyone", "it can't be seen by certain audiences",
          "unavailable for certain audiences", "cannot be seen by certain audiences",
          "isn't available to everyone"),
         403, "AUDIENCE_RESTRICTED",
         f"{name} marked this media as unavailable to certain audiences.",
         "You might still see it while signed in. The server's anonymous request is not eligible to view it. The message does not reveal which audience rule applies."),
        (("guest token", "guest/activate", "guest activation"),
         502, "GUEST_ACCESS_FAILED",
         f"{name} did not grant anonymous access to our server.",
         "This does not mean the post is private. The platform may be blocking guest requests from Render."),
        (("rate limit", "too many requests", "http error 429", "status code 429", "429 too many"),
         503, "UPSTREAM_RATE_LIMIT",
         f"{name} is rate-limiting media requests from the server.",
         "Try again later. Repeated retries may make the block last longer."),
        (("nsfw", "sensitive content", "sensitive media", "age-restricted", "age restricted", "age verification"),
         403, "SENSITIVE_LOGIN_REQUIRED",
         f"{name} requires a signed-in session to access this media.",
         "A post can be public but still require login for sensitive or age-restricted media. GoonHub does not request your credentials."),
        (("login required", "requires login", "requires authentication", "sign in", "log in", "login to", "use --cookies",
          "use cookies", "not authorized", "protected tweet", "authentication required", "http error 401"),
         403, "LOGIN_REQUIRED",
         f"{name} requires authentication before it will provide this media.",
         "Being able to see a post in your signed-in browser does not guarantee anonymous server access."),
        (("http error 403", "403 forbidden", "access denied", "bot detection", "blocked by"),
         502, "UPSTREAM_ACCESS_DENIED",
         f"{name} denied the download server's request (HTTP 403).",
         "This is usually a platform-side access restriction; it does not establish that the post is private."),
        (("failed to parse json", "jsondecodeerror", "unable to extract", "unable to parse",
          "could not parse", "graphql", "extractor error", "unexpected response"),
         502, "EXTRACTOR_INCOMPATIBLE",
         f"The media extractor could not understand {name}'s response.",
         "The platform may have changed its API. Updating yt-dlp or its adapter may be necessary."),
        (("timed out", "timeout", "name resolution", "connection reset", "connection refused",
          "network is unreachable", "ssl error", "certificate verify"),
         504, "UPSTREAM_NETWORK_ERROR",
         f"The server couldn't complete its connection to {name}.",
         "This is a network or upstream timeout, not a statement about the post's visibility."),
        (("unsupported url", "no suitable extractor"),
         422, "UNSUPPORTED_LINK",
         f"The extractor doesn't recognize this {name} post format.",
         "Try copying the post's direct URL rather than a feed, profile, or share redirect."),
        (("not found", "deleted", "http error 404", "tweet unavailable", "post unavailable",
          "does not exist", "no longer available"),
         404, "POST_NOT_FOUND",
         f"{name} reported that the post isn't available to this server.",
         f"It may have been removed, or {name} may be withholding it from anonymous visitors."),
        (("geo-restricted", "geo restricted", "not available in your country"),
         422, "REGION_RESTRICTED",
         f"{name} reported a regional viewing restriction.",
         "Access may differ between your device and the server's region."),
    ]
    for phrases, status, code, message, hint in cases:
        if any(s in description for s in phrases):
            return status, {"code": code, "message": message, "hint": hint}
    return 502, {
        "code": "EXTRACTION_FAILED",
        "message": f"The {name} extractor failed, but the server has not identified why.",
        "hint": "This is not evidence that the post is private. Please share the diagnostic reference so we can investigate.",
    }


def extraction_error_response(exc: Exception, platform: str) -> HTTPException:
    status, detail = classify_extraction_error(exc, platform)
    reference = secrets.token_hex(4)
    logger.warning(
        "Extraction failed: platform=%s code=%s reference=%s exception_type=%s",
        platform, detail["code"], reference, type(exc).__name__,
    )
    return HTTPException(status_code=status, detail={**detail, "reference": reference})


@app.post("/api/v1/analyze")
async def analyze(payload: AnalyzeRequest, request: Request):
    cleanup_expired()
    rate_limit(request)
    try:
        platform, url = validate_url(payload.url)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if YoutubeDL is None:
        raise HTTPException(503, "Media extraction isn't installed on the backend")
    try:
        info = await asyncio.wait_for(asyncio.to_thread(extractor_info, url), timeout=35)
    except asyncio.TimeoutError as exc:
        raise HTTPException(504, detail={"code": "ANALYSIS_TIMEOUT", "message": "The media server timed out during analysis.", "hint": "Try again when the download server and platform are responsive."}) from exc
    except Exception as exc:
        raise extraction_error_response(exc, platform) from exc
    media = flatten_media(info)
    if not media:
        raise HTTPException(422, detail={"code": "NO_MEDIA", "message": "The post was reached, but no downloadable media was found.", "hint": "It may be text-only or use a media format the extractor does not currently support."})
    aid = secrets.token_urlsafe(20)
    result = {"analysis_id": aid, "source_url": url, "platform": platform,
              "creator": str(info.get("uploader") or info.get("channel") or "")[:100] or None,
              "caption": str(info.get("description") or info.get("title") or "")[:1200] or None,
              "thumbnail": info.get("thumbnail"), "media": media}
    with lock:
        analyses[aid] = {"data": result, "expires": time.time() + 900}
    return result


def probe(path: Path) -> tuple[bool, bool]:
    try:
        raw = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)], timeout=20, text=True)
        types = set(raw.split())
        return "video" in types, "audio" in types
    except (subprocess.SubprocessError, OSError):
        return False, False


def source_has_audio(info: dict) -> bool:
    if "entries" in info and isinstance(info["entries"], list):
        return any(source_has_audio(e) for e in info["entries"] if isinstance(e, dict))
    formats = info.get("formats") or []
    return any(str(fmt.get("acodec") or "none").lower() not in {"none", "null", ""} for fmt in formats if isinstance(fmt, dict))


def downloader(url: str, folder: Path, selected: list[int], cancel: threading.Event, on_progress) -> dict:
    if YoutubeDL is None:
        raise RuntimeError("yt-dlp isn't installed")
    def hook(data):
        if cancel.is_set():
            raise RuntimeError("Download cancelled")
        total = data.get("total_bytes") or data.get("total_bytes_estimate")
        done = data.get("downloaded_bytes") or 0
        if total:
            on_progress(min(90, round(90 * done / total)))
    opts = {"quiet": True, "no_warnings": True, "noplaylist": False,
            "playlist_items": ",".join(str(i) for i in selected),
            "playlistend": MAX_ITEMS, "outtmpl": str(folder / "%(autonumber)02d-%(id).80s.%(ext)s"),
            "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/best",
            "merge_output_format": "mp4", "progress_hooks": [hook],
            "max_filesize": MAX_BYTES, "socket_timeout": 18, "retries": 2, "fragment_retries": 2,
            "restrictfilenames": True, "ignoreerrors": False, "cachedir": False,
            "postprocessors": [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}],
        }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    if cancel.is_set():
        raise RuntimeError("Download cancelled")
    if not info:
        raise ValueError("The source had no accessible files")
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".m4v", ".mov", ".webm", ".mkv"}]
    if not files:
        raise ValueError("No supported files were downloaded")
    total = sum(p.stat().st_size for p in files)
    if total > MAX_BYTES:
        raise ValueError("The file exceeds the server size limit")
    expected_audio = source_has_audio(info)
    for p in files:
        if p.suffix.lower() in {".mp4", ".m4v", ".mov", ".webm", ".mkv"}:
            video, audio = probe(p)
            if not video:
                raise ValueError("The resulting file isn't a playable video")
            if expected_audio and not audio:
                raise ValueError("Audio processing failed. Refusing to return a silent video.")
    if len(files) == 1:
        return {"file": files[0], "size": files[0].stat().st_size}
    bundle = folder / "goonhub-media.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(files):
            z.write(p, arcname=p.name)
    if bundle.stat().st_size > MAX_BYTES:
        raise ValueError("The archive exceeds the server size limit")
    return {"file": bundle, "size": bundle.stat().st_size}


def run_job(jobid: str, url: str, selected: list[int]):
    with lock:
        job = jobs.get(jobid)
        if job is None:
            slots.release()
            return
        job["status"] = "working"
    def progress(n):
        with lock:
            if jobid in jobs:
                jobs[jobid]["progress"] = n
    try:
        result = downloader(url, job["directory"], selected, job["cancel"], progress)
        with lock:
            if job["cancel"].is_set():
                job["status"] = "cancelled"
            else:
                job.update({"status": "ready", "progress": 100, "file": result["file"], "size": result["size"],
                            "message": "File ready"})
    except Exception as exc:
        with lock:
            job["status"] = "cancelled" if job["cancel"].is_set() else "error"
            job["message"] = "Download unavailable, restricted, or processing failed." if job["status"] == "error" else "Cancelled"
        # Avoid printing source URLs, cookies, or sensitive extractor tracebacks.
    finally:
        with lock:
            job["expires"] = time.time() + TTL
        slots.release()


def expose_job(job: dict) -> dict:
    d = {k: job[k] for k in ("id", "status", "progress", "message")}
    if job["status"] == "ready":
        d["file_url"] = f"/api/v1/files/{job['id']}?token={job['token']}"
        d["size"] = job.get("size")
    return d


@app.post("/api/v1/jobs", status_code=202)
def create_job(payload: JobRequest, request: Request):
    cleanup_expired()
    rate_limit(request)
    with lock:
        entry = analyses.get(payload.analysis_id)
        if entry is None:
            raise HTTPException(410, "Post analysis expired. Find media again.")
        valid = {m["index"] for m in entry["data"]["media"]}
        if len(payload.media_indices) != len(set(payload.media_indices)) or any(n not in valid for n in payload.media_indices):
            raise HTTPException(400, "Choose available media items only")
    if not slots.acquire(blocking=False):
        raise HTTPException(429, "The downloader is busy. Try again shortly.")
    jobid = secrets.token_urlsafe(18)
    directory = ROOT / jobid
    try:
        directory.mkdir(parents=True, exist_ok=False)
        job = {"id": jobid, "status": "queued", "progress": 0, "message": "Waiting to download",
               "directory": directory, "cancel": threading.Event(), "token": secrets.token_urlsafe(22),
               "expires": time.time() + TTL, "file": None}
        with lock:
            jobs[jobid] = job
        executor.submit(run_job, jobid, entry["data"]["source_url"], payload.media_indices)
    except Exception:
        slots.release()
        shutil.rmtree(directory, ignore_errors=True)
        raise HTTPException(500, "Could not create a download job")
    return expose_job(job)


@app.get("/api/v1/jobs/{jobid}")
def get_job(jobid: str):
    cleanup_expired()
    with lock:
        job = jobs.get(jobid)
        if not job:
            raise HTTPException(404, "Download not found or expired")
        return expose_job(job)


@app.delete("/api/v1/jobs/{jobid}")
def cancel_job(jobid: str):
    with lock:
        job = jobs.get(jobid)
        if not job:
            raise HTTPException(404, "Download not found")
        job["cancel"].set()
        if job["status"] not in {"ready", "error"}:
            job["status"] = "cancelled"
        return {"ok": True}


@app.get("/api/v1/files/{jobid}")
def get_file(jobid: str, token: str):
    cleanup_expired()
    with lock:
        job = jobs.get(jobid)
        if not job or job["status"] != "ready" or not secrets.compare_digest(token, job["token"]):
            raise HTTPException(404, "File not available or expired")
        path = job.get("file")
        if not path or not path.is_file():
            raise HTTPException(404, "File not found")
        if path.parent != job["directory"]:
            raise HTTPException(404, "Invalid download file")
        return FileResponse(path, media_type="application/octet-stream", filename=path.name)