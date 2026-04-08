from flask import Flask, render_template, request, jsonify, send_file
import yt_dlp
import os
import re
import sys
import threading
import webview
import subprocess
import json
import shutil
import urllib.parse
import uuid as uuid_mod
from curl_cffi import requests as cffi_requests

if getattr(sys, 'frozen', False):
    template_folder = os.path.join(sys._MEIPASS, 'templates')
    app = Flask(__name__, template_folder=template_folder)
    app_path = os.path.dirname(sys.executable)
else:
    app = Flask(__name__)
    app_path = os.path.dirname(os.path.abspath(__file__))

os.chdir(app_path)

DOWNLOAD_FOLDER = os.path.join(os.path.expanduser("~"), "Downloads")
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

CONFIG_FILE = os.path.join(app_path, 'config.json')

def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_config(data):
    try:
        existing = load_config()
        existing.update(data)
        with open(CONFIG_FILE, 'w') as f:
            json.dump(existing, f)
    except:
        pass

app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

@app.after_request
def no_cache(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    return response

downloads = {}
pending_downloads = {}
downloads_lock = threading.Lock()
cancel_flags = {}
cancel_flags_lock = threading.Lock()
history = []
history_lock = threading.Lock()
window_ref = None
speed_limit = 0
max_concurrent = 1

cfg = load_config()
if cfg.get('download_folder'):
    DOWNLOAD_FOLDER = cfg['download_folder']
speed_limit = cfg.get('speed_limit', 0)
max_concurrent = cfg.get('max_concurrent', 1)

def remove_ansi_colors(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def clean_filename(title):
    cleaned = re.sub(r'[\\/*?:"<>|]', '', title)
    cleaned = cleaned.strip()
    return cleaned or 'download'

def get_unique_filepath(folder, title, ext):
    base = clean_filename(title)
    filepath = os.path.join(folder, f'{base}.{ext}')
    if not os.path.exists(filepath):
        return filepath
    counter = 1
    while os.path.exists(os.path.join(folder, f'{base} ({counter}).{ext}')):
        counter += 1
    return os.path.join(folder, f'{base} ({counter}).{ext}')

def get_python_exe():
    if getattr(sys, 'frozen', False):
        python_exe = os.path.join(os.path.dirname(sys.executable), 'python.exe')
        if not os.path.exists(python_exe):
            python_exe = shutil.which('python') or shutil.which('python3') or 'python'
    else:
        python_exe = sys.executable
    return python_exe

def make_hook(vid_id):
    def progress_hook(d):
        with cancel_flags_lock:
            if cancel_flags.get(vid_id):
                raise Exception('Cancelled')
        with downloads_lock:
            if vid_id not in downloads:
                return
            if d['status'] == 'downloading':
                downloads[vid_id]['status'] = 'Downloading...'
                percent_str = remove_ansi_colors(d.get('_percent_str', '0.0%')).strip()
                try:
                    downloads[vid_id]['percent'] = float(percent_str.replace('%', ''))
                except:
                    downloads[vid_id]['percent'] = 0.0
                downloads[vid_id]['speed'] = remove_ansi_colors(d.get('_speed_str', '-')).strip()
                downloads[vid_id]['eta'] = remove_ansi_colors(d.get('_eta_str', '-')).strip()
            elif d['status'] == 'finished':
                downloads[vid_id]['status'] = 'Finalizing...'
                downloads[vid_id]['percent'] = 100.0
    return progress_hook

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    urls_text = request.form.get('urls', '')
    urls = [u.strip() for u in urls_text.split('\n') if u.strip()]
    if not urls:
        return jsonify({"status": "error", "message": "No links provided."})

    def is_direct_file(url):
        direct_exts = {
            '.bin', '.exe', '.zip', '.rar', '.7z', '.tar', '.gz',
            '.pdf', '.iso', '.dmg', '.pkg', '.deb', '.rpm',
            '.apk', '.msi', '.torrent', '.csv', '.xlsx', '.docx',
        }
        parsed = urllib.parse.urlparse(url)
        if 'kick.com' in parsed.netloc:
            return False
        path = parsed.path.lower()
        _, ext = os.path.splitext(path)
        return ext in direct_exts

    results = []
    for url in urls:
        if is_direct_file(url):
            filename = os.path.basename(urllib.parse.urlparse(url).path) or 'file'
            results.append({
                'type': 'generic',
                'title': filename,
                'thumbnail': '',
                'duration': '',
                'url': url,
                'heights': [],
                'has_subs': False,
                'sub_langs': [],
            })
            continue
        try:
            with yt_dlp.YoutubeDL({'quiet': True, 'noplaylist': False, 'extract_flat': 'in_playlist'}) as ydl:
                info = ydl.extract_info(url, download=False)

            if 'entries' in info:
                playlist_entries = []
                for entry in info['entries']:
                    thumb = ''
                    if entry.get('thumbnails'):
                        thumb = entry['thumbnails'][-1].get('url', '')
                    elif entry.get('thumbnail'):
                        thumb = entry['thumbnail']
                    playlist_entries.append({
                        'title': entry.get('title', 'Unknown'),
                        'thumbnail': thumb,
                        'duration': entry.get('duration_string', ''),
                        'url': entry.get('url') or entry.get('webpage_url') or f"https://www.youtube.com/watch?v={entry['id']}",
                        'selected': True,
                    })
                results.append({
                    'type': 'playlist',
                    'title': info.get('title', 'Playlist'),
                    'thumbnail': info.get('thumbnail', '') or (playlist_entries[0]['thumbnail'] if playlist_entries else ''),
                    'url': url,
                    'entries': playlist_entries,
                    'has_subs': False,
                    'sub_langs': [],
                    'heights': [1080, 720, 480],
                })
            else:
                formats = info.get('formats', [])
                heights = sorted(set(
                    f['height'] for f in formats
                    if f.get('height') and f.get('vcodec') != 'none'
                ), reverse=True)

                subs = info.get('subtitles', {})
                has_subs = len(subs) > 0
                sub_langs = [{'code': lang, 'label': lang, 'auto': False} for lang in subs.keys()]

                results.append({
                    'type': 'video',
                    'title': info.get('title', 'Unknown'),
                    'thumbnail': info.get('thumbnail', ''),
                    'duration': info.get('duration_string', ''),
                    'url': url,
                    'heights': heights if heights else [1080, 720, 480],
                    'has_subs': has_subs,
                    'sub_langs': sub_langs,
                })
        except Exception as e:
            filename = os.path.basename(urllib.parse.urlparse(url).path) or 'file'
            results.append({
                'type': 'generic',
                'title': filename,
                'thumbnail': '',
                'duration': '',
                'url': url,
                'heights': [],
                'has_subs': False,
                'sub_langs': [],
            })

    return jsonify({"status": "success", "results": results})

@app.route('/progress')
def progress():
    with downloads_lock:
        return jsonify(downloads)

@app.route('/history')
def get_history():
    with history_lock:
        return jsonify(history)

@app.route('/select_folder', methods=['POST'])
def select_folder():
    global DOWNLOAD_FOLDER, window_ref
    if window_ref is None:
        return jsonify({"status": "error", "message": "Window not ready."})
    result = window_ref.create_file_dialog(webview.FOLDER_DIALOG)
    if result and len(result) > 0:
        DOWNLOAD_FOLDER = result[0]
        save_config({'download_folder': DOWNLOAD_FOLDER})
        return jsonify({"status": "ok", "folder": DOWNLOAD_FOLDER})
    return jsonify({"status": "cancelled"})

@app.route('/get_folder')
def get_folder():
    return jsonify({"folder": DOWNLOAD_FOLDER})

@app.route('/set_speed_limit', methods=['POST'])
def set_speed_limit():
    global speed_limit
    try:
        val = int(request.form.get('limit', 0))
        speed_limit = max(0, val)
        save_config({'speed_limit': speed_limit})
        return jsonify({"status": "ok", "limit": speed_limit})
    except:
        return jsonify({"status": "error"})

@app.route('/get_speed_limit')
def get_speed_limit():
    return jsonify({"limit": speed_limit})

@app.route('/set_max_concurrent', methods=['POST'])
def set_max_concurrent():
    global max_concurrent
    try:
        val = int(request.form.get('value', 1))
        max_concurrent = max(1, min(5, val))
        save_config({'max_concurrent': max_concurrent})
        return jsonify({"status": "ok", "value": max_concurrent})
    except:
        return jsonify({"status": "error"})

@app.route('/get_settings')
def get_settings():
    return jsonify({
        "folder": DOWNLOAD_FOLDER,
        "speed_limit": speed_limit,
        "max_concurrent": max_concurrent,
    })

@app.route('/save_window_size', methods=['POST'])
def save_window_size():
    try:
        w = int(request.form.get('width', 560))
        h = int(request.form.get('height', 900))
        save_config({'window_width': w, 'window_height': h})
        return jsonify({"status": "ok"})
    except:
        return jsonify({"status": "error"})

@app.route('/cancel_download', methods=['POST'])
def cancel_download():
    vid_id = request.form.get('vid_id')
    if not vid_id:
        return jsonify({"status": "error"})
    with cancel_flags_lock:
        cancel_flags[vid_id] = True
    with downloads_lock:
        if vid_id in downloads:
            downloads[vid_id]['cancelled'] = True
    return jsonify({"status": "ok"})

@app.route('/cancel_all', methods=['POST'])
def cancel_all():
    with downloads_lock:
        ids = list(downloads.keys())
    with cancel_flags_lock:
        for vid_id in ids:
            if vid_id != '__update__':
                cancel_flags[vid_id] = True
    with downloads_lock:
        for vid_id in ids:
            if vid_id != '__update__' and vid_id in downloads:
                downloads[vid_id]['cancelled'] = True
    return jsonify({"status": "ok"})

@app.route('/remove_download', methods=['POST'])
def remove_download():
    vid_id = request.form.get('vid_id')
    if not vid_id:
        return jsonify({"status": "error"})
    with downloads_lock:
        downloads.pop(vid_id, None)
    with cancel_flags_lock:
        cancel_flags.pop(vid_id, None)
    return jsonify({"status": "ok"})

@app.route('/update_ytdlp', methods=['POST'])
def update_ytdlp():
    def do_update():
        with downloads_lock:
            downloads['__update__'] = {
                'title': 'yt-dlp update',
                'status': 'Updating...',
                'percent': 0.0,
                'speed': '-',
                'eta': '-',
                'done': False,
                'error': False,
                'filepath': None,
                'thumbnail': '',
                'is_update': True,
            }
        try:
            python_exe = get_python_exe()
            kwargs = {'capture_output': True, 'text': True}
            if sys.platform == 'win32':
                kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
            result = subprocess.run(
                [python_exe, '-m', 'pip', 'install', '--upgrade', 'yt-dlp', '--quiet'],
                **kwargs
            )
            success = result.returncode == 0
            with downloads_lock:
                if '__update__' in downloads:
                    downloads['__update__']['status'] = 'Updated!' if success else 'Update failed'
                    downloads['__update__']['percent'] = 100.0
                    downloads['__update__']['done'] = success
                    downloads['__update__']['error'] = not success
        except Exception as e:
            with downloads_lock:
                if '__update__' in downloads:
                    downloads['__update__']['status'] = f'Error: {str(e)}'
                    downloads['__update__']['error'] = True

    t = threading.Thread(target=do_update)
    t.daemon = True
    t.start()
    return jsonify({"status": "ok"})

@app.route('/retry_download', methods=['POST'])
def retry_download():
    vid_id = request.form.get('vid_id')
    if not vid_id:
        return jsonify({"status": "error"})

    with downloads_lock:
        if vid_id not in downloads:
            return jsonify({"status": "error", "message": "Download not found."})
        entry = {
            'url': downloads[vid_id]['url'],
            'title': downloads[vid_id]['title'],
            'thumbnail': downloads[vid_id].get('thumbnail', ''),
            'type': downloads[vid_id].get('type', 'video'),
            'fmt': downloads[vid_id].get('fmt', 'video'),
            'qual': downloads[vid_id].get('qual', '1080'),
            'sub': downloads[vid_id].get('sub', 'none'),
            'sub_langs': downloads[vid_id].get('sub_langs', ['en']),
            'clip_start': downloads[vid_id].get('clip_start'),
            'clip_end': downloads[vid_id].get('clip_end'),
        }
        downloads[vid_id].update({
            'status': 'Retrying...',
            'percent': 0.0,
            'speed': '-',
            'eta': '-',
            'done': False,
            'error': False,
            'cancelled': False,
            'filepath': None,
        })

    with cancel_flags_lock:
        cancel_flags[vid_id] = False

    def do_retry():
        _run_single(vid_id, entry, entry['fmt'], entry['qual'], entry['sub'], entry['sub_langs'],
                    entry.get('clip_start'), entry.get('clip_end'))

    t = threading.Thread(target=do_retry)
    t.daemon = True
    t.start()
    return jsonify({"status": "ok"})

def _guess_filename(url, headers):
    cd = headers.get('Content-Disposition', '')
    match = re.findall(r'filename\*?=["\']?(?:UTF-8\'\')?([^"\';\r\n]+)', cd, re.IGNORECASE)
    if match:
        return urllib.parse.unquote(match[-1].strip())
    path = urllib.parse.urlparse(url).path
    name = os.path.basename(urllib.parse.unquote(path))
    if name and '.' in name:
        return name
    ct = headers.get('Content-Type', '').split(';')[0].strip()
    ext_map = {
        'application/pdf': '.pdf', 'application/zip': '.zip',
        'application/x-rar-compressed': '.rar', 'application/x-7z-compressed': '.7z',
        'application/octet-stream': '.bin', 'video/mp4': '.mp4',
        'audio/mpeg': '.mp3', 'image/jpeg': '.jpg', 'image/png': '.png',
    }
    ext = ext_map.get(ct, '.bin')
    return f'download_{uuid_mod.uuid4().hex[:8]}{ext}'

def _generic_download_worker(vid_id, url, title, extra_cookies=None):
    import requests as req
    import time
    try:
        start_time = time.time()
        with downloads_lock:
            downloads[vid_id]['status'] = 'Connecting...'

        if isinstance(extra_cookies, dict):
            cookie_str = extra_cookies.get('cookies', '')
            ua_str = extra_cookies.get('user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')
        else:
            cookie_str = extra_cookies or ''
            ua_str = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'

        headers = {
            'User-Agent': ua_str,
            'Accept': '*/*'
        }
        if cookie_str:
            headers['Cookie'] = cookie_str

        filename = _guess_filename(url, {})
        total = 0
        try:
            head = req.head(url, headers=headers, allow_redirects=True, timeout=10)
            filename = _guess_filename(url, head.headers)
            total = int(head.headers.get('Content-Length', 0))
        except Exception:
            pass

        filepath = get_unique_filepath(DOWNLOAD_FOLDER, os.path.splitext(filename)[0], filename.rsplit('.', 1)[-1] if '.' in filename else 'bin')

        with req.get(url, headers=headers, stream=True, timeout=30) as r:
            r.raise_for_status()
            total = int(r.headers.get('Content-Length', 0))
            downloaded = 0
            with open(filepath, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    with cancel_flags_lock:
                        if cancel_flags.get(vid_id):
                            raise Exception('Cancelled')
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        elapsed = time.time() - start_time
                        speed_bps = downloaded / elapsed if elapsed > 0 else 0
                        speed_str = f'{speed_bps/1024/1024:.1f} MB/s' if speed_bps > 1024*1024 else f'{speed_bps/1024:.0f} KB/s'
                        mb_done = downloaded / (1024 * 1024)
                        with downloads_lock:
                            downloads[vid_id]['status'] = 'Downloading...'
                            downloads[vid_id]['percent'] = (downloaded / total * 100) if total else 0
                            downloads[vid_id]['speed'] = speed_str
                            if total and speed_bps > 0:
                                remaining = (total - downloaded) / speed_bps
                                if remaining < 60:
                                    eta_str = f'{int(remaining)}s'
                                else:
                                    eta_str = f'{int(remaining/60)}m {int(remaining%60)}s'
                            else:
                                eta_str = f'{mb_done:.1f} MB'
                            downloads[vid_id]['eta'] = eta_str

        with downloads_lock:
            downloads[vid_id]['status'] = 'Done'
            downloads[vid_id]['percent'] = 100.0
            downloads[vid_id]['done'] = True
            downloads[vid_id]['filepath'] = filepath

        with history_lock:
            history.append({
                'title': title,
                'filepath': filepath,
                'thumbnail': '',
                'format': 'file',
                'quality': '',
            })

    except Exception as e:
        err_msg = str(e)
        is_cancelled = 'Cancelled' in err_msg or cancel_flags.get(vid_id, False)
        with downloads_lock:
            if is_cancelled:
                downloads[vid_id]['status'] = 'Cancelled'
                downloads[vid_id]['cancelled'] = True
                downloads[vid_id]['error'] = False
            else:
                downloads[vid_id]['status'] = f'Error: {err_msg[:80]}'
                downloads[vid_id]['error'] = True

def _run_single(vid_id, entry, format_type, quality, subtitle_mode, subtitle_langs, clip_start=None, clip_end=None):
    title = entry.get('title', 'download')

    if entry.get('type') == 'generic':
        extra_cookies = pending_downloads.get(entry['url'], None)
        _generic_download_worker(vid_id, entry['url'], title, extra_cookies)
        return
    with cancel_flags_lock:
        cancel_flags[vid_id] = False

    with downloads_lock:
        downloads[vid_id]['status'] = 'Starting...'

    ext = 'mp3' if format_type == 'audio' else 'mp4'
    title = entry.get('title', 'download')

    clip_suffix = ''
    if clip_start is not None or clip_end is not None:
        s = int(clip_start or 0)
        e = int(clip_end or 0)
        clip_suffix = f' [{s}s-{e}s]'

    temp_prefix = f'ytdl_tmp_{vid_id}_'
    out_template = os.path.join(DOWNLOAD_FOLDER, f'{temp_prefix}%(title)s.%(ext)s')

    ydl_opts = {
        'outtmpl': out_template,
        'noplaylist': True,
        'quiet': True,
        'progress_hooks': [make_hook(vid_id)],
        'concurrent_fragment_downloads': 10,
        'ffmpeg_location': app_path,
        'writethumbnail': True,
    }

    if speed_limit > 0:
        ydl_opts['ratelimit'] = speed_limit * 1024

    if clip_start is not None or clip_end is not None:
        start_sec = float(clip_start or 0)
        end_sec = float(clip_end) if clip_end else None
        ydl_opts['download_ranges'] = yt_dlp.utils.download_range_func(None, [(start_sec, end_sec)])
        ydl_opts['force_keyframes_at_cuts'] = True

    if format_type == 'audio':
        ydl_opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [
                {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': quality},
                {'key': 'EmbedThumbnail'},
            ]
        })
    else:
        ydl_opts.update({
            'format': f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/best',
            'merge_output_format': 'mp4',
            'postprocessor_args': {'ffmpeg': ['-c:a', 'aac', '-b:a', '192k']},
            'postprocessors': [{'key': 'EmbedThumbnail'}],
        })

    clean_langs = [l.replace(' (auto)', '') for l in subtitle_langs] if subtitle_langs else ['en']

    if subtitle_mode == 'download' and format_type == 'video':
        ydl_opts.update({'writesubtitles': True, 'writeautomaticsub': True, 'subtitleslangs': clean_langs})
    elif subtitle_mode == 'hardcode' and format_type == 'video':
        ydl_opts.update({'writesubtitles': True, 'writeautomaticsub': True, 'subtitleslangs': clean_langs})
        ydl_opts['postprocessors'] = ydl_opts.get('postprocessors', []) + [{'key': 'FFmpegEmbedSubtitle'}]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([entry['url']])

        filepath = None
        for f in os.listdir(DOWNLOAD_FOLDER):
            if f.startswith(temp_prefix) and f.endswith('.' + ext):
                old_path = os.path.join(DOWNLOAD_FOLDER, f)
                new_path = get_unique_filepath(DOWNLOAD_FOLDER, title + clip_suffix, ext)
                os.rename(old_path, new_path)
                filepath = new_path
                break

        with downloads_lock:
            downloads[vid_id]['status'] = 'Done'
            downloads[vid_id]['percent'] = 100.0
            downloads[vid_id]['done'] = True
            downloads[vid_id]['filepath'] = filepath

        with history_lock:
            history.append({
                'title': title + clip_suffix,
                'filepath': filepath,
                'thumbnail': entry.get('thumbnail', ''),
                'format': format_type,
                'quality': quality,
            })

    except Exception as e:
        err_msg = str(e)
        is_cancelled = 'Cancelled' in err_msg or cancel_flags.get(vid_id, False)

        for f in os.listdir(DOWNLOAD_FOLDER):
            if f.startswith(temp_prefix):
                try:
                    os.remove(os.path.join(DOWNLOAD_FOLDER, f))
                except:
                    pass

        with downloads_lock:
            if is_cancelled:
                downloads[vid_id]['status'] = 'Cancelled'
                downloads[vid_id]['cancelled'] = True
                downloads[vid_id]['error'] = False
            else:
                with downloads_lock:
                    downloads[vid_id]['status'] = 'yt-dlp failed, trying direct...'
                    downloads[vid_id]['percent'] = 0.0
                    downloads[vid_id]['error'] = False
                extra_cookies = pending_downloads.get(entry['url'], None)
                _generic_download_worker(vid_id, entry['url'], title, extra_cookies)

@app.route('/download', methods=['POST'])
def download():
    global max_concurrent
    items_json = request.form.get('items')
    format_type = request.form.get('format_type')
    quality = request.form.get('quality')
    subtitle_mode = request.form.get('subtitle_mode', 'none')

    if not items_json:
        return jsonify({"status": "error", "message": "No items provided."})

    try:
        all_entries = json.loads(items_json)
    except:
        return jsonify({"status": "error", "message": "Invalid items."})

    with downloads_lock:
        downloads.clear()
        for i, entry in enumerate(all_entries):
            downloads[str(i)] = {
                'title': entry['title'],
                'url': entry['url'],
                'type': entry.get('type', 'video'),
                'status': 'Waiting...',
                'percent': 0.0,
                'speed': '-',
                'eta': '-',
                'done': False,
                'error': False,
                'cancelled': False,
                'filepath': None,
                'thumbnail': entry.get('thumbnail', ''),
                'fmt': entry.get('fmt', format_type),
                'qual': entry.get('qual', quality),
                'sub': entry.get('sub', subtitle_mode),
                'sub_langs': entry.get('sub_langs', ['en']),
                'clip_start': entry.get('clip_start'),
                'clip_end': entry.get('clip_end'),
            }

    with cancel_flags_lock:
        cancel_flags.clear()

    semaphore = threading.Semaphore(max_concurrent)

    def run_one(i, entry):
        vid_id = str(i)
        item_fmt = entry.get('fmt', format_type)
        item_qual = entry.get('qual', quality)
        item_sub = entry.get('sub', subtitle_mode)
        item_sub_langs = entry.get('sub_langs', ['en'])
        item_clip_start = entry.get('clip_start')
        item_clip_end = entry.get('clip_end')
        with semaphore:
            if cancel_flags.get(vid_id):
                with downloads_lock:
                    downloads[vid_id]['status'] = 'Cancelled'
                    downloads[vid_id]['cancelled'] = True
                return
            with downloads_lock:
                entry['type'] = downloads[vid_id].get('type', entry.get('type', 'video'))
            _run_single(vid_id, entry, item_fmt, item_qual, item_sub, item_sub_langs, item_clip_start, item_clip_end)

    def run_downloads():
        threads = []
        for i, entry in enumerate(all_entries):
            t = threading.Thread(target=run_one, args=(i, entry))
            t.daemon = True
            threads.append(t)
            t.start()
        for t in threads:
            t.join()

    t = threading.Thread(target=run_downloads)
    t.daemon = True
    t.start()

    return jsonify({"status": "success", "count": len(all_entries)})

@app.route('/open_file', methods=['POST'])
def open_file():
    filepath = request.form.get('filepath')
    if filepath and os.path.exists(filepath):
        os.startfile(filepath)
        return jsonify({"status": "ok"})
    return jsonify({"status": "error", "message": "File not found"})

@app.route('/show_in_folder', methods=['POST'])
def show_in_folder():
    filepath = request.form.get('filepath')
    if filepath and os.path.exists(filepath):
        subprocess.Popen(f'explorer /select,"{filepath}"')
        return jsonify({"status": "ok"})
    return jsonify({"status": "error", "message": "File not found"})

@app.route('/preview_file')
def preview_file():
    filepath = request.args.get('filepath')
    if filepath and os.path.exists(filepath):
        return send_file(filepath)
    return "File not found", 404

@app.route('/kick_analyze', methods=['POST'])
def kick_analyze():
    url = request.form.get('url', '').strip()
    if not url:
        return jsonify({"status": "error", "message": "No URL provided."})

    try:
        vod_match = re.search(r'/videos/([a-f0-9\-]{36})', url)
        vod_id_match = re.search(r'/videos/(\d+)', url)
        clip_match = re.search(r'/clips/([A-Za-z0-9_\-]+)', url) or re.search(r'/clip/([A-Za-z0-9_\-]+)', url)

        if vod_match or vod_id_match:
            if vod_match:
                uuid = vod_match.group(1)
                api_url = f'https://kick.com/api/v1/video/{uuid}'
            else:
                vid_id = vod_id_match.group(1)
                channel_slug = re.search(r'kick\.com/([^/]+)/videos', url)
                if channel_slug:
                    slug = channel_slug.group(1)
                    api_url = f'https://kick.com/api/v2/channels/{slug}/videos?video_id={vid_id}'
                else:
                    return jsonify({"status": "error", "message": "Could not parse channel."})

            resp = cffi_requests.get(api_url, impersonate="chrome", timeout=15)
            data = resp.json()

            if isinstance(data, list):
                data = data[0] if data else {}

            playback_url = data.get('source') or data.get('playback_url') or data.get('stream', {}).get('url')
            title = data.get('session_title') or data.get('title') or 'Kick VOD'
            thumbnail = data.get('thumbnail') or (data.get('channel', {}) or {}).get('banner_image', {}).get('url', '')
            duration = data.get('duration', 0)
            duration_str = f"{int(duration)//3600}h {(int(duration)%3600)//60}m" if duration else ''

            qualities = []
            if playback_url:
                try:
                    m3u8_resp = cffi_requests.get(playback_url, impersonate="chrome", timeout=15)
                    m3u8_content = m3u8_resp.text
                    base_url = playback_url.rsplit('/', 1)[0]
                    lines = m3u8_content.splitlines()
                    for i, line in enumerate(lines):
                        if line.startswith('#EXT-X-STREAM-INF'):
                            res_match = re.search(r'RESOLUTION=(\d+)x(\d+)', line)
                            if res_match:
                                height = int(res_match.group(2))
                                stream_url = lines[i+1] if i+1 < len(lines) else ''
                                if stream_url and not stream_url.startswith('http'):
                                    stream_url = base_url + '/' + stream_url
                                qualities.append({'height': height, 'url': stream_url})
                    qualities.sort(key=lambda x: x['height'], reverse=True)
                except:
                    pass

            return jsonify({
                "status": "success",
                "type": "vod",
                "title": title,
                "thumbnail": thumbnail,
                "duration": duration_str,
                "playback_url": playback_url,
                "qualities": qualities,
            })

        elif clip_match:
            clip_id = clip_match.group(1)
            api_url = f'https://kick.com/api/v2/clips/{clip_id}'
            
            resp = cffi_requests.get(api_url, impersonate="chrome", timeout=15)
            data = resp.json()

            clip_data = data.get('clip', data)
            playback_url = clip_data.get('clip_url') or clip_data.get('playback_url')
            title = clip_data.get('title') or 'Kick Clip'
            thumbnail = clip_data.get('thumbnail_url') or ''
            duration = clip_data.get('duration', 0)
            duration_str = f"{int(duration)}s" if duration else ''

            qualities = []
            if playback_url:
                try:
                    m3u8_resp = cffi_requests.get(playback_url, impersonate="chrome", timeout=15)
                    m3u8_content = m3u8_resp.text
                    base_url = playback_url.rsplit('/', 1)[0]
                    lines = m3u8_content.splitlines()
                    for i, line in enumerate(lines):
                        if line.startswith('#EXT-X-STREAM-INF'):
                            res_match = re.search(r'RESOLUTION=(\d+)x(\d+)', line)
                            if res_match:
                                height = int(res_match.group(2))
                                stream_url = lines[i+1] if i+1 < len(lines) else ''
                                if stream_url and not stream_url.startswith('http'):
                                    stream_url = base_url + '/' + stream_url
                                qualities.append({'height': height, 'url': stream_url})
                    qualities.sort(key=lambda x: x['height'], reverse=True)
                except:
                    pass

            return jsonify({
                "status": "success",
                "type": "clip",
                "title": title,
                "thumbnail": thumbnail,
                "duration": duration_str,
                "playback_url": playback_url,
                "qualities": qualities,
            })

        else:
            return jsonify({"status": "error", "message": "Invalid Kick URL. Paste a VOD or clip link."})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})
        
@app.route('/receive_url', methods=['POST'])
def receive_url():
    data = request.get_json()
    url = data.get('url', '').strip()
    cookies = data.get('cookies', '')
    ua = data.get('user_agent', '')
    if not url:
        return jsonify({"status": "error"})
    
    pending_downloads[url] = {'cookies': cookies, 'user_agent': ua}

    def inject():
        import time
        # Pencerenin var olmasını bekle
        while not window_ref:
            time.sleep(0.2)
            
        time.sleep(1.0) # Arayüzün çizilmesi için kısa bir pay
        
        safe_url = url.replace('\\', '\\\\').replace('"', '\\"').replace("'", "\\'")
        
        # DOM manipülasyonunu tarayıcı motoruna bırak (PyWebView'i yormaz)
        js_code = f'''
            setTimeout(function() {{
                try {{
                    if ("{safe_url}".includes("kick.com")) {{
                        document.getElementById("kick-url").value = "{safe_url}";
                        document.getElementById("tab-btn-kick").click();
                        document.getElementById("kick-analyze-btn").click();
                    }} else {{
                        document.getElementById("urls").value = "{safe_url}";
                        document.getElementById("tab-btn-download").click();
                        document.getElementById("analyze-btn").click();
                    }}
                }} catch(e) {{ console.error("Inject Error:", e); }}
            }}, 500);
        '''
        try:
            window_ref.evaluate_js(js_code)
        except Exception as e:
            print("Injection failed:", e)

    t = threading.Thread(target=inject)
    t.daemon = True
    t.start()
    return jsonify({"status": "ok"})
    
@app.route('/kick_download', methods=['POST'])
def kick_download():
    playback_url = request.form.get('playback_url')
    title = request.form.get('title', 'kick_download')
    fmt = request.form.get('fmt', 'video')
    quality = request.form.get('quality', 'Best')
    thumbnail = request.form.get('thumbnail', '')

    if not playback_url:
        return jsonify({"status": "error", "message": "No playback URL."})

    vid_id = 'kick_0'
    with downloads_lock:
        downloads.clear()
        downloads[vid_id] = {
            'title': title,
            'url': playback_url,
            'status': 'Waiting...',
            'percent': 0.0,
            'speed': '-',
            'eta': '-',
            'done': False,
            'error': False,
            'cancelled': False,
            'filepath': None,
            'thumbnail': thumbnail,
            'fmt': fmt,
            'qual': quality,
            'sub': 'none',
            'sub_langs': [],
        }

    with cancel_flags_lock:
        cancel_flags.clear()

    ext = 'mp3' if fmt == 'audio' else 'mp4'
    temp_prefix = 'ytdl_tmp_kick_0_'

    def run():
        with downloads_lock:
            downloads[vid_id]['status'] = 'Starting...'
        with cancel_flags_lock:
            cancel_flags[vid_id] = False

        try:
            if fmt == 'audio':
                ydl_opts = {
                    'outtmpl': os.path.join(DOWNLOAD_FOLDER, f'{temp_prefix}%(title)s.%(ext)s'),
                    'quiet': True,
                    'progress_hooks': [make_hook(vid_id)],
                    'ffmpeg_location': app_path,
                    'format': 'bestaudio/best',
                    'postprocessors': [
                        {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'},
                    ],
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([playback_url])
                filepath = None
                for f in os.listdir(DOWNLOAD_FOLDER):
                    if f.startswith(temp_prefix) and f.endswith('.mp3'):
                        old = os.path.join(DOWNLOAD_FOLDER, f)
                        new = get_unique_filepath(DOWNLOAD_FOLDER, title, 'mp3')
                        os.rename(old, new)
                        filepath = new
                        break
            else:
                filepath = get_unique_filepath(DOWNLOAD_FOLDER, title, 'mp4')
                cmd = [
                    os.path.join(app_path, 'ffmpeg'),
                    '-i', playback_url,
                    '-c', 'copy',
                    '-y',
                    filepath
                ]
                kwargs = {'capture_output': True}
                if sys.platform == 'win32':
                    kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
                result = subprocess.run(cmd, **kwargs)
                if result.returncode != 0:
                    raise Exception('ffmpeg failed')

            with downloads_lock:
                downloads[vid_id]['status'] = 'Done'
                downloads[vid_id]['percent'] = 100.0
                downloads[vid_id]['done'] = True
                downloads[vid_id]['filepath'] = filepath

            with history_lock:
                history.append({
                    'title': title,
                    'filepath': filepath,
                    'thumbnail': thumbnail,
                    'format': fmt,
                    'quality': '192' if fmt == 'audio' else quality,
                })

        except Exception as e:
            err_msg = str(e)
            is_cancelled = 'Cancelled' in err_msg or cancel_flags.get(vid_id, False)
            with downloads_lock:
                if is_cancelled:
                    downloads[vid_id]['status'] = 'Cancelled'
                    downloads[vid_id]['cancelled'] = True
                    downloads[vid_id]['error'] = False
                else:
                    downloads[vid_id]['status'] = f'Error: {err_msg[:80]}'
                    downloads[vid_id]['error'] = True

    t = threading.Thread(target=run)
    t.daemon = True
    t.start()

    return jsonify({"status": "success"})


def start_server():
    app.run(port=5000, use_reloader=False)

if __name__ == '__main__':
    cfg = load_config()
    w = cfg.get('window_width', 560)
    h = cfg.get('window_height', 900)

    t = threading.Thread(target=start_server)
    t.daemon = True
    t.start()

    window_ref = webview.create_window(
        'Grabber',
        'http://localhost:5000',
        width=w, height=h,
        resizable=True
    )
    webview.start()