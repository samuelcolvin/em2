#!/usr/bin/env python3.6
"""
Build a production js bundle, calls "yarn build", but also does some other stuff.

Designed primarily for netlify.
"""
import base64
import hashlib
import os
import re
import subprocess
from pathlib import Path

THIS_DIR = Path(__file__).parent


CSP = {
    'default-src': [
        "'self'",
    ],
    'script-src': [
        "'self'",
        'www.google-analytics.com',
        'maps.googleapis.com',
        'storage.googleapis.com',  # workbox, TODO remove and change CDN
        '*.google.com',
        '*.gstatic.com',
    ],
    'font-src': [
        "'self'",
        'data:',
        'fonts.gstatic.com',
    ],
    'style-src': [
        "'self'",
        "'unsafe-inline'",
        '*.googleapis.com',
    ],
    'frame-src': [
        "'self'",
        'blob:',
        '*.google.com',
    ],
    'img-src': [
        "'self'",
        'blob:',
        'data:',
        'www.google-analytics.com',
        '*.googleapis.com',
        '*.gstatic.com',
        '*.google.com',
        '*.google.co.uk',
        '*.google.de',
        '*.google.pt',
    ],
    'media-src': [
        "'self'",
    ],
    'connect-src': [
        "'self'",
        '*.google-analytics.com',
        'https://sentry.io',
    ],
}


toml_template = """
[[headers]]
  for = "/*"
  [headers.values]
    Content-Security-Policy = "{}"
"""


def before():
    path = THIS_DIR / 'src' / 'index.js'
    new_content = re.sub(r'^// *{{.+?^// *}}', '', path.read_text(), flags=re.S | re.M)
    new_content = re.sub(r'\n+$', '\n', new_content)
    path.write_text(new_content)


def after():
    csp = dict(CSP)

    content = (THIS_DIR / 'build' / 'index.html').read_text()
    m = re.search(r'<script>(.+?)</script>', content, flags=re.S)
    if m:
        js = m.group(1)
        s = f"'sha256-{base64.b64encode(hashlib.sha256(js.encode()).digest()).decode()}'"
        csp['script-src'].append(s)
    else:
        print('WARNING: runtime script now found in index.html')

    raven_dsn = os.getenv('RAVEN_DSN', None)
    if raven_dsn:
        m = re.search(r'^https://(.+)@sentry\.io/(.+)', raven_dsn)
        if m:
            key, app = m.groups()
            csp['report-uri'] = [f'https://sentry.io/api/{app}/security/?sentry_key={key}']
        else:
            print('WARNING: app and key not found in RAVEN_DSN', raven_dsn)
    extra = toml_template.format(' '.join(f'{k} {" ".join(v)};' for k, v in csp.items()))
    path = THIS_DIR / '..' / 'netlify.toml'
    with path.open('a') as f:
        f.write(extra)


if __name__ == '__main__':
    before()
    subprocess.run(['yarn', 'build'], cwd=str(THIS_DIR), check=True)
    after()
