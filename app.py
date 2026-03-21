from flask import Flask, render_template, request, jsonify, send_file
import yt_dlp
import os
import re
import sys
import threading
import webview
import subprocess
import json

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

app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

@app.after_request
def no_cache(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    return response

downloads = {}
downloads_lock = threading.Lock()

def remove_ansi_colors(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def make_hook(vid_id):
    def progress_hook(d):
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
                for entry in info['entries']:
                    thumb = ''
                    if entry.get('thumbnails'):
                        thumb = entry['thumbnails'][-1].get('url', '')
                    elif entry.get('thumbnail'):
                        thumb = entry['thumbnail']
                    results.append({
                        'type': 'video',
                        'title': entry.get('title', 'Unknown'),
                        'thumbnail': thumb,
                        'duration': entry.get('duration_string', ''),
                        'url': entry.get('url') or entry.get('webpage_url') or f"https://www.youtube.com/watch?v={entry['id']}",
                        'heights': [1080, 720, 480]
                    })
            else:
                formats = info.get('formats', [])
                heights = sorted(set(
                    f['height'] for f in formats
                    if f.get('height') and f.get('vcodec') != 'none'
                ), reverse=True)

                results.append({
                    'type': 'video',
                    'title': info.get('title', 'Unknown'),
                    'thumbnail': info.get('thumbnail', ''),
                    'duration': info.get('duration_string', ''),
                    'url': url,
                    'heights': heights if heights else [1080, 720, 480]
                })
        except Exception as e:
            results.append({'type': 'error', 'url': url, 'message': str(e)})

    return jsonify({"status": "success", "results": results})

@app.route('/progress')
def progress():
    with downloads_lock:
        return jsonify(downloads)

@app.route('/download', methods=['POST'])
def download():
    items_json = request.form.get('items')
    format_type = request.form.get('format_type')
    quality = request.form.get('quality')

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
                'filepath': None,
            }

    def run_downloads():
        for i, entry in enumerate(all_entries):
            vid_id = str(i)
            with downloads_lock:
                downloads[vid_id]['status'] = 'Starting...'

            ext = 'mp3' if format_type == 'audio' else 'mp4'
            out_template = os.path.join(DOWNLOAD_FOLDER, f'ytdl_{vid_id}_%(title)s.%(ext)s')

            ydl_opts = {
                'outtmpl': out_template,
                'noplaylist': True,
                'quiet': True,
                'progress_hooks': [make_hook(vid_id)],
                'concurrent_fragment_downloads': 10,
                'ffmpeg_location': app_path,
            }

            if format_type == 'audio':
                ydl_opts.update({
                    'format': 'bestaudio/best',
                    'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': quality}]
                })
            else:
                ydl_opts.update({
                    'format': f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/best',
                    'merge_output_format': 'mp4',
                    'postprocessor_args': {'ffmpeg': ['-c:a', 'aac', '-b:a', '192k']}
                })

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([entry['url']])

                filepath = None
                prefix = f'ytdl_{vid_id}_'
                for f in os.listdir(DOWNLOAD_FOLDER):
                    if f.startswith(prefix) and f.endswith('.' + ext):
                        filepath = os.path.join(DOWNLOAD_FOLDER, f)
                        break

                with downloads_lock:
                    downloads[vid_id]['status'] = 'Done'
                    downloads[vid_id]['percent'] = 100.0
                    downloads[vid_id]['done'] = True
                    downloads[vid_id]['filepath'] = filepath

            except Exception as e:
                with downloads_lock:
                    downloads[vid_id]['status'] = f'Error: {str(e)}'
                    downloads[vid_id]['error'] = True

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
    t = threading.Thread(target=start_server)
    t.daemon = True
    t.start()
    webview.create_window('YT Downloader', 'http://localhost:5000', width=520, height=850, resizable=True)
    webview.start()