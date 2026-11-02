import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main as m
from fastapi.testclient import TestClient

client = TestClient(m.app)


def test_supported_and_blocked_urls():
    assert m.validate_url("https://x.com/somebody/status/123456789")[0] == "x"
    assert m.validate_url("https://www.instagram.com/reel/C1A2B3_/")[0] == "instagram"
    assert m.validate_url("https://www.facebook.com/watch/?v=123")[0] == "facebook"
    for url in [
        "http://x.com/me/status/12345", "https://x.com.attacker.test/me/status/12345",
        "https://127.0.0.1/me/status/12345", "https://x.com@evil.example/me/status/12345",
        "https://x.com:8443/me/status/12345", "https://x.com/home",
        "https://www.instagram.com/accounts/login/", "file:///etc/passwd",
    ]:
        try:
            m.validate_url(url)
        except ValueError:
            continue
        assert False, f"Should reject {url}"


def test_preview_sanitization():
    info = {"entries": [
        {"id": "1", "ext": "mp4", "formats": [{"format_id": "h264"}], "duration": 14},
        {"id": "2", "ext": "jpg", "url": "https://pbs.twimg.com/a.jpg"},
        {"id": "3", "ext": "mp4"},
    ]}
    media = m.flatten_media(info)
    assert [(x["index"], x["kind"]) for x in media] == [(1, "video"), (2, "image")]


def test_analyze_and_file_delivery(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "YoutubeDL", object())
    monkeypatch.setattr(m, "ROOT", tmp_path)
    monkeypatch.setattr(m, "extractor_info", lambda url: {
        "uploader": "Test creator", "title": "A video", "ext": "mp4",
        "formats": [{"ext": "mp4", "vcodec": "avc1", "acodec": "mp4a.40.2"}],
        "thumbnail": "https://pbs.twimg.com/preview.jpg", "webpage_url": url
    })
    def fake_download(url, folder, selected, cancel, progress):
        assert selected == [1]
        f = folder / "video.mp4"
        f.write_bytes(b"fake-media")
        progress(80)
        return {"file": f, "size": f.stat().st_size}
    monkeypatch.setattr(m, "downloader", fake_download)
    data = client.post("/api/v1/analyze", json={"url": "https://x.com/test/status/12345678"})
    assert data.status_code == 200, data.text
    a = data.json()
    assert len(a["media"]) == 1
    invalid = client.post("/api/v1/jobs", json={"analysis_id": a["analysis_id"], "media_indices": [99]})
    assert invalid.status_code == 400
    job = client.post("/api/v1/jobs", json={"analysis_id": a["analysis_id"], "media_indices": [1]})
    assert job.status_code == 202, job.text
    j = job.json()
    for i in range(50):
        row = client.get(f"/api/v1/jobs/{j['id']}")
        if row.json()["status"] == "ready":
            break
        time.sleep(.02)
    assert row.json()["status"] == "ready", row.json()
    url = row.json()["file_url"]
    assert client.get(url.split('?')[0]+'?token=bad').status_code == 404
    output = client.get(url)
    assert output.status_code == 200
    assert output.content == b"fake-media"
    assert 'attachment' in output.headers['content-disposition']


def test_audio_probe_when_source_has_audio(monkeypatch, tmp_path):
    assert m.source_has_audio({"formats": [{"acodec": "none"}, {"acodec": "aac"}]})
    assert not m.source_has_audio({"formats": [{"acodec": "none"}]})
    assert not m.source_has_audio({})
    assert m.probe(tmp_path / "missing.mp4") == (False, False)

def test_extractor_error_categories_do_not_assume_private():
    cases = [
        ("Could not retrieve guest token", 502, "GUEST_ACCESS_FAILED"),
        ("Rate limit exceeded", 503, "UPSTREAM_RATE_LIMIT"),
        ("NSFW tweet requires authentication", 403, "SENSITIVE_LOGIN_REQUIRED"),
        ("This tweet requires login", 403, "LOGIN_REQUIRED"),
        ("HTTP Error 403: Forbidden", 502, "UPSTREAM_ACCESS_DENIED"),
        ("Failed to parse JSON from GraphQL", 502, "EXTRACTOR_INCOMPATIBLE"),
        ("Connection timed out", 504, "UPSTREAM_NETWORK_ERROR"),
        ("Unexpected extractor exception", 502, "EXTRACTION_FAILED"),
    ]
    for raw, status, expected in cases:
        http_status, detail = m.classify_extraction_error(RuntimeError(raw), "x")
        assert http_status == status, raw
        assert detail["code"] == expected
        assert "private" not in detail["message"].lower()
    status, detail = m.classify_extraction_error(ValueError("unhandled"), "instagram")
    assert detail["code"] == "EXTRACTION_FAILED"
    assert status == 502


def test_analyze_failure_includes_safe_diagnostic_code(monkeypatch):
    monkeypatch.setattr(m, "YoutubeDL", object())
    monkeypatch.setattr(
        m, "extractor_info",
        lambda url: (_ for _ in ()).throw(ValueError("Could not retrieve guest token at https://x.com/secret-test")),
    )
    response = client.post(
        "/api/v1/analyze",
        json={"url": "https://x.com/test/status/1234567890123456789"},
    )
    assert response.status_code == 502, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "GUEST_ACCESS_FAILED"
    assert len(detail["reference"]) == 8
    assert "secret-test" not in response.text
    assert "private, unavailable" not in response.text
