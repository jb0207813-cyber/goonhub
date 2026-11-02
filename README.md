# GoonHub — media downloader

**Rebuild v1.0** · X-inspired, mobile-first download application for supported public X, Instagram and Facebook videos/photos. No account, lock screen, gallery, liked-post syncing, FxEmbed or third-party downloader website.

## What works / what requires setup

- **Frontend:** Complete static PWA, media composer, preview, multiple-item selection, session activity, real progress and download links. Live on GitHub Pages after the root files deploy. The interface itself is free to host.
- **Backend:** Included Python FastAPI service using yt-dlp and FFmpeg for extraction, audio/video merging, validation, ephemeral jobs, expiring file delivery and basic rate limiting. **You must deploy this backend before real downloads work from your iPhone.** GitHub Pages cannot run Python, video extraction or FFmpeg.
- **Platforms:** Support is best-effort. X/Instagram/Facebook can restrict individual posts, require authentication or change their extraction mechanisms. No guarantee that every photo, Reel or video is downloadable. Don't enter social account passwords or cookies.
- **No permanent gallery:** Files are delivered to your device. The temporary backend file is removed after expiration. Activity remains only in the open browser session.

### Run locally on Arch Linux

Install Python, ffmpeg and pip, then in a virtual environment:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
python -m http.server 8080
```

Open `http://localhost:8080/` and the frontend will automatically use `http://127.0.0.1:8000`. For iPhone use, expose the backend on a **proper HTTPS hostname** with a trusted deployment or secure private tunnel and enter its origin (e.g., `https://api.example.com`) under **Settings → Download server**. Avoid exposing an unauthenticated public downloader without network and rate-limit hardening.

### Deploy frontend to GitHub Pages

This repository includes compiled-free HTML/CSS/JavaScript directly at the root; keep Pages set to `main / (root)`. No npm build or GitHub Actions configuration is needed. Home screen: open the GitHub Pages site in Safari, Share → Add to Home Screen.

### Tests

```bash
node tests/smoke.mjs
cd backend && python -m pytest tests -q
```

Unit tests simulate extraction/download. **Live platform downloads and real iPhone audio playback remain unverified until the backend is deployed and actual public test URLs are tested.**

### Architecture

- `index.html`, `styles.css`, `app.js`, `lib.js` — frontend and PWA shell
- `backend/main.py` — download API with `/api/v1/analyze`, `/api/v1/jobs`, `/api/v1/files`, `/api/v1/health`
- `backend/Dockerfile` — container image with ffmpeg + yt-dlp
- `docs/DESIGN_SPEC.md` — product/UX specification for the redesign

### Privacy and limitations

No GoonHub user account or social platform credentials. The backend receives submitted public post URLs, temporarily downloads media and deletes expired jobs. Server administrators can see network requests; never treat publicly exposed instance as private. Frontend stores only the backend origin in localStorage. Existing legacy vault data from the old app is not read, sent or deleted. Download only media you have permission to save. Respect creators' rights and platform terms.

### Roadmap

- Verify platform-specific extraction on real, permitted public posts (including X photo posts).
- Deploy the FastAPI backend behind HTTPS; set limits and egress firewall rules.
- Run a physical iPhone Safari and Home Screen PWA playback/download test, especially confirming merged audio.
- Add an optional native iOS shortcut later if useful.