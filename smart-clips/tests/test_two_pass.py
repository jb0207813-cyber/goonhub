from pathlib import Path

import pytest
from clip_engine.core import Candidate, Observation
from clip_engine.two_pass import (
    Window, Match, make_windows, choose_matches, localize_candidate,
    run_two_pass,
)


def fake_candidate(offset=0.0):
    pts = tuple(Observation(offset + t, 100 + t * 3, 0.7, 0.9, (90, 20, 130, 220)) for t in (1, 2, 3, 4, 5, 6))
    return Candidate(1, offset, offset + 8, 8.0, pts)


def test_windows_bounded_and_spread_across_video():
    windows = make_windows(7200, every=300, window=20, limit=8)
    assert len(windows) == 8
    assert windows[0].start == 0
    assert windows[-1].end == 7200
    assert all(round(w.end - w.start) == 20 for w in windows)
    assert make_windows(12, window=22) == [Window(0, 12)]
    with pytest.raises(ValueError):
        make_windows(100, window=121)


def test_candidates_are_absolute_time_and_nonoverlapping():
    wins = [Window(0, 22), Window(400, 422)]
    matches = [Match(w, fake_candidate()) for w in wins]
    selected = choose_matches(matches, 2)
    assert [m.start for m in selected] == [0, 400]
    assert [m.end for m in selected] == [8, 408]


def test_proxy_coordinates_are_scaled_before_full_resolution_render():
    match = Match(Window(100, 120), fake_candidate(0))
    local = localize_candidate(match, 640, 3840, 8.5)
    assert local.start == 0
    assert local.end == 8.5
    assert local.observations[0].x == 103 * 6
    assert local.observations[0].t == 1


def test_two_pass_fetches_only_selected_hd_excerpts_and_cleans_proxies(monkeypatch, tmp_path):
    import clip_engine.two_pass as two_pass
    monkeypatch.setattr(two_pass, "probe_youtube", lambda url, browser=None: {"duration": 600, "id": "TfNJMZBIbsI", "title": "Walk"})
    monkeypatch.setattr(two_pass, "metadata", lambda path: {"width": 3840, "height": 2160, "duration": 8.0})
    fetch_calls = []
    rendered = []
    def fetch(url, start, end, folder, *, proxy, browser):
        folder.mkdir(parents=True)
        path = folder / ("proxy.mp4" if proxy else "full.mp4")
        path.write_bytes(b"pretend video segment")
        fetch_calls.append((start, end, proxy, browser, path))
        return path
    def inspect(src, *, sample_fps, max_clips):
        assert src.exists()
        return {"width": 640}, [fake_candidate()]
    def export(src, dest, meta, candidate):
        assert src.exists()
        assert candidate.observations[0].x == 618
        assert meta["width"] == 3840
        dest.write_bytes(b"fake portrait clip")
        rendered.append(dest)
    result = run_two_pass(
        "https://youtu.be/TfNJMZBIbsI", tmp_path / "out", clips=1,
        sample_every=240, scan_seconds=22, max_windows=3,
        browser="firefox", fetch=fetch, inspect=inspect, export=export)
    assert len(fetch_calls) == 4
    assert all(x[2] for x in fetch_calls[:3])
    assert not fetch_calls[-1][2]
    assert fetch_calls[-1][0] == 0
    assert fetch_calls[-1][1] == 8
    assert all(x[3] == "firefox" for x in fetch_calls)
    assert len(rendered) == 1 and rendered[0].exists()
    assert len(result["scan_windows"]) == 3
    assert result["selected"][0]["file"] == "highlight-01.mp4"
    assert not any(path.exists() for *_, path in fetch_calls)


def test_rejects_invalid_url_before_fetch(tmp_path):
    with pytest.raises(ValueError):
        run_two_pass("https://bad.example/video", tmp_path / "out")