-- includes both local and remote users,
-- TODO once we have address book and public profiles, we'll need a way of getting name for an email
create table users (
  id bigserial primary key,
  email varchar(255) not null
);
create unique index user_email on users using btree (email);

create table conversations (
  id bigserial primary key,
  key varchar(64) unique,
  published bool default false,
  creator int not null references users on delete restrict,
  created_ts timestamptz not null,
  updated_ts timestamptz not null,  -- if not used in queries, could be removed as duplicated in actions
  last_action_id int not null default 0 check (last_action_id >= 0),
  details json
);
create index conversations_created_ts on conversations using btree (created_ts);

create table participants (
  id bigserial primary key,
  conv int not null references conversations on delete cascade,
  user_id int not null references users on delete restrict,
  -- todo permissions, hidden, status, has_seen/unread
  unique (conv, user_id)
);

-- see core.ActionsTypes enum which matches this
create type ActionTypes as enum (
  'conv:publish', 'conv:create',
  'subject:modify', 'subject:lock', 'subject:release',
  'expiry:modify',  -- rename to conv:expiry?
  'message:add', 'message:modify', 'message:delete', 'message:recover', 'message:lock', 'message:release',
  'participant:add', 'participant:remove', 'participant:modify'
);
-- see core.MsgFormat enum which matches this
create type MsgFormat as enum ('markdown', 'plain', 'html');

create table actions (
  pk bigserial primary key,
  id int not null check (id >= 0),
  conv int not null references conversations on delete cascade,
  act ActionTypes not null,
  actor int not null references users on delete restrict,
  ts timestamptz not null default current_timestamp,

  follows int references actions,  -- when modifying/deleting etc. a component
  participant_user int references users on delete restrict,
  body text,
  msg_parent int references actions,
  msg_format MsgFormat,

  -- todo participant details, attachment details, perhaps json for other types

  unique (conv, id),
  -- only one action can follow a given action: where follows is required, a linear direct time line is enforced
  unique (conv, follows)
);
create index action_id on actions using btree (id);
create index action_act_id on actions using btree (conv, act, id);
create index action_conv_msg_parent on actions using btree (conv, msg_parent);

-- this could be run on every "migration"
create or replace function action_insert() returns trigger as $$
  -- could replace all this with plv8
  declare
    -- todo add actor name when we have it, could add attachment count etc. here too
    -- if this ends up being a bottle neck, we could cache particular values on the the conversation
    -- and update them individually
    details_ json = json_build_object(
      'act', new.act,
      'sub', (
        case when new.act=any(array['conv:publish', 'conv:create', 'subject:modify']::ActionTypes[]) then
          new.body
        else
          (select body
           from actions
           where conv=new.conv and act=any(array['conv:publish', 'conv:create', 'subject:modify']::ActionTypes[])
           order by id desc limit 1)
        end
      ),
      'email', (select email from users where id=new.actor),
      'body', left(
        case when new.act=any(array['message:add', 'message:modify']::ActionTypes[]) then
          new.body
        else
          (select body
           from actions
           where conv=new.conv and act=any(array['message:add', 'message:modify']::ActionTypes[])
           order by id desc limit 1)
        end, 100
      ),
      'prts', (select count(*) from participants where conv=new.conv),
      'msgs', (
        select count(*) filter (where act='message:add') - count(*) filter (where act='message:delete')
        from actions where conv=new.conv and act=any(array['message:add', 'message:delete']::ActionTypes[])
      ) + case when new.act='message:add' then 1
               when new.act='message:delete' then -1
               else 0 end
    );
  begin
    update conversations
      set updated_ts=new.ts, details=details_, last_action_id=last_action_id + 1
      where id=new.conv
      returning last_action_id into new.id;
    return new;
  end;
$$ language plpgsql;

create trigger action_insert before insert on actions for each row execute procedure action_insert();

-- todo attachments


----------------------------------------------------------------------------------
-- auth tables, currently in the the same database as everything else, but with --
-- no links so could easily be moved to a separate db.                          --
----------------------------------------------------------------------------------
-- todo table of supported domains/nodes

create type account_status as enum ('pending', 'active', 'suspended');

create table auth_users (
  id bigserial primary key,
  email varchar(255) not null unique,
  first_name varchar(63),
  last_name varchar(63),
  password_hash varchar(63),
  otp_secret varchar(20),
  recovery_email varchar(63) unique,
  account_status account_status not null default 'pending'
  -- todo: node that the user is registered to
);
create unique index auth_users_email on auth_users using btree (email);
create index auth_users_account_status on auth_users using btree (account_status);  -- could be a composite index with email

create table auth_sessions (
  id bigserial primary key,
  auth_user int not null references auth_users on delete cascade,
  started timestamptz not null default current_timestamp,
  last_active timestamptz not null default current_timestamp,
  active boolean default true,  -- todo need a cron job to close expired sessions just so they look sensible
  events jsonb[]
);

-- todo add address book, domains, organisations and teams, perhaps new db/app.
