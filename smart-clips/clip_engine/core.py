"""Pure, testable tracking/clip selection/reframing primitives.

This engine tracks *people*, not gender or age. Candidates need user review,
particularly for public street footage where a detector cannot establish age.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median


@dataclass(frozen=True)
class Observation:
    t: float
    x: float              # subject center x in source pixels
    height: float         # person bounding-box height / video height, [0, 1]
    confidence: float     # detector confidence
    box: tuple[float, float, float, float]


@dataclass(frozen=True)
class Candidate:
    track_id: int
    start: float
    end: float
    score: float
    observations: tuple[Observation, ...]


def box_iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    x0 = max(a[0], b[0]); y0 = max(a[1], b[1]); x1 = min(a[2], b[2]); y1 = min(a[3], b[3])
    overlap = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    aa = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    bb = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    return overlap / (aa + bb - overlap) if aa + bb > overlap else 0.0


def assign_detections(
    active: dict[int, Observation],
    detections: list[Observation],
    *,
    width: int,
    max_gap: float = 0.9,
    next_id: int = 1,
) -> tuple[dict[int, Observation], int]:
    """Greedy box association; fast enough for a sparse pedestrian sample stream.

    The visual track can switch people in crowds; user review remains mandatory.
    """
    proposals: list[tuple[float, int, int]] = []
    for track_id, prev in active.items():
        for j, obs in enumerate(detections):
            dt = obs.t - prev.t
            if not (0 < dt <= max_gap):
                continue
            iou = box_iou(prev.box, obs.box)
            dx = abs(prev.x - obs.x) / max(1.0, width)
            if iou < 0.10 and dx > 0.11:
                continue
            proposals.append((2 * iou - dx, track_id, j))
    proposals.sort(reverse=True)
    assigned: dict[int, Observation] = {}
    matched: set[int] = set()
    for _, track_id, j in proposals:
        if track_id not in assigned and j not in matched:
            assigned[track_id] = detections[j]
            matched.add(j)
    for j, obs in enumerate(detections):
        if j not in matched:
            assigned[next_id] = obs
            next_id += 1
    return assigned, next_id


def split_track(points: list[Observation], *, max_gap: float = 1.0) -> list[list[Observation]]:
    chunks: list[list[Observation]] = []
    for obs in sorted(points, key=lambda p: p.t):
        if not chunks or obs.t - chunks[-1][-1].t > max_gap:
            chunks.append([])
        chunks[-1].append(obs)
    return chunks


def find_candidates(
    tracks: dict[int, list[Observation]],
    video_duration: float,
    *,
    max_clips: int = 5,
    min_duration: float = 3.0,
    max_duration: float = 16.0,
    pad: float = 0.9,
    min_height: float = 0.22,
) -> list[Candidate]:
    """Select sustained, well-framed person tracks; no sexual or gender scoring."""
    proposed = []
    for track_id, points in tracks.items():
        for chunk in split_track(points):
            if len(chunk) < 5:
                continue
            a = chunk[0].t
            b = chunk[-1].t
            if b - a < min_duration:
                continue
            heights = [p.height for p in chunk]
            size = median(heights)
            if size < min_height:
                continue
            if (b - a) > max_duration - 2 * pad:
                center = (a + b) / 2
                a, b = center - (max_duration - 2 * pad) / 2, center + (max_duration - 2 * pad) / 2
                chunk = [p for p in chunk if a <= p.t <= b]
            start = max(0.0, a - pad)
            end = min(video_duration, b + pad)
            if end - start < min_duration:
                continue
            score = (b - a) ** 0.6 * min(1.0, size) * median(p.confidence for p in chunk)
            proposed.append(Candidate(track_id, start, end, score, tuple(chunk)))
    selected: list[Candidate] = []
    for candidate in sorted(proposed, key=lambda p: p.score, reverse=True):
        if any(max(0.0, min(candidate.end, c.end) - max(candidate.start, c.start)) >
               0.45 * min(candidate.end - candidate.start, c.end - c.start) for c in selected):
            continue
        selected.append(candidate)
        if len(selected) >= max_clips:
            break
    return sorted(selected, key=lambda p: p.start)


def smooth_centers(points: tuple[Observation, ...], *, radius: int = 2) -> list[tuple[float, float]]:
    """Median-filter sudden tracking errors, then use an EMA for stable pans."""
    if not points:
        raise ValueError("Cannot reframe a track without observations")
    xvals = [p.x for p in points]
    center = xvals[0]
    result = []
    for i, point in enumerate(points):
        med = median(xvals[max(0, i - radius):min(len(xvals), i + radius + 1)])
        center = 0.65 * center + 0.35 * med
        result.append((point.t, center))
    return result


def target_width(source_width: int, source_height: int) -> int:
    """Crop full source height to a width close to 9:16, preserving even pixels."""
    if source_width < 2 or source_height < 2:
        raise ValueError("Invalid source dimensions")
    return min(source_width - source_width % 2, max(2, int(source_height * 9 / 16) // 2 * 2))


def crop_x(center: float, source_width: int, crop_width: int) -> float:
    return min(max(0.0, center - crop_width / 2), max(0.0, source_width - crop_width))


def ffmpeg_x_expression(samples: list[tuple[float, float]], crop_width: int, source_width: int, clip_start: float) -> str:
    """Construct per-frame, piecewise-linear FFmpeg crop-x expression (t-based)."""
    if not samples:
        raise ValueError("Missing tracking samples")
    by_t = sorted((max(0.0, t - clip_start), crop_x(x, source_width, crop_width)) for t, x in samples)
    # The nearest observed position applies before the first sample and after the last.
    expr = f"{by_t[-1][1]:.2f}"
    for (t0, x0), (t1, x1) in reversed(list(zip(by_t, by_t[1:]))):
        span = max(0.001, t1 - t0)
        interpolated = f"({x0:.2f}+({x1-x0:.2f})*(t-{t0:.3f})/{span:.3f})"
        expr = f"if(lt(t,{t1:.3f}),{interpolated},{expr})"
    first_t, first_x = by_t[0]
    expr = f"if(lt(t,{first_t:.3f}),{first_x:.2f},{expr})"
    return f"clip({expr},0,{max(0, source_width-crop_width)})"