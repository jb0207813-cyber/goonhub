# GoonHub — Product & UI/UX Design Specification

**Version:** 1.0  
**Date:** 2026-11-02  
**Status:** Proposed redesign; not yet implemented  
**Primary device:** iPhone / Safari / installable PWA  
**Repository:** https://github.com/jb0207813-cyber/goonhub

## 1. Product vision

GoonHub is a fast, minimal, iPhone-first tool for downloading publicly accessible X, Instagram and Facebook photos and videos that the user is entitled to save. It should look and feel as polished and intuitive as X on iPhone, without copying X's branding. It is a **media downloader**, not a social network, content discovery engine, vault or media gallery.

**Core promise:** Copy a social-media post URL, paste it into GoonHub, preview the available media, and download in the best usable quality with sound when the source contains audio.

**Non-goals for v1:** User accounts, login, passwords, encryption screens, likes/saves syncing, third-party downloader websites, feed aggregation, recommendation engines, private-post access, DRM bypass, creator tracking, permanent cloud storage and a persistent media gallery.

### Product principles

1. **One clear job.** Paste → Preview → Download. Every screen supports that flow.
2. **Respect the user's time.** No onboarding, registration, pop-ups, or unnecessary menus.
3. **Truthful feedback.** Never claim a download succeeded until a file exists; never claim a file reached Photos or Files without confirmation from iOS.
4. **X-inspired, not copied.** Adopt the calm dark timeline, crisp hierarchy, compact post cards, restrained blue actions and thin dividers; use original GoonHub brand and icons.
5. **No external downloader websites.** Extraction is performed by our own backend using locally installed open-source libraries. Upstream platforms are still external dependencies.
6. **Graceful failure.** Access restrictions and upstream changes are communicated clearly; unsupported posts are never silently broken.

## 2. User and devices

Primary user: one person opening an installed GoonHub web app on an iPhone, often after copying a link in X, Instagram, or Facebook. Secondary usage: desktop browser for testing and occasional downloads.

The app must be usable one-handed on a 375–430px mobile viewport, with iOS safe areas, notched displays, Safari keyboard behavior, and a reliable browser-based download path. Desktop layout should be polished but secondary.

## 3. Information architecture

Only **two primary destinations**:

- **Home:** paste link, analyze, see source preview, choose media/quality, download.
- **Activity:** current-session download jobs, progress, results, retry and clear. This is a task queue, not a permanent gallery.

A small **Settings** sheet, opened from the header, contains appearance, storage/privacy explanation, backend status, and About. No bottom-navigation Settings tab and no password/lock action.

Navigation: sticky top header with GoonHub wordmark, optional slim underline tabs **Home | Activity**, and a sticky bottom nav on mobile containing only Home and Activity icons/labels (if it adds value). Avoid duplicate large toolbars. Mobile content remains one full-width central column; desktop central column max-width 640px.

## 4. Visual design system

### 4.1 Appearance and branding

Default: X-like **dark mode**, not purple/neon. Use an original GoonHub identity, not the X logo.

| Token | Value | Use |
|---|---|---|
| Page background | #000000 | Main app background |
| Raised surface | #0F1419 | Inputs, subtle sheets |
| Primary text | #EFF3F4 | Headlines and body text |
| Secondary text | #71767B | Metadata, hints |
| Hairline divider | #2F3336 | Posts and sections |
| Accent / CTA | #1D9BF0 | Primary button, active tab |
| Accent hover | #1A8CD8 | Press feedback |
| Success | #00BA7C | File ready |
| Error | #F4212E | Errors only |
| Warning | #FFD400 | Limited availability |

Prefer system font (-apple-system / SF Pro), normal case, precise font weights, and no gradients, glassmorphism, chunky cards, glowing borders, decorative emoji, or oversized empty panels. Media corners 12–16px; input corners 12px; primary buttons pill-shaped.

### 4.2 Type and spacing

- Wordmark: 20–22px, bold.
- Screen heading: 20px, semibold, not a giant hero banner.
- Post/preview title: 15–16px, semibold.
- Body text: 15px, line-height 1.4–1.5.
- Metadata/captions: 13px, secondary.
- Compact 8px spacing scale: 4, 8, 12, 16, 24, 32.
- Mobile horizontal padding 16px; feed items separated by 1px dividers.
- Controls have at least 44×44px touch targets; visible keyboard focus and legible contrast.

### 4.3 Layout

**iPhone:**
- Top: GoonHub left, small status/options icon right.
- Primary composer immediately visible: label "Paste a post link", URL field, clear control, **Paste** shortcut button and a single full-width **Find media** action.
- After analysis, the results appear inline below the composer, in a post-style row: platform indicator, real creator/title if available, source link, preview poster, media count and available actions.
- Format selection is compact; only show options actually available.
- Bottom nav respects safe-area inset and never covers the download CTA, progress, or iOS keyboard.

**Desktop:**
- Dark narrow central timeline (max-width 640px), subtle side gutters, no stretched controls.
- Optional narrow left rail for Home/Activity; no decorative right sidebar.

## 5. Primary screens and interactions

### Screen A — Home / Empty

**Visible without authentication.** Header; one link field; secondary **Paste** button (reads clipboard only after a tap, where browser permission allows); primary **Find media** button; brief "Works with public X, Instagram and Facebook posts" hint.

Automatic source detection after a URL is entered; no platform dropdown required. Submission allowed with Return / Enter. Disabled actions must have understandable reasons.

A link copied from a post should require at most two taps within GoonHub to start analysis: Paste, Find media. If clipboard APIs are blocked, manual paste always works.

### Screen B — Analyzing

Keep the input and layout stable. Show a small indeterminate status with "Checking this post…" and a Cancel option. Do not use a full-screen spinner. Timeouts must produce a clear retry option.

### Screen C — Media preview

Render an X-inspired post card:
- Platform icon / label; real creator display name and handle if the extractor returns them.
- Optional short source text, timestamp and "View original" link.
- Large image/video poster (16:9, portrait or original aspect ratio as appropriate).
- For multiple media items, use a swipeable horizontal carousel with count indicator and checkboxes/select-all.
- On supported video, user-initiated playback with an unambiguous sound/mute control. Never assume muted playback means the source is silent.
- Details: photo/video count, available resolution, duration and audio status when known.
- Primary **Download** button; **Download all** when multiple items.
- Quality menu defaults to **Best available**, with only verified source-derived quality choices. No fake 1080p option.
- If metadata is missing, show a neutral platform placeholder; never fabricate creator names, thumbnails or quality.

### Screen D — Download progress and file delivery

Transition through: Validating → Analyzing → Ready → Downloading source → Processing audio/video (when necessary) → File ready → Browser download requested.

The UI must distinguish **File ready** from **Saved to iPhone**. A real file download starts by navigating to an expiring backend file URL or downloading a same-origin attachment. Provide **Download again** while the job is valid, and **Find in Files** instructions (do not claim direct access to the iOS Files app).

If video and audio are separate at source, merge them server-side into an iPhone-compatible MP4 when possible. Verify tracks with ffprobe; test actual audible playback on iPhone. If the original has no audio, state "Source video has no audio" rather than implying a processing error.

For multi-photo posts: selection and individual downloads; **Download all as ZIP** when technically supported. Name files safely and predictably, e.g. goonhub_x_123456_video.mp4 or goonhub_instagram_ABC_photo_01.jpg.

### Screen E — Activity (session only)

Show an uncluttered vertical list of jobs created during the current session. Each row includes platform, small poster if available, status, size if known, progress, retry and re-download action. Do not turn this into a permanent gallery or store media files in the browser. Provide **Clear activity**. No analytics-style dashboard.

### Screen F — Settings / About

Only essentials: appearance (dark default; optional system/light later), backend status indicator, privacy and media retention summary, app version, GitHub link, and troubleshooting. No vault, passwords, login, followers, notifications, or unused toggles.

## 6. Platform support contract

Support applies **only to media our backend can actually retrieve with permitted access**, and is best-effort rather than guaranteed.

| Platform | Target inputs | Expected v1 behavior | Honest limitations |
|---|---|---|---|
| X | Public posts with video, photos, GIF-like clips | Download eligible images and playable MP4 with audio when present | Restricted/deleted/login-gated posts or extractor changes can fail |
| Instagram | Public reels, posts, videos, carousels | Preview and download media exposed by extraction | Some posts may require authentication or be inaccessible |
| Facebook | Public video and Reels; public post media when extractable | Download supported video and images | Photo posts and restricted/public-but-login-gated posts may not be extractable |

Do not promise 100% platform coverage. Failure on one platform must not break the others. Each platform uses its own adapter and acceptance tests. No feature may request the user's X/Meta passwords or session cookies in the MVP. Do not bypass DRM, private access controls, or paywalls.

## 7. Architecture

### Frontend

- React + TypeScript + Vite; semantic components, lightweight CSS variables or scoped styles.
- PWA with web manifest, app icon and static-shell offline cache. Offline app shell is not offline media extraction.
- Existing GitHub Pages hosting may remain for the frontend.
- Components: AppShell, LinkComposer, SourceBadge, PostPreview, MediaCarousel, QualityPicker, DownloadProgress, ActivityList, ErrorState, SettingsSheet.
- State-driven UI: avoid scattered document.getElementById handlers; keep analysis/download states typed and testable.
- Clipboard Paste uses browser permissions only on user activation; manual paste is always available.

### Backend

- Our own Python FastAPI service, hosted on a reachable HTTPS backend.
- yt-dlp installed locally for extractor support; FFmpeg/ffprobe installed locally for audio/video merging and verification.
- Platform adapters validate supported URLs, normalize mobile/short links, and map returned metadata to one internal schema.
- A bounded job queue manages extraction and processing. Avoid doing long downloads synchronously in HTTP request handlers.
- Ephemeral storage only: job files expire after 30 minutes by default; delete failed/expired jobs and files safely.
- Return binary files with correct Content-Type, Content-Length where available and Content-Disposition: attachment, with safe ASCII filenames.
- **GitHub Pages alone cannot perform extraction, merge media, or keep FFmpeg running.** Hosting and bandwidth cost must be evaluated; a free, guaranteed unlimited downloader is not promised.
- No hosted FxEmbed endpoint or other downloader proxy. Open-source library code is a dependency, not a third-party download website.

### Suggested API

| Endpoint | Purpose |
|---|---|
| POST /api/v1/analyze | Validate URL and return source metadata and selectable media, or an async analysis ID |
| POST /api/v1/jobs | Create a bounded download/merge job from an analysis ID and selected media |
| GET /api/v1/jobs/{id} | Return status, progress, failure code and available output files |
| GET /api/v1/files/{id}?token=... | Download a short-lived finished file/ZIP as attachment |
| DELETE /api/v1/jobs/{id} | Cancel/clear an active job or purge its temporary files |
| GET /api/v1/health | Basic backend readiness and extractor/FFmpeg availability |

Example analysis result fields: analysis_id, platform, source_url, creator_name (nullable), caption (nullable), poster_url (nullable), media[{id, kind, width, height, duration_seconds, has_audio (true/false/unknown), available_qualities}], expires_at.

### Security, privacy and responsible use

- No GoonHub user login or lock screen.
- Never ask for social account credentials or push cookies/tokens to the server.
- Public downloader endpoints require strict platform/domain allowlists, URL/redirect validation, denial of private-IP and metadata endpoints (SSRF protection), request timeouts, file-size limits, rate limits and bounded concurrency.
- Restrict browser CORS to the deployed frontend origin; do not treat CORS as server authentication. Avoid becoming an arbitrary public URL proxy.
- Redact source URLs and creator details from long-lived server logs. No analytics scripts by default.
- Use randomized job IDs and short-lived file URLs, delete server-side temporary files, and don't publish completed files to GitHub.
- Handle only content the user is allowed to save; respect copyright, creators' rights and applicable platform conditions.
- Existing v0.2 encrypted local-storage vault data must **not be silently erased during migration**; deprecate the feature without reading or exposing old records, and provide a safe explicit cleanup option later.

## 8. Errors and edge cases

Use precise, helpful messages:
- Invalid URL: "Paste a link to an X, Instagram or Facebook post."
- Unsupported URL type: "This link isn't a supported post or Reel."
- Access restricted: "This post isn't available publicly."
- Media not found: "We couldn't find downloadable media in this post."
- Service changed: "This platform changed how its media is served. Try again later."
- Audio unavailable: "The source doesn't contain an audio track."
- Rate limited: "Too many downloads right now. Please try again later."
- Network interrupted: "Connection lost. Retry the download."
- File too large: show configured limit and do not leave temp files behind.

Never offer a silent video as a successful "with sound" download. Never fake success based on third-party metadata or a visible thumbnail.

## 9. iPhone specifics

- Serve over HTTPS and provide a valid PWA manifest and icon.
- Respect Safari Downloads and Files behavior; use an attachment response instead of assuming a browser click saves to Photos.
- Describe the expected path: Safari Downloads / Files app; users can move supported items to Photos themselves.
- Avoid auto-playing videos with sound (iOS gesture restriction). Playback is user initiated.
- Prevent accidental loss of job progress on tab switches; render correct states after screen rotation and keyboard opening.
- Test in Safari **and** the installed Home Screen web app. Their download handling may differ.
- Fast, low-data thumbnails, lazy-load posters, and never automatically download a full video merely to preview a post.

## 10. Nonfunctional requirements

- Responsive at 320px through desktop; primary QA at 375px and 390px iPhone viewports.
- App shell interactive quickly on a normal mobile connection (target under 2 seconds excluding network/server delays).
- Visible feedback within 100ms of pressing an action; never freeze the main thread for extraction or file processing.
- WCAG 2.2 AA contrast targets, 44px tap targets, screen reader labels, reduced-motion preference, visible focus and semantic progress/status announcements.
- Backend limits: configurable max file size, job timeout, concurrency and per-IP usage quota; never silently charge for an external paid API.
- Graceful degradation when extractors fail; platform errors isolated and surfaced with useful messages.

## 11. Acceptance tests / Definition of Done

The redesign is **not done** because the interface looks right. A release must pass:

1. Fresh iPhone visit opens Home immediately without login, passphrase or vault setup.
2. Valid public X video link → post preview → MP4 with actual audible audio if audio exists in the source; verified with ffprobe and physical iPhone playback.
3. Public X photo link → full-resolution available photo download; multi-photo link exposes correct item count.
4. Supported public Instagram Reel/post → valid downloadable video or image, with accurate failure messaging when not extractable.
5. Supported public Facebook video/Reel → playable file including source audio when present; unsupported photo posts fail truthfully.
6. Invalid, deleted, private, access-restricted, unsupported and rate-limited links show actionable error states.
7. Download action yields a real file in iPhone Safari/Files, not just a preview opened in a new tab.
8. User can paste, edit, clear, re-try and cancel without stale cards or duplicate jobs.
9. No external downloader website, X API credit purchase, social account password prompt, or hidden cloud gallery.
10. No regressions on a seed list of public test posts across all three platforms; automated unit tests cover URL parsing, adapters, state transitions and SSRF defenses.
11. Existing v0.2 local data isn't destroyed automatically.
12. Basic accessibility and responsive checks pass in Safari and desktop browsers.

## 12. Implementation sequence

**Phase 0 — Repository baseline:** Preserve v0.2 as a tag/branch; write this spec, platform test matrix and UI snapshot tests. No loss of existing user data.

**Phase 1 — Beautiful frontend shell:** Rebuild from scratch in React/TypeScript, X-inspired visual system, Home → analyzing → preview → activity, with mocked deterministic fixtures. Remove vault/lock/gallery/feed UI. Deploy frontend.

**Phase 2 — Real X downloader:** Stand up own FastAPI + yt-dlp + FFmpeg backend. Prove X public photos and videos, including audio mux and iPhone file delivery. Test failures and constraints. No reliance on FxEmbed.

**Phase 3 — Instagram and Facebook adapters:** Add supported public Reels/posts/video, image flows where extractable, platform-specific fixtures and graceful restricted-content errors.

**Phase 4 — iPhone polish:** Improve PWA icon, cached shell, clipboard behavior, progress, retry, ZIP for multi-media, quality choices and accessibility. Add optional iOS Shortcuts URL hand-off later only if reliably supported.

**Release criterion:** Three-platform best-effort download workflows validated on real test links and actual iPhone. Call unsupported formats unsupported; don't ship misleading buttons.

## 13. Research/technical references

- yt-dlp extractor support and changing-site caveat: https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md
- yt-dlp format selection and FFmpeg merging: https://github.com/yt-dlp/yt-dlp/blob/master/README.md
- Apple Downloads in Files: https://support.apple.com/en-au/102440
- Apple Dark Mode HIG: https://developer.apple.com/design/human-interface-guidelines/dark-mode

**Design decision summary:** Build a beautifully executed, X-inspired **downloader**, not an imitation social network. The user enters a link and receives a real, working, correctly processed media file. Everything else is secondary.
