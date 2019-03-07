import logging
import secrets
from email.message import EmailMessage
from textwrap import indent
from typing import Set

from .base_handler import BaseFallbackHandler
from .aws import AwsFallbackHandler  # noqa F401

logger = logging.getLogger('em2.fallback')


class LogFallbackHandler(BaseFallbackHandler):
    async def send_message(self, *, e_from: str, to: Set[str], email_msg: EmailMessage) -> str:
        logger.info('%s > %s\n%s', e_from, to, indent(email_msg.as_string(), '  '))
        return secrets.token_hex(20)
