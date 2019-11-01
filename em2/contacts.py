from em2.utils.db import Connections


async def add_contacts(conns: Connections, conv_id: int, actor_id: int, known_local: bool = False):
    """
    Every participant in the conversation should be a contact of an actor in that conversation, they might have been in
    the conversation before or the actor might just have added them, either way they should be a contact of the actor.
    """
    if not known_local and not await conns.main.fetchval(
        "select 1 from users where id=$1 and user_type='local'", actor_id
    ):
        # user is not local and doesn't need contacts
        return

    await conns.main.execute(
        """
        insert into contacts (owner, profile_user)
        (
          select $2, user_id from participants
          where conv = $1 and user_id != $2 and removal_action_id is null
        )
        on conflict (owner, profile_user) do nothing
        """,
        conv_id,
        actor_id,
    )
