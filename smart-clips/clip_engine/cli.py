"""Run: python -m clip_engine.cli /path/to/video.mp4 --output clips"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .processor import analyze, render
from .ingest import download_youtube, parse_youtube_url


def main() -> None:
    p = argparse.ArgumentParser(description="GoonHub smart 9:16 walking-video highlight prototype")
    p.add_argument("video", help="Local video file, or a public YouTube URL you have permission to download")
    p.add_argument("--output", type=Path, default=Path("./goonhub-clips"))
    p.add_argument("--clips", type=int, default=5)
    p.add_argument("--sample-fps", type=float, default=4)
    p.add_argument("--output-height", type=int, default=1920)
    p.add_argument("--model", default="yolo11n-pose.pt", help="YOLO pose model weights")
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    source = download_youtube(args.video, args.output / "source") if args.video.startswith("https://") else Path(args.video)
    if not source.is_file():
        p.error("Source video file does not exist")
    meta, clips = analyze(source, model_name=args.model, sample_fps=args.sample_fps, max_clips=args.clips)
    records = []
    for i, clip in enumerate(clips, 1):
        dest = args.output / f"highlight-{i:02d}.mp4"
        print(f"[{i}/{len(clips)}] {clip.start:.1f}-{clip.end:.1f}s => {dest}", flush=True)
        render(source, dest, meta, clip, output_height=args.output_height)
        records.append({"file": str(dest), "start": clip.start, "end": clip.end, "track": clip.track_id,
                        "score": round(clip.score, 3)})
    manifest = args.output / "highlights.json"
    manifest.write_text(json.dumps({"source": str(source), "video": meta, "clips": records}, indent=2))
    print(f"Done. {len(clips)} candidate clips saved; review each person's identity and suitability.")


if __name__ == "__main__":
    main()