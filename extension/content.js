let SHORTCUT = 'Alt+D';
let isVisible = false;

chrome.storage.sync.get(['shortcut'], r => {
  if (r.shortcut) SHORTCUT = r.shortcut;
});

chrome.storage.onChanged.addListener((changes) => {
  if (changes.shortcut) SHORTCUT = changes.shortcut.newValue;
});

document.addEventListener('submit', async (e) => {
  const form = e.target;
  if (!form || form.tagName !== 'FORM') return;

  const action = form.action || '';
  if (!action.includes('drive.usercontent.google.com') && !action.includes('docs.google.com')) return;

  e.preventDefault();
  e.stopPropagation();

  const params = new URLSearchParams();
  for (const input of form.querySelectorAll('input')) {
    if (input.name) params.append(input.name, input.value);
  }
  const downloadUrl = `${action}?${params.toString()}`;

  const choice = await showChoiceDialog(downloadUrl);
  if (choice === 'app') {
    chrome.runtime.sendMessage({ action: 'send_to_app', url: downloadUrl });
  } else if (choice === 'browser') {
    form.submit();
  }
}, true);

document.addEventListener('click', async (e) => {
  const a = e.target.closest('a');
  if (!a || !a.href) return;

  const url = a.href;
  const isDownloadable = isDownloadLink(url);

  if (!isDownloadable) return;

  e.preventDefault();
  e.stopPropagation();

  const choice = await showChoiceDialog(url);
  if (choice === 'app') {
    chrome.runtime.sendMessage({ action: 'send_to_app', url });
  } else if (choice === 'browser') {
    window.location.href = url;
  }
}, true);

document.addEventListener('keydown', async (e) => {
  const combo = [
    e.altKey && 'Alt',
    e.ctrlKey && 'Ctrl',
    e.shiftKey && 'Shift',
    e.key.length === 1 ? e.key.toUpperCase() : e.key
  ].filter(Boolean).join('+');

  if (combo === SHORTCUT) {
    e.preventDefault();
    isVisible = !isVisible;
    document.querySelectorAll('.grabber-dl-btn').forEach(btn => {
      btn.style.display = isVisible ? 'block' : 'none';
    });
  }
});

function addDownloadButton(videoEl) {
  if (videoEl.parentElement.querySelector('.grabber-dl-btn')) return;

  const btn = document.createElement('div');
  btn.className = 'grabber-dl-btn';
  btn.innerText = '⬇ GRAB';
  
  Object.assign(btn.style, {
    position: 'absolute',
    top: '10px',
    right: '10px',
    zIndex: '999999',
    backgroundColor: '#ff003c',
    color: 'white',
    padding: '6px 12px',
    borderRadius: '6px',
    cursor: 'pointer',
    fontFamily: 'monospace',
    fontSize: '12px',
    fontWeight: 'bold',
    boxShadow: '0 4px 15px rgba(255,0,60,0.4)',
    border: '1px solid #b3002a',
    transition: 'all 0.2s',
    display: isVisible ? 'block' : 'none'
  });

  btn.onmouseover = () => btn.style.transform = 'scale(1.05)';
  btn.onmouseout = () => btn.style.transform = 'scale(1)';

  btn.onclick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    chrome.runtime.sendMessage({ action: 'send_to_app', url: window.location.href });
    
    btn.innerText = 'GÖNDERİLDİ';
    btn.style.backgroundColor = '#00ff9d';
    btn.style.color = '#000';
    setTimeout(() => {
      btn.innerText = '⬇ GRAB';
      btn.style.backgroundColor = '#ff003c';
      btn.style.color = 'white';
    }, 2000);
  };

  if (window.getComputedStyle(videoEl.parentElement).position === 'static') {
    videoEl.parentElement.style.position = 'relative';
  }
  videoEl.parentElement.appendChild(btn);
}

const observer = new MutationObserver((mutations) => {
  mutations.forEach(m => {
    m.addedNodes.forEach(node => {
      if (node.nodeName === 'VIDEO') addDownloadButton(node);
      else if (node.querySelectorAll) {
        node.querySelectorAll('video').forEach(addDownloadButton);
      }
    });
  });
});

observer.observe(document.body, { childList: true, subtree: true });

document.querySelectorAll('video').forEach(addDownloadButton);

function isDownloadLink(url) {
  const downloadExts = [
    '.zip', '.rar', '.7z', '.tar', '.gz', '.exe', '.msi', '.dmg',
    '.pdf', '.iso', '.bin', '.apk', '.mp4', '.mp3', '.mkv', '.avi',
    '.mov', '.flv', '.wmv', '.torrent', '.docx', '.xlsx', '.csv'
  ];
  try {
    const parsed = new URL(url);
    const path = parsed.pathname.toLowerCase();
    const params = parsed.search.toLowerCase();
    if (downloadExts.some(ext => path.endsWith(ext))) return true;
    if (parsed.hostname.includes('google.com') && params.includes('export=download')) return true;
    if (parsed.hostname.includes('drive.usercontent.google.com')) return true;
    if (params.includes('download=') || params.includes('export=download')) return true;
    if (params.includes('response-content-disposition') || params.includes('rscd=attachment')) return true;
    return false;
  } catch {
    return false;
  }
}

function showChoiceDialog(url) {
  return new Promise(resolve => {
    document.getElementById('ytdl-dialog')?.remove();

    const filename = decodeURIComponent(url.split('/').pop().split('?')[0]) || 'file';

    const dialog = document.createElement('div');
    dialog.id = 'ytdl-dialog';
    dialog.innerHTML = `
      <div id="ytdl-overlay"></div>
      <div id="ytdl-box">
        <button id="ytdl-btn-close">✕</button>
        <div id="ytdl-title">⬇ Download with...</div>
        <div id="ytdl-filename">${filename}</div>
        <div id="ytdl-buttons">
          <button id="ytdl-btn-app">Grabber</button>
          <button id="ytdl-btn-browser">Browser</button>
        </div>
      </div>
    `;

    const style = document.createElement('style');
    style.textContent = `
      #ytdl-overlay {
        position: fixed; inset: 0;
        background: rgba(0,0,0,0.6);
        z-index: 2147483646;
      }
      #ytdl-box {
        position: fixed;
        top: 50%; left: 50%;
        transform: translate(-50%, -50%);
        background: #0c0f14;
        border: 1px solid #252e40;
        border-radius: 10px;
        padding: 20px 24px;
        z-index: 2147483647;
        font-family: 'Space Mono', monospace, sans-serif;
        min-width: 280px;
        box-shadow: 0 8px 32px rgba(0,0,0,0.6);
        position: fixed;
      }
      #ytdl-btn-close {
        position: absolute;
        top: 10px; right: 10px;
        background: none;
        border: none;
        color: #4a5568;
        cursor: pointer;
        font-size: 14px;
        padding: 0;
      }
      #ytdl-btn-close:hover { color: #e8eaf0; }
      #ytdl-title {
        color: #e8eaf0;
        font-size: 13px;
        font-weight: 700;
        margin-bottom: 8px;
        letter-spacing: 1px;
      }
      #ytdl-filename {
        color: #4a5568;
        font-size: 10px;
        margin-bottom: 16px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 260px;
      }
      #ytdl-buttons {
        display: flex;
        gap: 8px;
      }
      #ytdl-btn-app {
        flex: 1;
        background: #d42b2b;
        color: white;
        border: none;
        border-radius: 6px;
        padding: 8px 12px;
        font-family: inherit;
        font-size: 11px;
        cursor: pointer;
        letter-spacing: 0.5px;
      }
      #ytdl-btn-app:hover { background: #b82424; }
      #ytdl-btn-browser {
        flex: 1;
        background: #111620;
        color: #8892a4;
        border: 1px solid #252e40;
        border-radius: 6px;
        padding: 8px 12px;
        font-family: inherit;
        font-size: 11px;
        cursor: pointer;
      }
      #ytdl-btn-browser:hover { color: #e8eaf0; border-color: #4a5568; }
    `;

    document.head.appendChild(style);
    document.body.appendChild(dialog);

    dialog.querySelector('#ytdl-btn-app').onclick = () => {
      dialog.remove(); style.remove(); resolve('app');
    };
    dialog.querySelector('#ytdl-btn-browser').onclick = () => {
      dialog.remove(); style.remove(); resolve('browser');
    };
    dialog.querySelector('#ytdl-btn-close').onclick = () => {
      dialog.remove(); style.remove(); resolve('cancel');
    };
    dialog.querySelector('#ytdl-overlay').onclick = () => {
      dialog.remove(); style.remove(); resolve('cancel');
    };
  });
}