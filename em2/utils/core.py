import re
import textwrap
from enum import Enum, unique

from bs4 import BeautifulSoup


@unique
class MsgFormat(str, Enum):
    markdown = 'markdown'
    plain = 'plain'
    html = 'html'


_clean_markdown = [
    (re.compile(r'<.*?>', flags=re.S), ''),
    (re.compile(r'_(\S.*?\S)_'), r'\1'),
    (re.compile(r'\[(.+?)\]\(.*?\)'), r'\1'),
    (re.compile(r'(?:\*\*|`|~~)'), ''),
    (re.compile(r'^(#+|\*|\d+\.) ', flags=re.M), ''),
]
_clean_all = [
    (re.compile(r'^\s+'), ''),
    (re.compile(r'\s+$'), ''),
    (re.compile(r'[\x00-\x1f\x7f-\xa0]'), ''),
    (re.compile(r'[\t\n]+'), ' '),
    (re.compile(r' {2,}'), ' '),
]


def message_simplify(body: str, msg_format: MsgFormat) -> str:
    if msg_format == MsgFormat.markdown:
        for regex, p in _clean_markdown:
            body = regex.sub(p, body)
    elif msg_format == MsgFormat.html:
        soup = BeautifulSoup(body, 'html.parser')
        soup = soup.find('body') or soup

        for el_name in ('div.gmail_signature', 'style', 'script'):
            for el in soup.select(el_name):
                el.decompose()
        body = soup.text
    else:
        assert msg_format == MsgFormat.plain, msg_format

    for regex, p in _clean_all:
        body = regex.sub(p, body)
    return body


def message_preview(body: str, msg_format: MsgFormat) -> str:
    return textwrap.shorten(message_simplify(body, msg_format), width=140, placeholder='…')
