import re
from typing import TYPE_CHECKING, Dict, List, Optional

from buildpg import Empty, Func, V, funcs

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
        insert into search (conv, action, user_ids, vector)
        select
          id,
          1,
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
        self.conv_id: Optional[int] = None

    async def prepare(self):
        if self.conv_id is None:
            self.conv_id = await self.conns.search.fetchval(
                """
                select conv from search s
                join search_conv sc on s.conv = sc.id
                where conv_key=$1
                """,
                self.conv_key,
            )

    async def __call__(
        self, action: 'ActionModel', action_id: int, user_id: Optional[int], files: Optional[List['File']]
    ):
        from .core import ActionTypes

        if action.act is ActionTypes.subject_modify:
            await self.prepare()
            await self._modify_subject(action, action_id)
        elif action.act in {ActionTypes.msg_add, ActionTypes.msg_modify}:
            await self.prepare()
            await self._msg_change(action, action_id, files)
        elif action.act is ActionTypes.prt_add:
            await self.prepare()
            await self._prt_add(action, action_id, user_id)
        elif action.act is ActionTypes.prt_remove:
            await self.prepare()
            await self._prt_remove(user_id)

    async def _modify_subject(self, action: 'ActionModel', action_id: int):
        await self.conns.search.execute(
            """
            update search set vector=vector || setweight(to_tsvector($1), 'A'), action=$2, ts=current_timestamp
            where conv=$3 and freeze_action=0
            """,
            action.body,
            action_id,
            self.conv_id,
        )

    async def _msg_change(self, action: 'ActionModel', action_id: int, files: Optional[List['File']]):
        if files:
            files = {f.name for f in files if f.name}
            files.add(has_files_sentinel)
            files |= set('.' + n.split('.', 1)[1] for n in files if '.' in n)
        else:
            files = []
        await self.conns.search.execute(
            """
            update search set
              vector=vector || setweight(to_tsvector($1), 'C') || to_tsvector($2), action=$3, ts=current_timestamp
            where conv=$4 and freeze_action=0
            """,
            ' '.join(files),
            message_simplify(action.body, action.msg_format),
            action_id,
            self.conv_id,
        )

    async def _prt_add(self, action: 'ActionModel', action_id: int, user_id: int):
        # TODO remove the user from existing search entries on this conversation and delete them if required
        email = action.participant
        await self.conns.search.execute(
            """
            update search set
              user_ids=user_ids || array[$1::bigint],
              vector=vector || setweight(to_tsvector($2), 'B'),
              action=$3,
              ts=current_timestamp
            where conv=$4 and freeze_action=0
            """,
            user_id,
            '{} {}'.format(email, email.split('@', 1)[1]),
            action_id,
            self.conv_id,
        )

    async def _prt_remove(self, user_id: int):
        await self.conns.search.execute(
            """
            insert into search (conv, action, freeze_action, user_ids, vector)
            select $1, s.action, s.action, array[$2::bigint], s.vector from search s where conv=$1 and freeze_action=0
            on conflict (conv, freeze_action) do update set user_ids=search.user_ids || array[$2::bigint]
            """,
            self.conv_id,
            user_id,
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
    where user_ids @> array[:user_id::bigint] :where
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

    where = Empty()

    if new_query:
        query_match = V('vector').matches(Func('websearch_to_tsquery', new_query))
        if re_hex.fullmatch(new_query):
            # looks like it could be a conv key, search for that too
            where &= funcs.OR(query_match, V('conv_key').like('%' + new_query + '%'))
        else:
            where &= query_match

    for name, value in named_filters:
        where &= apply_named_filters(name, value)

    return await conns.search.fetchval_b(search_sql, user_id=user_id, where=where)


prefixes = ('from', 'include', 'to', 'file', 'attachment', 'has', 'subject')
re_special = re.compile(fr"""(?:^|\s|,)({'|'.join(prefixes)})s?:((["']).*?[^\\]\3|\S*)""", re.I)
re_hex = re.compile('[a-f0-9]+', re.I)
re_tsquery = re.compile(r"""[^:*&|%"'\s]{2,}""")
re_file_attachment = re.compile(r'(?:file|attachment)s?', re.I)


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
    elif name in {'file', 'attachment'}:
        return build_ts_query(value, 'C', sentinel=has_files_sentinel)
    elif name == 'has':
        if re_file_attachment.fullmatch(value):
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
