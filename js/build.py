#!/usr/bin/env python3.6
"""
Build a production js bundle, calls "yarn build", but also does some other stuff.

Designed primarily for netlify.
"""
import base64
import hashlib
import json
import os
import re
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path

this_dir = Path(__file__).parent
build_dir = this_dir / 'build'

main_domain = os.getenv('REACT_APP_DOMAIN')
if main_domain:
    print('using REACT_APP_DOMAIN =', main_domain)
else:
    print('WARNING: "REACT_APP_DOMAIN" env var not set, using example.com')
    main_domain = 'example.com'


iframe_msg_old_path = Path('iframes') / 'message' / 'message.html'

review_id = os.getenv('REVIEW_ID')
if review_id and os.getenv('CONTEXT') == 'deploy-preview':
    origin = f'https://deploy-preview-{review_id}--em2.netlify.com'
else:
    origin = f'https://app.{main_domain}'

iframe_msg_hash = hashlib.md5((this_dir / 'public' / iframe_msg_old_path).read_bytes() + origin.encode()).hexdigest()
iframe_msg_new_path = iframe_msg_old_path.with_name(f'message.{iframe_msg_hash[:8]}.html')

main_csp = {
    'default-src': ["'self'"],
    'script-src': ["'self'", 'storage.googleapis.com'],  # workbox, TODO remove and change CDN
    'font-src': ["'self'", 'data:'],
    'style-src': ["'self'", "'unsafe-inline'"],  # TODO remove
    'frame-src': ["'self'", 'data:'],
    'img-src': ["'self'", 'blob:', 'data:'],
    'media-src': ["'self'"],
    'connect-src': [
        "'self'",
        'https://sentry.io',
        f'https://ui.{main_domain}',
        f'wss://ui.{main_domain}',
        f'https://auth.{main_domain}',
        f'https://attachments.{main_domain}',
    ],
}
iframe_auth_csp = {'default-src': ["'none'"], 'connect-src': [f'https://auth.{main_domain}'], 'style-src': [origin]}
iframe_msg_csp = {
    'default-src': ["'none'"],
    'style-src': ["'unsafe-inline'"],
    'font-src': ["'unsafe-inline'"],
    'img-src': [
        "'unsafe-inline'",
        f'https://ui.{main_domain}',
        f'https://temp.{main_domain}',
        f'https://cache.{main_domain}',
    ],
}
details_env = 'BRANCH', 'PULL_REQUEST', 'HEAD', 'CONTEXT', 'REVIEW_ID'


def replace_css(m):
    url = m.group(1)
    r = urllib.request.urlopen(url)
    assert r.status == 200, r.status
    css = r.read().decode()
    return re.sub(r'/\*#.+?\*/', '', css)


def get_script(path: Path):
    content = path.read_text()
    m = re.search(r'<script>(.+?)</script>', content, flags=re.S)
    if not m:
        raise RuntimeError(f'script now found in {path!r}')
    js = m.group(1)
    return f"'sha256-{base64.b64encode(hashlib.sha256(js.encode()).digest()).decode()}'"


def mod(version):
    # replace bootstrap import with the real thing
    # (this could be replaced by using the main css bundles)
    path = build_dir / 'iframes' / 'auth' / 'styles.css'
    styles = path.read_text()
    styles = re.sub(r'@import url\("(.+?)"\);', replace_css, styles)
    path.write_text(styles)

    # replace urls in iframes
    for path in (build_dir / 'iframes').glob('**/*.html'):
        print('changing urls in', path)
        path.write_text(path.read_text().replace('http://localhost:3000', origin))

    main_csp['script-src'].append(get_script(build_dir / 'index.html'))

    raven_dsn = os.getenv('RAVEN_DSN', None)
    if raven_dsn:
        m = re.search(r'^https://(.+)@sentry\.io/(.+)', raven_dsn)
        if m:
            key, app = m.groups()
            main_csp['report-uri'] = [f'https://sentry.io/api/{app}/security/?sentry_key={key}']
        else:
            print('WARNING: app and key not found in RAVEN_DSN', raven_dsn)

    iframe_auth_csp['script-src'] = [get_script(build_dir / 'iframes' / 'auth' / 'login.html')]
    iframe_msg_csp['script-src'] = [get_script(build_dir / iframe_msg_old_path)]

    replacements = {'main_csp': main_csp, 'iframe_auth_csp': iframe_auth_csp, 'iframe_msg_csp': iframe_msg_csp}
    headers_path = build_dir / '_headers'
    content = headers_path.read_text()
    for k, v in replacements.items():
        csp = ' '.join(f'{k} {" ".join(v)};' for k, v in v.items())
        print(f'setting {k} CSP header')
        content = content.replace('{%s}' % k, csp)
    headers_path.write_text(content)

    # create build_details.txt with details about the build
    build_details = {k: os.getenv(k) for k in details_env}
    build_details.update(version=version, time=str(datetime.utcnow()))
    (build_dir / 'build_details.txt').write_text(json.dumps(build_details, indent=2))
    (build_dir / 'version.txt').write_text(version)

    # rename iframes/message/message.html and add to precache-manifest.js
    (build_dir / iframe_msg_old_path).rename(build_dir / iframe_msg_new_path)
    man_path = next(build_dir.glob('precache-manifest.*'))
    man_data = json.loads(re.search(r'\.concat\((\[.+\])', man_path.read_text(), flags=re.S).group(1))
    man_data.append({'revision': iframe_msg_hash, 'url': f'/{iframe_msg_new_path}'})

    man_path.write_text(f'self.__precacheManifest = {json.dumps(man_data, indent=2)};')

    # remove asset-manifest.json which doesn't seem to do anything for us
    (build_dir / 'asset-manifest.json').unlink()

    # append service-worker.js to em2-service-worker.js to enable caching and delete service-worker.js
    em2_sw_path = build_dir / 'em2-service-worker.js'
    std_sw_path = build_dir / 'service-worker.js'
    # change work box path https://github.com/cdnjs/cdnjs/issues/12041
    with em2_sw_path.open('a') as f:
        f.write('\n// Standard CRA service-worker.js:\n')
        f.write(std_sw_path.read_text())
    std_sw_path.unlink()


if __name__ == '__main__':
    env = dict(os.environ)
    version = os.getenv('COMMIT_REF')
    if not version:
        p = subprocess.run(['git', 'rev-parse', 'HEAD'], stdout=subprocess.PIPE, check=True, universal_newlines=True)
        version = p.stdout.strip('\n')
    env.update(REACT_APP_IFRAME_MESSAGE=f'/{iframe_msg_new_path}', REACT_APP_VERSION=version)

    subprocess.run(['yarn', 'build'], cwd=str(this_dir), env=env, check=True)
    mod(version)
