"""Video analysis and loss-controlled, smoothly tracked 9:16 clips.

Dependencies are imported lazily to allow math and FFmpeg tests without ML weights.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from .core import Observation, Candidate, assign_detections, find_candidates, ffmpeg_x_expression, smooth_centers, target_width


def metadata(source: Path) -> dict:
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(source)],
        check=True, capture_output=True, text=True, timeout=60,
    )
    info = json.loads(p.stdout)
    video = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    if video is None:
        raise ValueError("Video stream missing")
    duration = float(video.get("duration") or info["format"].get("duration") or 0)
    if duration <= 0:
        raise ValueError("Could not establish video duration")
    return {"width": int(video["width"]), "height": int(video["height"]), "duration": duration,
            "fps": video.get("avg_frame_rate"), "has_audio": any(s["codec_type"] == "audio" for s in info["streams"])}


def analyze(source: Path, *, model_name: str = "yolo11n-pose.pt", sample_fps: float = 4.0, max_clips: int = 5,
            min_duration: float = 3, max_duration: float = 16) -> tuple[dict, list[Candidate]]:
    import cv2
    from ultralytics import YOLO
    if sample_fps <= 0 or sample_fps > 15:
        raise ValueError("sample_fps must be between 0 and 15")
    meta = metadata(source)
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        raise ValueError("Could not open source video")
    model = YOLO(model_name)
    active = {}
    tracks: dict[int, list[Observation]] = {}
    next_id = 1
    step_s = 1 / sample_fps
    timestamp = 0.0
    try:
        while timestamp < meta["duration"]:
            cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
            ok, frame = cap.read()
            if not ok:
                break
            result = model.predict(source=frame, imgsz=640, conf=0.35, classes=[0], verbose=False)[0]
            observations: list[Observation] = []
            boxes = result.boxes
            if boxes is not None and len(boxes):
                coords = boxes.xyxy.cpu().numpy()
                confidences = boxes.conf.cpu().numpy()
                keypoints = result.keypoints.xy.cpu().numpy() if result.keypoints is not None else None
                for i, (box, conf) in enumerate(zip(coords, confidences)):
                    left, top, right, bottom = [float(v) for v in box]
                    # COCO pose indices 11 and 12 correspond to hip keypoints.
                    midpoint = (left + right) / 2
                    if keypoints is not None and len(keypoints[i]) > 12:
                        left_hip, right_hip = keypoints[i][11], keypoints[i][12]
                        if left_hip[0] > 0 and right_hip[0] > 0:
                            midpoint = float((left_hip[0] + right_hip[0]) / 2)
                    observations.append(Observation(timestamp, midpoint,
                                                    min(1., max(0., (bottom - top) / meta["height"])),
                                                    float(conf), (left, top, right, bottom)))
            active, next_id = assign_detections(active, observations, width=meta["width"],
                                                max_gap=1.5 * step_s + .01, next_id=next_id)
            for track_id, obs in active.items():
                tracks.setdefault(track_id, []).append(obs)
            timestamp += step_s
    finally:
        cap.release()
    clips = find_candidates(tracks, meta["duration"], max_clips=max_clips,
                            min_duration=min_duration, max_duration=max_duration)
    return meta, clips


def make_ffmpeg_command(source: Path, output: Path, meta: dict, clip: Candidate, *, output_height: int = 1920,
                        crf: int = 17, preset: str = "slow") -> list[str]:
    crop_w = target_width(meta["width"], meta["height"])
    smoothed = smooth_centers(clip.observations)
    x = ffmpeg_x_expression(smoothed, crop_w, meta["width"], clip.start)
    # Full-height portrait crop, moved horizontally at each frame.
    h = max(240, min(output_height, meta["height"])) // 2 * 2
    w = round(h * 9 / 16 / 2) * 2
    filtergraph = f"crop={crop_w}:{meta['height']}:'{x}':0,scale={w}:{h}:flags=lanczos,setsar=1"
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{clip.start:.3f}",
            "-i", str(source), "-t", f"{clip.end - clip.start:.3f}", "-vf", filtergraph,
            "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", preset,
            "-crf", str(crf), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", str(output)]


def render(source: Path, output: Path, meta: dict, clip: Candidate, *, output_height: int = 1920) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = make_ffmpeg_command(source, output, meta, clip, output_height=output_height)
    try:
        subprocess.run(cmd, check=True, timeout=1200)
    except Exception:
        output.unlink(missing_ok=True)
        raise