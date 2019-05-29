from typing import TYPE_CHECKING, Dict, List, Optional, Set

from em2.utils.core import message_simplify
from em2.utils.db import Connections

if TYPE_CHECKING:
    from .core import ActionModel, File, CreateConvModel  # noqa: F401


async def search_create_conv(
    conns: Connections,
    *,
    conv_key: str,
    creator_id: int,
    creator_email: str,
    users: Dict[str, int],
    conv: 'CreateConvModel',
    files: Optional[List['File']],
):
    addresses = users.keys() | {creator_email}
    addresses |= {'@' + p.split('@', 1)[1] for p in addresses}
    if files:
        files = {f.name for f in files if f.name}
        files |= set('.' + n.split('.', 1)[1] for n in files if '.' in n)
    else:
        files = []
    body = message_simplify(conv.message, conv.msg_format)

    await conns.search.execute(
        """
        with conv as (insert into search_conv (conv_key, creator_email) values ($1, $2) returning id)
        insert into search (conv, user_ids, vector)
        select
          id,
          $3,
          setweight(to_tsvector($4), 'A') ||
          setweight(to_tsvector($5), 'B') ||
          setweight(to_tsvector($6), 'C') ||
          to_tsvector($7)
        from conv
        """,
        conv_key,
        creator_email,
        list(users.values()) if conv.publish else [creator_id],
        conv.subject,
        ' '.join(sorted(addresses)),  # sort just to make tests easier
        ' '.join(sorted(files)),
        body,
    )


class SearchUpdate:
    """
    TODO might need a "cleanup" method that adds a blank entry with to update user_ids and sets search_conv ts?
    """

    def __init__(self, conns: Connections, conv_key: str):
        self.conns = conns
        self.conv_key = conv_key
        self.conv_id: int = None
        self.user_ids: Set[int] = None
        self.creator_email: str = None
        from .core import ActionTypes

        self.coro_lookup = {
            ActionTypes.subject_modify: self._modify_subject,
            ActionTypes.msg_add: self._msg_change,
            ActionTypes.msg_modify: self._msg_change,
            ActionTypes.prt_add: self._prt_add,
            ActionTypes.prt_remove: self._prt_remove,
        }

    async def prepare(self):
        if self.user_ids is not None:
            return
        self.conv_id, prts, self.creator_email = await self.conns.search.fetchrow(
            """
            select conv, user_ids, creator_email from search s
            join search_conv sc on s.conv = sc.id
            where conv_key=$1
            """,
            self.conv_key,
        )
        self.user_ids = set(prts)

    async def __call__(self, action: 'ActionModel', user_id: Optional[int], files: Optional[List['File']]):
        coro = self.coro_lookup.get(action.act)
        if coro is None:
            return

        await self.prepare()
        await coro(action, user_id, files)

    async def _modify_subject(self, action: 'ActionModel', user_id, files):
        await self._insert(action.body, 'A')

    async def _msg_change(self, action: 'ActionModel', user_id, files):
        if files:
            files = {f.name for f in files if f.name}
            files |= set('.' + n.split('.', 1)[1] for n in files if '.' in n)
        else:
            files = []
        await self.conns.search.execute(
            """
            insert into search (conv, user_ids, vector)
            values ($1, $2, setweight(to_tsvector($3), 'C') || to_tsvector($4))
            """,
            self.conv_id,
            self.user_ids,
            ' '.join(files),
            message_simplify(action.body, action.msg_format),
        )

    async def _prt_add(self, action: 'ActionModel', user_id, files):
        await self.conns.search.execute(
            'update search set user_ids=user_ids || array[$1::bigint] where conv=$2', user_id, self.conv_id
        )

        self.user_ids.add(user_id)
        email = action.participant
        domain = email.split('@', 1)[1]
        await self._insert(f'{email} @{domain}', 'B')

    async def _prt_remove(self, action: 'ActionModel', user_id, files):
        """
        Have to create a search entry even though it has nothing in it so the removed participant is stored
        for `prepare` next time
        """
        self.user_ids.remove(user_id)
        await self.conns.search.execute(
            'insert into search (conv, user_ids) values ($1, $2)', self.conv_id, self.user_ids
        )

    async def _insert(self, vector: str, weight: str):
        await self.conns.search.execute(
            """
            insert into search (conv, user_ids, vector)
            values ($1, $2, setweight(to_tsvector($3), $4::"char"))
            """,
            self.conv_id,
            self.user_ids,
            vector,
            weight.encode(),
        )
