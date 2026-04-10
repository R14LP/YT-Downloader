# Grabber
A fast, dark-themed video and audio downloader built with Python and Flask.

[Download Latest Version](https://github.com/R14LP/Grabber/releases/latest)

## Changelog

### v2.3.0 (Major Update)
- **Project Renamed:** Now officially "Grabber" (GR.AB)
- **Browser Extension:** Deep integration with Chrome, Firefox, and Chromium browsers via Native Messaging.
- **In-Browser Overlay:** "⬇ GRAB" button appears directly on videos, toggleable via customizable keyboard shortcuts (Default: `Alt+D`).
- **Send to App:** Send any open page or download link directly to the app from the browser.
- **Universal File Downloading:** Direct file downloads (generic) now bypass Cloudflare and anti-bot protections using `curl_cffi` browser impersonation.
- **One-Click Installer:** Added Inno Setup script for seamless Windows installation and automatic Registry configuration.

### v2.1.0
- Added Kick.com tab — download VODs and clips
- VOD quality selection (1080p, 720p, 480p, 160p) via m3u8 parsing
- MP3 audio download support for Kick VODs
- Fixed history showing wrong format label for Kick downloads

### v2.0.1
- Fixed UPDATE button opening a new window

### v2.0.0
- Initial major release

## Features
- **Analyze before download:** See thumbnail, title, duration and available resolutions before downloading
- **Kick.com Support:** Download Kick VODs and clips directly, with quality selection
- **Clip download:** Download a specific time range — set start and end in seconds
- **Turbo Mode:** 10 simultaneous fragment downloads per file
- **Parallel downloads:** Download multiple videos at the same time (configurable 1-5)
- **High Quality:** Auto-merges video and audio — 4K, 1080p, 720p, 480p
- **WMP Compatible:** Audio re-encoded to AAC, works with Windows Media Player
- **MP3 Conversion:** Extract audio at 128, 192, or 320 kbps
- **Thumbnail embed:** Cover art embedded into MP3 and MP4 files automatically
- **Per-Video Progress:** Each video gets its own real-time progress bar with speed and ETA
- **Playlist Support:** Every video listed individually, select which ones to download
- **Cancel:** Cancel individual downloads or all at once
- **Drag to reorder:** Drag analyze cards to change download order before starting
- **Subtitle Support:** Download .srt or hardcode subtitles, disabled if video has none
- **Global Settings:** Set format, quality and subtitles for all videos at once
- **Download History:** View all downloads from the current session
- **Custom Download Folder:** Change destination folder, saved between sessions
- **Speed Limit:** Cap download speed in KB/s
- **yt-dlp Updater:** Update yt-dlp from inside the app with one click
- **Preview:** Click thumbnail after download to watch in-app
- **Open / Show in Folder:** Quick access buttons after download completes
- **Responsive UI:** Dark theme, scales with window size
- **Settings persistence:** All settings saved to config between sessions

## Installation (Windows)

1. Go to [Releases](https://github.com/R14LP/Grabber/releases/latest) and download `Grabber_Setup_v2.3.0.exe`.
2. Run the setup to install Grabber.
3. Open your browser's extension page (e.g., `chrome://extensions`).
4. Enable **Developer Mode**.
5. Click **Load unpacked** and select the `extension` folder from the source code.
6. Press `Alt+D` on any video to reveal the download button!

## Running from Source

**1. Clone the repo**
```bash
git clone https://github.com/R14LP/Grabber.git
cd YT-Downloader
```

**2. Install dependencies**
```bash
pip install flask yt-dlp pywebview pillow curl_cffi requests
```

**3. Get ffmpeg**
Download from https://www.gyan.dev/ffmpeg/builds/ — grab the `ffmpeg-release-essentials` build.
Extract `ffmpeg.exe` and `ffprobe.exe`, place them in the same folder as `app.py`.

**4. Run**
```bash
python app.py
```

## Building
Place `ffmpeg.exe`, `ffprobe.exe`, and `icon.ico` next to `app.py` before building.
```bash
pyinstaller --clean --onefile --noconsole native_host.py
pyinstaller --clean --onefile --noconsole --add-data "templates;templates" --icon "icon.ico" --name "Grabber" app.py
```
After building, place `ffmpeg.exe` and `ffprobe.exe` next to `YT_Downloader.exe` in `dist/`.

## License
MIT License - feel free to use and modify!
