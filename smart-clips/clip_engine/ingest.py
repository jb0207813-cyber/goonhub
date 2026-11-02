"""Optional, authorization-respecting YouTube import.

Only download content users have rights to save. Never bypass DRM or authentication.
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit, parse_qs


def parse_youtube_url(raw: str) -> str:
    url = urlsplit(raw.strip())
    if url.scheme != "https" or url.username or url.password or url.port is not None:
        raise ValueError("Only normal HTTPS YouTube URLs are supported")
    host = (url.hostname or "").lower()
    if host in {"youtu.be", "www.youtu.be"}:
        video_id = url.path.strip("/").split("/")[0]
    elif host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        if url.path == "/watch":
            video_id = parse_qs(url.query).get("v", [""])[0]
        elif url.path.startswith("/shorts/"):
            video_id = url.path.split("/")[2]
        else:
            raise ValueError("Paste a direct YouTube video link")
    else:
        raise ValueError("Paste a YouTube video URL, not an arbitrary site")
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise ValueError("Invalid YouTube video ID")
    return f"https://www.youtube.com/watch?v={video_id}"


def download_youtube(raw: str, workdir: Path, *, max_bytes: int = 2_000_000_000) -> Path:
    from yt_dlp import YoutubeDL
    url = parse_youtube_url(raw)
    workdir.mkdir(parents=True, exist_ok=True)
    settings = {
        "outtmpl": str(workdir / "source.%(ext)s"),
        "format": "bv*+ba/b", "merge_output_format": "mkv",
        "noplaylist": True, "max_filesize": max_bytes, "quiet": False,
        "no_warnings": False, "restrictfilenames": True,
    }
    with YoutubeDL(settings) as ydl:
        ydl.download([url])
    paths = sorted(workdir.glob("source.*"), key=lambda p:p.stat().st_size, reverse=True)
    videos = [p for p in paths if p.suffix.lower() in {".mkv", ".mp4", ".webm", ".mov"}]
    if not videos:
        raise RuntimeError("YouTube did not provide a downloadable media file")
    video = videos[0]
    if video.stat().st_size > max_bytes:
        raise ValueError("Source exceeds configured download limit")
    return video