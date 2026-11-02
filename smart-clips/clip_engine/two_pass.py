"""Experimental bounded-bandwidth YouTube -> portrait highlight pipeline.

Download is optional and conditional on platform access and permission to save.
This tool never asks for passwords, exports cookies or uses a remote cookie service.
A browser session may optionally be read *on the same local device* via yt-dlp.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .core import Candidate, Observation
from .ingest import parse_youtube_url
from .processor import analyze, metadata, render


@dataclass(frozen=True)
class Window:
    start: float
    end: float


@dataclass(frozen=True)
class Match:
    window: Window
    candidate: Candidate

    @property
    def start(self) -> float:
        return self.window.start + self.candidate.start

    @property
    def end(self) -> float:
        return self.window.start + self.candidate.end


BROWSERS = frozenset({"firefox", "chrome", "chromium", "brave", "edge"})
MEDIA_EXTENSIONS = frozenset({".mp4", ".webm", ".mkv", ".mov"})


def make_windows(duration: float, *, every: float = 240, window: float = 22, limit: int = 12) -> list[Window]:
    """Sample different regions instead of caching the complete long source."""
    if not (0 < duration <= 24 * 3600):
        raise ValueError("Video duration outside supported range")
    if not (10 <= window <= 120 and every >= window and 1 <= limit <= 40):
        raise ValueError("Invalid sampling budget")
    if duration <= window:
        return [Window(0.0, duration)]
    # Spread the sampling budget across the full source timeline.
    n = min(limit, max(1, int((duration - window) // every) + 1))
    if n == 1:
        return [Window(0.0, window)]
    return [Window(round(i * (duration - window) / (n - 1), 3),
                   round(i * (duration - window) / (n - 1) + window, 3)) for i in range(n)]


def choose_matches(matches: list[Match], max_clips: int) -> list[Match]:
    if not (1 <= max_clips <= 15):
        raise ValueError("Invalid clip limit")
    selected: list[Match] = []
    for item in sorted(matches, key=lambda m: m.candidate.score, reverse=True):
        if item.end <= item.start:
            continue
        if any(max(0, min(item.end, m.end) - max(item.start, m.start)) >
               0.4 * min(item.end - item.start, m.end - m.start) for m in selected):
            continue
        selected.append(item)
        if len(selected) == max_clips:
            break
    return sorted(selected, key=lambda m: m.start)


def localize_candidate(match: Match, proxy_width: int, full_width: int, full_duration: float) -> Candidate:
    """Map tracked proxy coordinates onto *only* the fetched HD excerpt."""
    if proxy_width <= 0 or full_width <= 0 or full_duration <= 0:
        raise ValueError("Invalid frame dimensions or duration")
    scale = full_width / proxy_width
    clip = match.candidate
    def remap(obs: Observation) -> Observation:
        return Observation(
            t=max(0.0, obs.t - clip.start), x=obs.x * scale,
            height=obs.height, confidence=obs.confidence,
            box=tuple(v * scale for v in obs.box),
        )
    return Candidate(
        track_id=clip.track_id, start=0.0, end=full_duration,
        score=clip.score, observations=tuple(remap(p) for p in clip.observations),
    )


def probe_youtube(url: str, *, browser: str | None = None) -> dict:
    """Metadata-only probe. May fail on cloud-hosted IPs; no bypass attempted."""
    from yt_dlp import YoutubeDL
    url = parse_youtube_url(url)
    if browser not in BROWSERS and browser is not None:
        raise ValueError("Unsupported browser session")
    opts = {"skip_download": True, "noplaylist": True, "quiet": True, "no_warnings": False,
            "cachedir": False, "socket_timeout": 20}
    if browser:
        opts["cookiesfrombrowser"] = (browser, None, None, None)
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info or not info.get("duration"):
        raise RuntimeError("YouTube did not provide a usable duration")
    duration = float(info["duration"])
    if duration <= 0 or duration > 24 * 3600:
        raise ValueError("Video duration not supported")
    return {"duration": duration, "title": str(info.get("title") or "")[:120],
            "id": str(info.get("id") or "")[:20]}


def download_excerpt(url: str, start: float, end: float, folder: Path, *,
                     proxy: bool, browser: str | None = None, timeout: int = 240) -> Path:
    """Ask yt-dlp/FFmpeg for just one time range, never the entire 4K original.

    Some streaming formats/servers do not honor precise seeking; this is a
    best-effort bounded request, NOT a guarantee of downloaded byte counts.
    """
    if not (0 <= start < end and end - start <= 180):
        raise ValueError("Invalid excerpt")
    if browser is not None and browser not in BROWSERS:
        raise ValueError("Unsupported browser session")
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg is required for section extraction")
    folder.mkdir(parents=True, exist_ok=False)
    # No shell=True, no arbitrary caller format strings, no external URL domains.
    cmd = [sys.executable, "-m", "yt_dlp", "--no-playlist", "--no-overwrites",
           "--no-write-thumbnail", "--force-keyframes-at-cuts",
           "--download-sections", f"*{start:.3f}-{end:.3f}",
           "--socket-timeout", "20", "--retries", "1", "--fragment-retries", "1",
           "--merge-output-format", "mp4", "-o", str(folder / "source.%(ext)s")]
    if proxy:
        cmd.extend(["-f", "bv*[height<=480]/b[height<=480]/worst"])
    else:
        cmd.extend(["-f", "bv*+ba/b"])
    if browser:
        # Reads a session only from the local user's own browser installation;
        # never copy or upload the extracted session to GoonHub servers.
        cmd.extend(["--cookies-from-browser", browser])
    cmd.append(parse_youtube_url(url))
    try:
        subprocess.run(cmd, check=True, timeout=timeout, capture_output=True, text=True)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("YouTube excerpt fetch timed out") from exc
    except subprocess.CalledProcessError as exc:
        log = (exc.stderr or "") + (exc.stdout or "")
        if "Sign in to confirm" in log:
            raise RuntimeError("YouTube blocked the server with a bot-verification challenge") from None
        raise RuntimeError("YouTube excerpt could not be fetched. Check upstream access and video permissions.") from None
    videos = [p for p in folder.iterdir() if p.suffix.lower() in MEDIA_EXTENSIONS and p.is_file()]
    if not videos:
        raise RuntimeError("No usable video was delivered by YouTube")
    return max(videos, key=lambda p: p.stat().st_size)


def run_two_pass(url: str, output: Path, *, clips: int = 3, sample_every: int = 240,
                 scan_seconds: int = 22, max_windows: int = 12, sample_fps: float = 2,
                 browser: str | None = None,
                 fetch: Callable[..., Path] = download_excerpt,
                 inspect: Callable[..., tuple[dict, list[Candidate]]] = analyze,
                 export: Callable[..., None] = render) -> dict:
    """Analyze small, low-res windows then fetch original quality only for winners.

    Temporary proxy and HD sections are removed at the end even on failure.
    Output consists only of user-selected short portrait samples + manifest.
    """
    normalized = parse_youtube_url(url)
    meta = probe_youtube(normalized, browser=browser)
    windows = make_windows(meta["duration"], every=sample_every,
                           window=scan_seconds, limit=max_windows)
    output.mkdir(parents=True, exist_ok=True)
    matches: list[Match] = []
    widths: dict[Window, int] = {}
    with tempfile.TemporaryDirectory(prefix="goonhub-scan-") as temp:
        base = Path(temp)
        for i, window in enumerate(windows):
            print(f"Scanning window {i + 1}/{len(windows)}: {window.start:.1f}-{window.end:.1f}s", flush=True)
            proxy = fetch(normalized, window.start, window.end,
                          base / f"proxy-{i:02d}", proxy=True, browser=browser)
            scan_meta, candidates = inspect(proxy, sample_fps=sample_fps, max_clips=3)
            widths[window] = int(scan_meta["width"])
            matches.extend(Match(window, c) for c in candidates)
            proxy.unlink(missing_ok=True)
        selected = choose_matches(matches, clips)
        records = []
        for i, match in enumerate(selected, 1):
            print(f"Fetching high-res excerpt {i}/{len(selected)}: {match.start:.1f}-{match.end:.1f}s", flush=True)
            full = fetch(normalized, match.start, match.end,
                         base / f"full-{i:02d}", proxy=False, browser=browser)
            full_meta = metadata(full)
            local = localize_candidate(match, widths[match.window],
                                       full_meta["width"], full_meta["duration"])
            dest = output / f"highlight-{i:02d}.mp4"
            export(full, dest, full_meta, local)
            records.append({"file": dest.name, "start": round(match.start, 3),
                            "end": round(match.end, 3), "score": round(match.candidate.score, 4)})
        manifest = {"source_id": meta["id"], "title": meta["title"],
                    "scan_windows": [vars(w) for w in windows],
                    "selected": records, "complete": True,
                    "note": "Person-track highlights are suggestions; review before reuse."}
        (output / "highlights.json").write_text(json.dumps(manifest, indent=2))
        return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="GoonHub sampled low-res scan + high-res clips")
    parser.add_argument("youtube_url", help="YouTube video you have permission to download and edit")
    parser.add_argument("--output", type=Path, default=Path("./smart-clips-output"))
    parser.add_argument("--clips", type=int, default=3)
    parser.add_argument("--sample-every", type=int, default=240, help="Seconds between scan windows")
    parser.add_argument("--scan-seconds", type=int, default=22)
    parser.add_argument("--max-windows", type=int, default=12)
    parser.add_argument("--browser-session", choices=sorted(BROWSERS), default=None,
                        help="Optional: local browser session; never uploads cookies or passwords")
    args = parser.parse_args()
    print(json.dumps(run_two_pass(args.youtube_url, args.output, clips=args.clips,
                                  sample_every=args.sample_every,
                                  scan_seconds=args.scan_seconds,
                                  max_windows=args.max_windows, browser=args.browser_session), indent=2))


if __name__ == "__main__":
    main()