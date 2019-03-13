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
import urllib.request
from pathlib import Path

THIS_DIR = Path(__file__).parent

main_domain = os.getenv('REACT_APP_DOMAIN')
if main_domain:
    print('using REACT_APP_DOMAIN =', main_domain)
else:
    print('WARNING: "REACT_APP_DOMAIN" env var not set, using example.com')
    main_domain = 'example.com'

main_csp = {
    'default-src': [
        "'self'",
    ],
    'script-src': [
        "'self'",
        'storage.googleapis.com',  # workbox, TODO remove and change CDN
    ],
    'font-src': [
        "'self'",
        'data:',
    ],
    'style-src': [
        "'self'",
        "'unsafe-inline'",  # TODO remove
    ],
    'frame-src': [
        "'self'",
        'data:',
    ],
    'img-src': [
        "'self'",
        'blob:',
        'data:',
    ],
    'media-src': [
        "'self'",
    ],
    'connect-src': [
        "'self'",
        'https://sentry.io',
        f'https://ui.{main_domain}',
        f'https://auth.{main_domain}'
    ],
}

auth_iframe_csp = {
    'default-src': [
        "'none'",
    ],
    'connect-src': [
        f'https://auth.{main_domain}',
    ],
    'style-src': [
        f'https://app.{main_domain}',
    ],
}


def replace_css(m):
    url = m.group(1)
    r = urllib.request.urlopen(url)
    assert r.status == 200, r.status
    return r.read().decode()


def before():
    # remove the unused reload prompt stuff from index.html
    path = THIS_DIR / 'src' / 'index.js'
    new_content = re.sub(r'^// *{{.+?^// *}}', '', path.read_text(), flags=re.S | re.M)
    new_content = re.sub(r'\n+$', '\n', new_content)
    path.write_text(new_content)

    # replace bootstrap import with the real thing
    # (this could be replaced by using the main css bundles)
    path = THIS_DIR / 'public' / 'auth-iframes' / 'styles.css'
    styles = path.read_text()
    styles = re.sub(r'@import url\("(.+?)"\);', replace_css, styles)
    path.write_text(styles)

    # replace urls in login iframe
    path = THIS_DIR / 'public' / 'auth-iframes' / 'login.html'
    content = path.read_text()
    path.write_text(
        content
        .replace('http://localhost:8000/auth', f'https://auth.{main_domain}')
        .replace('http://localhost:3000', f'https://app.{main_domain}')
    )


def get_script(path: Path):
    content = path.read_text()
    m = re.search(r'<script>(.+?)</script>', content, flags=re.S)
    if not m:
        raise RuntimeError(f'script now found in {path!r}')
    js = m.group(1)
    return f"'sha256-{base64.b64encode(hashlib.sha256(js.encode()).digest()).decode()}'"


def after():
    main_csp['script-src'].append(get_script(THIS_DIR / 'build' / 'index.html'))

    raven_dsn = os.getenv('RAVEN_DSN', None)
    if raven_dsn:
        m = re.search(r'^https://(.+)@sentry\.io/(.+)', raven_dsn)
        if m:
            key, app = m.groups()
            main_csp['report-uri'] = [f'https://sentry.io/api/{app}/security/?sentry_key={key}']
        else:
            print('WARNING: app and key not found in RAVEN_DSN', raven_dsn)

    auth_iframe_csp['script-src'] = [get_script(THIS_DIR / 'build' / 'auth-iframes' / 'login.html')]

    replacements = {
        'main_csp': main_csp,
        'auth_iframe_csp': auth_iframe_csp,
    }
    path = THIS_DIR / '..' / 'netlify.toml'
    content = path.read_text()
    for k, v in replacements.items():
        csp = ' '.join(f'{k} {" ".join(v)};' for k, v in v.items())
        print(f'setting {k} CSP header to: {csp}')
        content = content.replace('{%s}' % k, csp)
    path.write_text(content)


if __name__ == '__main__':
    before()
    subprocess.run(['yarn', 'build'], cwd=str(THIS_DIR), check=True)
    after()
