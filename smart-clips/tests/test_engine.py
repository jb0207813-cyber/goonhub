import math
from pathlib import Path
from clip_engine.core import (Observation, assign_detections, box_iou, crop_x, ffmpeg_x_expression,
                              find_candidates, smooth_centers, target_width)
from clip_engine.processor import make_ffmpeg_command


def p(t, x=550, confidence=.9):
    return Observation(t, x, .72, confidence, (x-80, 30, x+80, 620))


def test_iou_and_assignment():
    assert box_iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1
    assert box_iou((0, 0, 10, 10), (20, 0, 30, 10)) == 0
    matched, next_id = assign_detections({4:p(1)}, [p(1.2, 555), p(1.2, 920)], width=1280, next_id=5)
    assert 4 in matched and 5 in matched and next_id == 6


def test_candidate_selection_and_overlap():
    tracks={1:[p(t*.25, 400) for t in range(41)], 2:[p(t*.25, 500) for t in range(41)],
            3:[p(t*.25, 700) for t in range(4)]}
    candidates=find_candidates(tracks, 20, max_clips=5)
    assert len(candidates) == 1
    assert candidates[0].start >= 0 and candidates[0].end <= 20
    assert candidates[0].end - candidates[0].start <= 16


def test_crop_math_and_smooth_track():
    assert target_width(3840, 2160) == 1214
    assert crop_x(100, 3840, 1214) == 0
    assert crop_x(3700, 3840, 1214) == 2626
    points=tuple(p(i, 700 if i==3 else 500) for i in range(9))
    smoothed=smooth_centers(points)
    assert max(x for t, x in smoothed) < 600
    expr=ffmpeg_x_expression(smoothed, 608, 1920, clip_start=1)
    assert 'clip(' in expr and 'if(lt(t' in expr


def test_ffmpeg_quality_preserves_audio_mapping():
    clip=find_candidates({1:[p(i*.25) for i in range(40)]}, 15)[0]
    meta={"width":1920,"height":1080,"duration":15,"has_audio":True}
    cmd=make_ffmpeg_command(Path('input.mp4'),Path('out.mp4'),meta,clip)
    s=' '.join(cmd)
    assert '-crf 17' in s and '-preset slow' in s
    assert '0:a?' in s and '+faststart' in s
    assert 'scale=' in s and 'crop=' in s
    assert 'scale=608:1080:' in s  # preserve native 1080p detail, no artificial upscaling


def test_youtube_url_restrictive():
    from clip_engine.ingest import parse_youtube_url
    expected='https://www.youtube.com/watch?v=TfNJMZBIbsI'
    assert parse_youtube_url('https://youtu.be/TfNJMZBIbsI?si=x') == expected
    assert parse_youtube_url('https://www.youtube.com/watch?v=TfNJMZBIbsI') == expected
    for url in ['http://youtu.be/TfNJMZBIbsI', 'https://youtu.be.evil.test/TfNJMZBIbsI',
                'https://www.youtube.com/playlist?list=abc', 'https://youtu.be/bad',
                'https://youtube.com@attacker.test/watch?v=TfNJMZBIbsI']:
        try:
            parse_youtube_url(url)
        except ValueError:
            continue
        raise AssertionError(f'Invalid URL accepted: {url}')