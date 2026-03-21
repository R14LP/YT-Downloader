# YT Downloader

A fast, dark-themed video and audio downloader built with Python and Flask.

[Download Latest Version](https://github.com/R14LP/YT-Downloader/releases/latest)

## Features

- **Analyze before download:** See thumbnail, title, duration and available resolutions before downloading
- **Turbo Mode:** 10 simultaneous fragment downloads
- **High Quality:** Auto-merges video and audio — 4K, 1080p, 720p, 480p
- **WMP Compatible:** Audio re-encoded to AAC, works with Windows Media Player
- **MP3 Conversion:** Extract audio at 128, 192, or 320 kbps
- **Per-Video Progress:** Each video gets its own real-time progress bar with speed and ETA
- **Playlist Support:** Every video in a playlist listed and downloaded separately
- **Global Settings:** Set format, quality and subtitles for all videos at once with Apply to All
- **Subtitle Support:** Download .srt or hardcode subtitles into the video — disabled automatically if video has no subtitles
- **Download History:** View all downloads from the current session in the History tab
- **Custom Download Folder:** Change the destination folder at any time
- **Preview:** Click thumbnail after download to watch in-app
- **Open / Show in Folder:** Quick access buttons after download completes
- **Responsive UI:** Dark theme, scales with window size

## Running from Source

**1. Clone the repo**
```bash
git clone https://github.com/R14LP/YT-Downloader.git
cd YT-Downloader
```

**2. Install dependencies**
```bash
pip install flask yt-dlp pywebview
```

**3. Get ffmpeg**

Download from https://www.gyan.dev/ffmpeg/builds/ — grab the `ffmpeg-release-essentials` build.
Extract `ffmpeg.exe` and `ffprobe.exe`, place them in the same folder as `app.py`.

**4. Run**
```bash
python app.py
```

## Building
```bash
py -m PyInstaller --clean --onefile --noconsole --add-data "templates;templates" --name "YT_Downloader" app.py
```

Place `ffmpeg.exe` and `ffprobe.exe` next to `YT_Downloader.exe` in `dist/`.

## License

MIT License - feel free to use and modify!
