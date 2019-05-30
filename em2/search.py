import re
from typing import TYPE_CHECKING, Dict, List, Optional, Set

from buildpg import Func, V, funcs

from em2.utils.core import message_simplify
from em2.utils.db import Connections

if TYPE_CHECKING:
    from .core import ActionModel, File, CreateConvModel  # noqa: F401


has_files_sentinel = 'conversation.has.files'


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
    addresses |= {p.split('@', 1)[1] for p in addresses}
    if files:
        files = {f.name for f in files if f.name}
        files.add(has_files_sentinel)
        files |= set(n.split('.', 1)[1] for n in files if '.' in n)
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
            files.add(has_files_sentinel)
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


search_sql = """
select json_build_object(
  'conversations', conversations
) from (
  select coalesce(array_to_json(array_agg(row_to_json(t))), '[]') as conversations
  from (
    select conv_key, ts
    from search s
    join search_conv sc on s.conv = sc.id
    where :where
    group by conv_key, ts
    order by ts desc
    limit 50
  ) t
) conversations
"""


async def search(conns: Connections, user_id: int, query: str):
    new_query, named_filters = parse(query)
    if not (new_query or named_filters):
        # nothing to filter on
        return '{"results": []}'

    where = V('user_ids').contains([user_id])

    if new_query:
        query_match = V('vector').matches(Func('websearch_to_tsquery', new_query))
        if re_hex.fullmatch(new_query):
            # looks like it could be a conv key, search for that too
            where &= funcs.OR(query_match, V('conv_key').like('%' + new_query + '%'))
        else:
            where &= query_match

    for name, value in named_filters:
        where &= apply_named_filters(name, value)
    # debug(where)

    return await conns.search.fetchval_b(search_sql, where=where)


prefixes = ('from', 'include', 'to', 'file', 'attachment', 'has', 'subject')
re_special = re.compile(fr"""(?:^|\s|,)({'|'.join(prefixes)})s?:((["']).*?[^\\]\3|\S*)""", flags=re.S)
re_hex = re.compile('[a-f0-9]+', flags=re.S)
re_tsquery = re.compile(r"""[^:*&|%"'\s]{2,}""")
re_file_match = re.compile(r'(?:file|attachment)s')


def parse(query: str):
    groups = []

    def replace(m):
        prefix = m.group(1).lower()
        value = m.group(2).strip('"\'')
        groups.append((prefix, value))
        return ''

    new_query = re_special.sub(replace, query)
    return new_query.strip(' '), groups


def apply_named_filters(name: str, value: str):
    if name == 'from':
        return V('creator_email').like(f'%{value}%')
    elif name == 'include':
        return build_ts_query(value, 'B')
    elif name == 'to':
        addresses = re_tsquery.findall(value)
        not_creator = [funcs.NOT(V('creator_email').like(f'%{a}%')) for a in addresses]
        return funcs.AND(build_ts_query(value, 'B'), *not_creator)
    elif re_file_match.fullmatch(name):
        return build_ts_query(value, 'C', sentinel=has_files_sentinel)
    elif name == 'has':
        if value.lower() in {'file', 'files', 'attachment', 'attachments'}:
            # this is just any files
            return build_ts_query('', 'C', sentinel=has_files_sentinel)
        else:
            # assume this is the same as includes
            return build_ts_query(value, 'B')
    else:
        assert name == 'subject', name
        # TODO could do this better to get closer to websearch_to_tsquery
        return build_ts_query(value, 'A', prefixes=False)


def build_ts_query(value: str, weight: str, *, sentinel: Optional[str] = None, prefixes: bool = True):
    parts = re_tsquery.findall(value)
    query_parts = [f'{a}:{"*" if prefixes else ""}{weight}' for a in parts]
    if sentinel:
        query_parts.append(f'{sentinel}:{weight}')
    return V('vector').matches(Func('to_tsquery', ' & '.join(query_parts)))
