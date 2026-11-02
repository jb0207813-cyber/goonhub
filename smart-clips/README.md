# GoonHub Smart Clips — experimental engine (v0.1)

**New product direction:** transform long walking footage into short 9:16 person-following clips, with a human-in-the-loop picker before export. Prototype code is separate from the current production downloader; it does **not** yet run on the public iPhone GoonHub site.

## What this prototype does

- Accepts a local video, or a supported public YouTube link if yt-dlp can access it and you have permission to save it.
- Samples video frames with a YOLO pose detector (640px inference), finds people, groups nearby detections into tracks, and proposes sustained highlights.
- Reframes each accepted candidate with *smooth horizontal tracking*, using a frame-by-frame 9:16 crop (not a static crop). The full-height crop works best on 16:9 or wider source footage.
- Encodes final output from the **original full-resolution video** using FFmpeg `libx264`, `-crf 17`, `-preset slow`, high-quality Lanczos scaling, AAC audio and fast-start MP4. The low-res detector input does not limit rendered resolution.
- **Never upscale by default:** a 1920×1080 original produces a roughly 608×1080 portrait clip. A 3840×2160 original produces a 1080×1920 output. This preserves real detail rather than inventing resolution. Future web UI may offer an optional upscaled export, clearly labelled.
- Saves `highlights.json` with candidate time ranges, track IDs and scores, plus `highlight-01.mp4` etc.

## Limitations / required review

- **Current ranking chooses stable, sizeable person tracks**. It does NOT identify gender, age, buttocks, attractiveness, or sexual content. Automatic age inference from ordinary street footage is not reliable; use review to avoid inappropriate clips.
- In crowds, the greedy sparse-frame tracker may switch people or lose a person, and low-visibility bodies will be missed. The pipeline needs evaluation against real walking video before promotion.
- **No live iPhone web app yet.** The existing Render Free service is too constrained for dependable processing of very long, high-resolution ML/video jobs. A real hosted version needs appropriate compute and storage budgets and a queue, previews, a picker, and strict disk/CPU caps.
- YouTube downloading can fail due to YouTube restrictions, including PO tokens. Nothing here bypasses access controls or DRM. Save and edit only content you are entitled to use.
- The linked example `https://youtu.be/TfNJMZBIbsI` was provided as a *reference*, but its frames have not been inspected or benchmarked during this prototype.

## Run locally (Python 3.11/3.12)

Requires `ffmpeg`/`ffprobe` on PATH. `ultralytics` downloads an open YOLO pose model on first run.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m clip_engine.cli /path/to/walking-video.mp4 --clips 5 --output ./output
```

For an allowed public YouTube source:

```bash
python -m clip_engine.cli 'https://youtu.be/TfNJMZBIbsI' --clips 5 --output ./output
```

For first CPU tests use `--sample-fps 2`. To improve detection for small people, try a larger trained pose model (with more hardware).

## Tests

```bash
PYTHONPATH=. python -m pytest tests -q
```

Also verified FFmpeg rendering on a generated 1280×720 test source with an audio track: output 404×720, with audio preserved. No real-world pose inference has yet been run in this environment.

## Next steps for iPhone-first product

1. Real-source video analysis and benchmark of candidate quality; evaluate occlusion, camera motion and false tracking.
2. A fast server-side preview/contact-sheet job returning person-track candidate cards with start/end controls and selection.
3. User-selected subject anchoring, track continuity, optional vertical composition, and accurate high-resolution rendering.
4. Dedicated compute host and background job worker with storage quotas, progress UI, expiry, and direct iPhone Files delivery.
5. Preserve current production downloader until this new pipeline succeeds end-to-end.

## Efficient two-pass prototype (v0.2 experimental)

A new `clip_engine.two_pass` command changes how the first test fetches media:

1. Probe *metadata*, then sample a bounded number of short windows using a low-resolution format (480p or lower). This **does not download the entire 4K file**. Some YouTube transport formats may still transfer more bytes than requested.
2. Rank candidate person tracks from the sampled windows. These are only *candidate* highlights, not guaranteed coverage of every moment between sampled windows. Sparse scans can miss subjects entirely.
3. Fetch only the chosen **short excerpts** in the best available quality, translate tracked positions from proxy pixels to source pixels, render 9:16 clips with audio, then delete temporary source/proxy media.

```bash
python -m clip_engine.two_pass 'https://youtu.be/TfNJMZBIbsI' \
  --clips 3 --sample-every 240 --scan-seconds 22 --max-windows 12 \
  --output ./vertical-highlights
```

Optional, **local device only**, if the site's permissions and your account allow it:

```bash
python -m clip_engine.two_pass 'https://youtu.be/TfNJMZBIbsI' \
  --browser-session firefox --output ./vertical-highlights
```

The Firefox option allows yt-dlp to read an *already signed-in* session on your own computer. The session is **never copied to Render, GitHub, or the website**. It cannot be used when our code runs in GitHub Actions or Render, because those servers cannot access the user's Firefox installation. Signing into GoonHub using Google OAuth would identify the user to GoonHub, not grant yt-dlp a playable/downloadable YouTube media stream; don't add an OAuth button pretending otherwise.

**Observed limitation:** The actual sample `TfNJMZBIbsI` was tested on GitHub Actions on 2 Nov 2026 and failed at YouTube's bot-verification gate before frame analysis. It has not been processed into a real clip. [Actual job and log](https://github.com/jb0207813-cyber/goonhub/actions/runs/41439431187). This new pipeline is built and tested offline with mocked excerpt downloads and tracking; no claim of live source success.

The official YouTube API policies also place restrictions on downloading/storing YouTube audiovisual content; only import source media you have permission to save and transform. Where platform access or rights do not allow extraction, request a user-provided authorized source video rather than bypassing platform controls.