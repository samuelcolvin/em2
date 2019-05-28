from typing import TYPE_CHECKING, Dict, List, Optional

from em2.utils.core import message_simplify

if TYPE_CHECKING:
    from .core import Connections, File, CreateConvModel  # noqa: F401


async def search_create_conv(
    conns: 'Connections',
    *,
    conv_key: str,
    creator_id: int,
    creator_email: str,
    participants: Dict[str, int],
    conv: 'CreateConvModel',
    files: Optional[List['File']],
):
    addresses = participants.keys() | set('@' + p.split('@', 1)[1] for p in participants)
    if files:
        files = {f.name for f in files if f.name}
        files |= set('.' + n.split('.', 1)[1] for n in files if '.' in n)
    else:
        files = []
    body = message_simplify(conv.message, conv.msg_format)

    await conns.search.execute(
        """
        insert into search (conv_key, action_id, participant_ids, creator_email, vector)
        values (
          $1,
          1,
          $2,
          $3,
          setweight(to_tsvector($4), 'A') ||
          setweight(to_tsvector($5), 'B') ||
          setweight(to_tsvector($6), 'C') ||
          setweight(to_tsvector($7), 'D')
        )
        """,
        conv_key,
        list(participants.values()) if conv.publish else [creator_id],
        creator_email,
        conv.subject,
        ' '.join(addresses),
        ' '.join(files),
        body,
    )
