import hashlib
from dataclasses import dataclass
from email import policy as email_policy
from email.message import EmailMessage
from email.parser import BytesParser
from typing import Generator, Optional

__all__ = ('parse_smtp', 'File', 'find_smtp_files')


email_parser = BytesParser(policy=email_policy.default)


def parse_smtp(body: bytes) -> EmailMessage:
    return email_parser.parsebytes(body)


@dataclass
class File:
    filename: str
    ref: str
    type: str
    content_type: str
    content: Optional[bytes]


def find_smtp_files(m: EmailMessage, inc_content: bool = False) -> Generator[File, None, None]:
    for part in m.iter_parts():
        disposition = part.get_content_disposition()
        if disposition:
            # https://tools.ietf.org/html/rfc2392
            file_name = part.get_filename()

            if inc_content:
                content = _get_content(part)
            else:
                content = None

            content_id = part['Content-ID']
            if content_id:
                ref = content_id.strip('<>')
            else:
                hash_content = content or _get_content(part)
                ref = hashlib.md5(file_name.encode() + hash_content).hexdigest()

            yield File(
                file_name, ref, 'inline' if disposition == 'inline' else 'attachment', part.get_content_type(), content
            )
        else:
            yield from find_smtp_files(part)


def _get_content(msg: EmailMessage) -> bytes:
    content = msg.get_content()
    if isinstance(content, str):
        content = content.encode()
    return content
