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

if getattr(sys, 'frozen', False):
    template_folder = os.path.join(sys._MEIPASS, 'templates')
    app = Flask(__name__, template_folder=template_folder)
    app_path = os.path.dirname(sys.executable)
else:
    app = Flask(__name__)
    app_path = os.path.dirname(os.path.abspath(__file__))

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

    results = []
    for url in urls:
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
            results.append({'type': 'error', 'url': url, 'message': str(e)})

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
            kwargs = {
                'capture_output': True,
                'text': True,
            }
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

def _run_single(vid_id, entry, format_type, quality, subtitle_mode, subtitle_langs, clip_start=None, clip_end=None):
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
                downloads[vid_id]['status'] = f'Error: {err_msg[:80]}'
                downloads[vid_id]['error'] = True

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
        'YT Downloader',
        'http://localhost:5000',
        width=w, height=h,
        resizable=True
    )
    webview.start()