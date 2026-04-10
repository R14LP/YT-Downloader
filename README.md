# Grabber
A fast, dark-themed video and audio downloader built with Python and Flask.

[Download Latest Setup](https://github.com/R14LP/Grabber/releases/latest) | [Chrome Extension](#) | [Firefox Add-on](#)

---

## 🚀 Changelog

### v2.3.0 (Major Update)
- **Project Renamed:** Now officially "Grabber" (GR.AB).
- **Browser Extension Integration:** Deep integration with Chrome, Firefox, and Chromium browsers via Native Messaging.
- **In-Browser Overlay:** "⬇ GRAB" button appears directly on videos, toggleable via customizable keyboard shortcuts (Default: `Alt+D`).
- **Send to App:** Send any open page or download link directly to the local desktop app from your browser securely.
- **Universal File Downloading:** Direct file downloads (generic) now bypass Cloudflare and anti-bot protections using `curl_cffi` browser impersonation.
- **One-Click Installer:** Added Inno Setup script for seamless Windows installation and automatic Native Messaging Registry configuration.

### v2.1.0
- Added Kick.com tab — download VODs and clips.
- VOD quality selection (1080p, 720p, 480p, 160p) via m3u8 parsing.
- MP3 audio download support for Kick VODs.

### v2.0.0 & v2.0.1
- Initial major release with drag-and-drop reordering, Turbo Mode, and UI fixes.

---

## ✨ Features
- **Analyze before download:** See thumbnail, title, duration, and available resolutions before downloading.
- **Kick.com & Universal Support:** Download from Kick and bypass Cloudflare for standard URLs.
- **Parallel & Turbo Downloads:** Download multiple videos at once, with up to 10 simultaneous fragments per file.
- **High Quality & Auto-Merge:** Automatically merges 4K/1080p video with the best audio.
- **Format Conversion:** MP3 (128/192/320 kbps) and WMP compatible AAC audio.
- **Thumbnail Embed:** Cover art embedded into MP3 and MP4 files automatically.
- **Per-Video Progress:** Real-time progress bars with speed (KB/s) and ETA.
- **Advanced Control:** Drag to reorder queue, individual cancel buttons, and global speed limits.
- **Subtitle Support:** Download `.srt` or hardcode subtitles directly into the video.
- **Built-in Updater:** Update `yt-dlp` from inside the app with one click.
- **Responsive Dark UI:** Scales cleanly with your window size, preserving settings between sessions.

---

## 💻 Installation (Recommended for Users)

The easiest way to use Grabber is via the official installer, which automatically configures the background bridges required for the browser extension.

1. Go to [Releases](https://github.com/R14LP/Grabber/releases/latest) and download `Grabber_Setup_v2.3.0.exe`.
2. Run the installer. *(This automatically registers the Native Messaging Host in your Windows Registry.)*
3. Install the official **Grabber Helper** extension for your browser:
   - **Chrome / Edge / Brave:** [Link to Chrome Web Store]
   - **Firefox:** [Link to Firefox Add-ons]
4. Open any video page, press `Alt+D`, and click **Grab** to send it directly to the app!

---

## 🛠️ Running & Installing from Source (For Developers)

If you want to run Grabber from the source code or modify the extension yourself, you need to manually configure the Native Messaging bridge.

### 1. Clone the repo
```bash
git clone https://github.com/R14LP/Grabber.git
cd Grabber
```

### 2. Install dependencies
```bash
pip install flask yt-dlp pywebview pillow curl_cffi requests
```

### 3. Get FFmpeg
1. Download from [gyan.dev](https://gyan.dev) (grab the `ffmpeg-release-essentials` build).
2. Extract `ffmpeg.exe` and `ffprobe.exe`.
3. Place them in the `dist/` folder (or next to `app.py` if running raw).

### 4. Setup the Custom Browser Extension (Unpacked)

If you are developing and want to load the local extension instead of the store version:

1. Open your browser's extension page (`chrome://extensions` or `about:debugging`).
2. Enable **Developer Mode**.
3. Click **Load unpacked** and select either the `extension_chrome` or `extension_firefox` folder.
4. **Important:** Chrome will generate a new random Extension ID. Copy this ID.

### 5. Configure Native Messaging Manually

To allow the unpacked extension to talk to your local Python script:

1. Open `grabber_host.json`.
2. Update the `path` to point to the absolute path of your compiled `native_host.exe` (or a `.bat` wrapper pointing to `native_host.py`). Remember to use double backslashes (`\\`).
3. Update `allowed_origins` with the new Extension ID you got from Chrome in Step 4.
4. **Add to Registry:** Open Command Prompt as Administrator and run the following command *(replace the path with your actual JSON path)*:

```dos
REG ADD "HKCU\Software\Google\Chrome\NativeMessagingHosts\grabber_host" /ve /t REG_SZ /d "C:\Path\To\Your\grabber_host.json" /f
```

> For Firefox, replace `Google\Chrome` with `Mozilla` in the registry path.

### 6. Run the App
```bash
python app.py
```

---

## 📦 Building the Executables

You must compile `native_host.py` separately so the browser can execute it silently in the background.

```bash
# 1. Build the invisible background bridge
pyinstaller --clean --onefile --noconsole native_host.py

# 2. Build the main Grabber application
pyinstaller --clean --onefile --noconsole --add-data "templates;templates" --icon "icon.ico" --name "Grabber" app.py
```

After building, ensure `ffmpeg.exe`, `ffprobe.exe`, and `grabber_host.json` are placed in the same directory as the compiled `.exe` files.

---

## 📄 License

MIT License — feel free to use and modify!
