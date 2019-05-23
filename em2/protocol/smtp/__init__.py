import logging
import secrets
from email.message import EmailMessage
from textwrap import indent
from typing import Any, Dict, List, Set

from .base_handler import BaseSmtpHandler
from .ses import SesSmtpHandler  # noqa F401

logger = logging.getLogger('em2.smtp')


class LogSmtpHandler(BaseSmtpHandler):
    async def send_message(self, *, e_from: str, to: Set[str], email_msg: EmailMessage) -> str:
        logger.info('%s > %s\n%s', e_from, ','.join(sorted(to)), indent(email_msg.as_string(), '  '))
        return 'log-smtp-' + secrets.token_hex(20)


async def smtp_send(ctx, actions: List[Dict[str, Any]]):
    smtp_handler: BaseSmtpHandler = ctx['smtp_handler']
    return await smtp_handler.send(actions)
