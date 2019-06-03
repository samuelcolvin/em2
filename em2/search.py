import re
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from buildpg import Empty, Func, V, funcs

from em2.utils.core import message_simplify
from em2.utils.db import Connections

if TYPE_CHECKING:  # pragma: no cover
    from .core import ActionModel, File, CreateConvModel  # noqa: F401

__all__ = ['search_create_conv', 'search_publish_conv', 'search_update', 'search']

has_files_sentinel = 'conversation.has.files'
min_length = 3
max_length = 100


async def search_create_conv(
    conns: Connections,
    *,
    conv_id: int,
    creator_id: int,
    creator_email: str,
    users: Dict[str, int],
    conv: 'CreateConvModel',
    files: Optional[List['File']],
):
    addresses = _prepare_address(creator_email, *users.keys())
    files = _prepare_files(files)
    body = message_simplify(conv.message, conv.msg_format)
    user_ids = [creator_id]
    if conv.publish:
        user_ids += list(users.values())

    await conns.main.execute(
        """
        insert into search (conv, action, user_ids, creator_email, vector)
        values (
          $1,
          1,
          $2,
          $3,
          setweight(to_tsvector($4), 'A') ||
          setweight(to_tsvector($5), 'B') ||
          setweight(to_tsvector($6), 'C') ||
          to_tsvector($7)
        )
        """,
        conv_id,
        user_ids,
        creator_email,
        conv.subject,
        addresses,
        files,
        body,
    )


async def search_publish_conv(conns: Connections, conv_id: int, old_key: str, new_key: str):
    await conns.main.execute(
        """
        with t as (
            select p.conv, array_agg(p.user_id) user_ids
            from participants p where p.conv = $1
            group by p.conv
        )
        update search set user_ids=t.user_ids from t where search.conv=t.conv
        """,
        conv_id,
    )


async def search_update(
    conns: Connections,
    conv_id: int,
    actions: List[Tuple[int, Optional[int], 'ActionModel']],
    files: Optional[List['File']],
):
    """
    If this gets slow it could be done on the worker.

    might need to use pg_column_size to to avoid vector getting too long.
    """
    from .core import ActionTypes

    s_update = SearchUpdate(conns, conv_id)
    async with conns.main.transaction():
        for action_id, user_id, action in actions:
            if action.act is ActionTypes.subject_modify:
                await s_update.modify_subject(action, action_id)
            elif action.act in {ActionTypes.msg_add, ActionTypes.msg_modify}:
                await s_update.msg_change(action, action_id, files)
            elif action.act is ActionTypes.prt_add:
                await s_update.prt_add(action, action_id, user_id)
            elif action.act is ActionTypes.prt_remove:
                await s_update.prt_remove(user_id)


class SearchUpdate:
    def __init__(self, conns: Connections, conv_id: int):
        self.conns = conns
        self.conv_id: int = conv_id

    async def modify_subject(self, action: 'ActionModel', action_id: int):
        await self.conns.main.execute(
            """
            update search set vector=vector || setweight(to_tsvector($1), 'A'), action=$2, ts=current_timestamp
            where conv=$3 and freeze_action=0
            """,
            action.body,
            action_id,
            self.conv_id,
        )

    async def msg_change(self, action: 'ActionModel', action_id: int, files: Optional[List['File']]):
        await self.conns.main.execute(
            """
            update search set
              vector=vector || setweight(to_tsvector($1), 'C') || to_tsvector($2), action=$3, ts=current_timestamp
            where conv=$4 and freeze_action=0
            """,
            _prepare_files(files),
            message_simplify(action.body, action.msg_format),
            action_id,
            self.conv_id,
        )

    async def prt_add(self, action: 'ActionModel', action_id: int, user_id: int):
        email = action.participant
        async with self.conns.main.transaction():
            v = await self.conns.main.execute(
                """
                update search set user_ids=array_remove(user_ids, $1)
                where conv=$2 and freeze_action!=0 and user_ids @> array[$1::bigint]
                """,
                user_id,
                self.conv_id,
            )
            if v != 'UPDATE 0':
                # if we've got any search entries with no users delete them
                await self.conns.main.execute("delete from search where conv=$1 and user_ids='{}'", self.conv_id)
            await self.conns.main.execute(
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

    async def prt_remove(self, user_id: int):
        async with self.conns.main.transaction():
            await self.conns.main.execute(
                """
                insert into search (conv, action, freeze_action, user_ids, creator_email, vector)
                select $1, s.action, s.action, array[$2::bigint], s.creator_email, s.vector
                from search s where conv=$1 and freeze_action=0
                on conflict (conv, freeze_action) do update set user_ids=search.user_ids || array[$2::bigint]
                """,
                self.conv_id,
                user_id,
            )
            await self.conns.main.execute(
                """
                update search set user_ids=array_remove(user_ids, $1), ts=current_timestamp
                where conv=$2 and freeze_action=0
                """,
                user_id,
                self.conv_id,
            )


search_rank_sql = """
select json_build_object(
  'conversations', conversations
) from (
  select coalesce(array_to_json(array_agg(row_to_json(t))), '[]') as conversations
  from (
    select key, updated_ts, details, publish_ts, seen
    from (
      select
        c.key, coalesce(s.ts, c.updated_ts) updated_ts, c.details, c.publish_ts, p.seen, s.vector,
        ts_rank_cd(vector, :query_func, 16) rank
      from search s
      join conversations c on s.conv = c.id
      join participants p on c.id = p.conv
      where p.user_id = :user_id and user_ids @> array[:user_id::bigint] :where
      order by s.ts desc
      limit 200
    ) tt
    order by rank desc
    limit 50
  ) t
) conversations
"""

search_ts_sql = """
select json_build_object(
  'conversations', conversations
) from (
  select coalesce(array_to_json(array_agg(row_to_json(t))), '[]') as conversations
  from (
    select c.key, coalesce(s.ts, c.updated_ts) updated_ts, c.details, c.publish_ts, p.seen
    from search s
    join conversations c on s.conv = c.id
    join participants p on c.id = p.conv
    where p.user_id = :user_id and user_ids @> array[:user_id::bigint] :where
    order by s.ts desc
    limit 50
  ) t
) conversations
"""


async def search(conns: Connections, user_id: int, query: str):
    # TODO cache results based on user id and query, clear on prepare above
    new_query, named_filters = _parse_query(query)
    if not new_query and not named_filters:
        # nothing to filter on
        return '{"conversations": []}'

    where = Empty()

    if new_query:
        query_func = _build_main_query(new_query)
        query_match = V('s.vector').matches(query_func)
        if re_hex.fullmatch(new_query):
            # looks like it could be a conv key, search for that too
            where &= funcs.OR(query_match, V('c.key').like('%' + new_query.lower() + '%'))
        else:
            where &= query_match
        sql = search_rank_sql
    else:
        query_func = Empty()
        sql = search_ts_sql

    for name, value in named_filters:
        where &= _apply_named_filters(name, value)

    return await conns.main.fetchval_b(sql, user_id=user_id, where=where, query_func=query_func)


re_null = re.compile('\x00')
prefixes = ('from', 'include', 'to', 'file', 'attachment', 'has', 'subject')
re_special = re.compile(fr"""(?:^|\s|,)({'|'.join(prefixes)})s?:((["']).*?[^\\]\3|\S*)""", re.I)
re_hex = re.compile('[a-f0-9]{5,}', re.I)

# characters that cause syntax errors in to_tsquery and/or should be used to split
pg_tsquery_split = ''.join((':', '&', '|', '"', "'", '!', '*', r'\s'))
re_tsquery = re.compile(f'[^{pg_tsquery_split}]{{2,}}')

# any of these and we should fall back to websearch_to_tsquery
pg_requires_websearch = ''.join((':', '&', '|', '%', '"', "'", '<', '>', '!', '*', '(', ')'))
re_websearch = re.compile(fr'(?:[{pg_requires_websearch}]|\sor\s)', re.I)

re_file_attachment = re.compile(r'(?:file|attachment)s?', re.I)


def _parse_query(query: str) -> Tuple[Optional[str], List[str]]:
    groups = []

    def replace(m):
        prefix = m.group(1).lower()
        value = m.group(2).strip('"\'')
        groups.append((prefix, value))
        return ''

    new_query = re_null.sub('', query)[:max_length]
    new_query = re_special.sub(replace, new_query).strip(' ')
    if len(new_query) < min_length:
        new_query = None
    return new_query, groups


def _build_main_query(query: str):
    if not re_websearch.search(query):
        words = re_tsquery.findall(query)
        if words:
            # nothing funny and words found, use a "foo & bar:*"
            return Func('to_tsquery', ' & '.join(words) + ':*')

    # query has got special characters in, just use websearch_to_tsquery
    return Func('websearch_to_tsquery', query)


def _apply_named_filters(name: str, value: str):
    if name == 'from':
        return V('s.creator_email').like(f'%{value}%')
    elif name == 'include':
        return _build_ts_query(value, 'B')
    elif name == 'to':
        addresses = re_tsquery.findall(value)
        not_creator = [funcs.NOT(V('s.creator_email').like(f'%{a}%')) for a in addresses]
        return funcs.AND(_build_ts_query(value, 'B'), *not_creator)
    elif name in {'file', 'attachment'}:
        return _build_ts_query(value, 'C', sentinel=has_files_sentinel)
    elif name == 'has':
        if re_file_attachment.fullmatch(value):
            # this is just any files
            return _build_ts_query('', 'C', sentinel=has_files_sentinel)
        else:
            # assume this is the same as includes, this is a little weird, could ignore at the query stage.
            return _build_ts_query(value, 'B')
    else:
        assert name == 'subject', name
        # TODO could do this better to get closer to websearch_to_tsquery
        return _build_ts_query(value, 'A', prefixes=False)


def _build_ts_query(value: str, weight: str, *, sentinel: Optional[str] = None, prefixes: bool = True):
    parts = re_tsquery.findall(value)
    query_parts = [f'{a}:{"*" if prefixes else ""}{weight}' for a in parts]
    if sentinel:
        query_parts.append(f'{sentinel}:{weight}')
    return V('s.vector').matches(Func('to_tsquery', ' & '.join(query_parts)))


def _prepare_address(*addresses: str) -> str:
    a = set(addresses)
    a |= {p.split('@', 1)[1] for p in a}
    return ' '.join(sorted(a))  # sort just to make tests easier


def _prepare_files(files: Optional[List['File']]) -> str:
    if files:
        f = {has_files_sentinel, *(f.name for f in files if f.name)}
        f |= {n.split('.', 1)[1] for n in f if '.' in n}
        return ' '.join(sorted(f))
    else:
        return ''
