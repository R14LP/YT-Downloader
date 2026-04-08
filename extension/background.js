const browserAPI = (typeof browser !== 'undefined') ? browser : chrome;

browserAPI.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'send_to_app') {
        getCookiesForUrl(request.url, (cookieString) => {
            sendToGrabberApp(request.url, cookieString);
        });
    }
});

function getCookiesForUrl(url, callback) {
    if (!browserAPI.cookies) {
        callback('');
        return;
    }
    try {
        let domain = new URL(url).hostname;
        let parts = domain.split('.');
        let rootDomain = parts.length > 2 ? parts.slice(-2).join('.') : domain;
        
        browserAPI.cookies.getAll({ domain: rootDomain }, (cookies) => {
            const cookieString = (cookies || []).map(c => `${c.name}=${c.value}`).join('; ');
            callback(cookieString);
        });
    } catch(e) {
        callback('');
    }
}

function sendToGrabberApp(url, cookies) {
    const port = browserAPI.runtime.connectNative("grabber_host");
    port.postMessage({ url: url, cookies: cookies, user_agent: navigator.userAgent });
}