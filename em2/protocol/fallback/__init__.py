import logging
import secrets
from email.message import EmailMessage
from textwrap import indent
from typing import Any, Dict, List, Set

from .base_handler import BaseFallbackHandler
from .ses import SesFallbackHandler  # noqa F401

logger = logging.getLogger('em2.fallback')


class LogFallbackHandler(BaseFallbackHandler):
    async def send_message(self, *, e_from: str, to: Set[str], email_msg: EmailMessage) -> str:
        logger.info('%s > %s\n%s', e_from, to, indent(email_msg.as_string(), '  '))
        return 'log-fallback-' + secrets.token_hex(20)


async def fallback_send(ctx, actions: List[Dict[str, Any]]):
    fallback_handler: BaseFallbackHandler = ctx['fallback_handler']
    return await fallback_handler.send(actions)
