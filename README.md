# YT Downloader

A fast, dark-themed video and audio downloader built with Python and Flask.

[Download Latest Version](https://github.com/R14LP/YT-Downloader/releases/latest)

## Features

- **Turbo Mode:** 10 simultaneous fragment downloads to bypass server speed limits
- **High Quality:** Auto-merges video and audio — 4K, 1080p, 720p, 480p
- **WMP Compatible:** Audio re-encoded to AAC, works with Windows Media Player
- **MP3 Conversion:** Extract audio at 128, 192, or 320 kbps
- **Per-Video Progress:** Each video gets its own real-time progress bar
- **Playlist Support:** Paste a playlist URL, every video downloads separately
- **Responsive UI:** Dark theme, scales with window size

## Running from Source

### Requirements

- Python 3.11
- ffmpeg and ffprobe

### Setup

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

## Building the exe yourself
```bash
py -m PyInstaller --clean --onefile --noconsole --add-data "templates;templates" --name "YT_Downloader" app.py
```

After building, place `ffmpeg.exe` and `ffprobe.exe` next to the generated `YT_Downloader.exe` in the `dist/` folder.

## License

MIT License - feel free to use and modify!
