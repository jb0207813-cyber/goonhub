# GoonHub

Private, installable iPhone-first bookmark feed and discovery launchpad.

This repo is the source code only. Saved links stay encrypted in your browser's local storage; no saved content or passwords are committed.

## Launch

Enable GitHub Pages from Settings → Pages → Deploy from branch → `main` / root, then visit `https://jb0207813-cyber.github.io/goonhub/` in Safari and use Add to Home Screen.

## Features

Encrypted local vault; save/edit/delete/favourite URLs; platform filters; external discovery searches; export/import encrypted backups. This is not a live social network aggregator or unrestricted scraper.


## X media downloads (v0.2)

In GoonHub, open **Download**, paste a public `https://x.com/handle/status/123...` link, and choose **Find media**. The app tries the **free, unofficial FxEmbed public metadata service** to list photo/video files. It also provides a direct-media link even if the lookup fails (for example due to browser CORS, rate limiting, X restrictions, or third-party outages). From Safari, open the image/video file, then use the share menu to save to Files or Photos where supported.

**No X API credits or keys are needed.** This is not a guaranteed downloader: private/protected/deleted/age-gated posts can be unavailable, and third-party services may change. The post ID is sent to FxEmbed on lookup, and opening media exposes normal requests to media hosts. Never share account cookies, credentials, or private vault backups with third-party sites. Download only media you have the rights or permission to save.

The **existing encrypted vault format was preserved** by the v0.2 update.
