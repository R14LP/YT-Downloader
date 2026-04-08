import sys
import struct
import json
import time
import os
import urllib.request
import subprocess

def read_message():
    try:
        raw_length = sys.stdin.buffer.read(4)
        if not raw_length:
            return None
        length = struct.unpack('=I', raw_length)[0]
        message = sys.stdin.buffer.read(length).decode('utf-8')
        return json.loads(message)
    except:
        return None

def send_message(msg):
    try:
        encoded = json.dumps(msg).encode('utf-8')
        sys.stdout.buffer.write(struct.pack('=I', len(encoded)))
        sys.stdout.buffer.write(encoded)
        sys.stdout.buffer.flush()
    except:
        pass

def is_app_running():
    try:
        urllib.request.urlopen('http://localhost:5000/progress', timeout=0.5)
        return True
    except:
        return False

def launch_app():
    try:
        exe = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), 'Grabber.exe')
        if os.path.exists(exe):
            subprocess.Popen(['explorer.exe', exe], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        pass

def send_url_to_app(url, cookies='', ua=''):
    try:
        data = json.dumps({'url': url, 'cookies': cookies, 'user_agent': ua}).encode('utf-8')
        r = urllib.request.Request(
            'http://localhost:5000/receive_url', 
            data=data, 
            headers={'Content-Type': 'application/json'}
        )
        urllib.request.urlopen(r, timeout=3)
    except:
        pass

try:
    msg = read_message()
    if msg:
        url = msg.get('url', '')
        cookies = msg.get('cookies', '')
        ua = msg.get('user_agent', '')

        if not is_app_running():
            launch_app()
            for _ in range(50):
                time.sleep(0.2)
                if is_app_running():
                    break
            time.sleep(1.0)
            
        send_url_to_app(url, cookies, ua)
        send_message({'status': 'success'})

except:
    pass