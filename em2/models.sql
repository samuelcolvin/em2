-- includes both local and remote users
create table users (
  id bigserial primary key,
  email varchar(255) not null,
  display_name varchar(127)
);
create unique index user_email on users using btree (email);

create table conversations (
  id bigserial primary key,
  key varchar(64) unique,
  published bool default false,
  creator int not null references users on delete restrict,
  created_ts timestamptz not null default current_timestamp,
  updated_ts timestamptz not null default current_timestamp,
  subject varchar(255) not null,
  last_action_id int not null default 0 check (last_action_id >= 0),
  snippet json
  -- todo expiry, ref?
);
create index conversations_created_ts on conversations using btree (created_ts);

create table participants (
  id bigserial primary key,
  conv int not null references conversations on delete cascade,
  user_id int not null references users on delete restrict,
  -- todo permissions, hidden, status, has_seen/unread
  unique (conv, user_id)
);

-- see core.relationships enum which matches this
create type relationship as enum ('sibling', 'child');
create type msg_format as enum ('markdown', 'plain', 'html');

-- see core.verbs enum which matches this
create type verb as enum ('create', 'publish', 'add', 'modify', 'delete', 'recover', 'lock', 'unlock');
-- see core.components enum which matches this
create type component as enum ('subject', 'expiry', 'label', 'message', 'participant', 'attachment');

create table actions (
  _id bigserial primary key,
  id int not null check (id >= 0),
  conv int not null references conversations on delete cascade,
  verb verb not null,
  component component not null,
  actor int not null references users on delete restrict,
  timestamp timestamptz not null default current_timestamp,

  participant int references participants,

  body text,
  msg int references actions,  -- follows or modifies depending on whether the verb is add or modify
  msg_relationship relationship,
  msg_position int[] default array[1],
  msg_format msg_format,

  -- todo participant details, attachment details, perhaps json for other types

  unique (conv, id)
);
create index action_conv_comp_verb_id on actions using btree (conv, component, verb, id);

-- this could be run on every "migration"
create or replace function action_inserted() returns trigger as $$
  -- could replace all this with plv8
  declare
    -- todo add actor name when we have it, could add attachment count etc. here too
    snippet_ json = json_build_object(
      'comp', new.component,
      'verb', new.verb,
      'email', (select email from users where id=new.actor),
      'body', left(
          case when new.component='message' and new.body is not null then
            new.body
          else
            (select body from actions where conv=new.conv and component='message' order by id desc limit 1)
          end, 100
      ),
      'prts', (select count(*) from participants where conv=new.conv),
      'msgs', (
        select count(*) filter (where verb='add') - count(*) filter (where verb='delete')
        from actions where conv=new.conv and component='message'
      )
    );
  begin
    -- update the conversation timestamp and snippet on new actions
    update conversations set updated_ts=new.timestamp, snippet=snippet_ where id=new.conv;
    return null;
  end;
$$ language plpgsql;

create trigger action_insert after insert on actions for each row execute procedure action_inserted();

-- see core.actionstatuses enum which matches this
create type action_status as enum ('temporary_failure', 'failed', 'successful');

create table action_states (
  action int not null references actions on delete cascade,
  ref varchar(100),
  status action_status not null,
  node varchar(255),  -- null for fallback todo rename to node
  errors jsonb[],
  unique (action, node)
);
create index action_state_ref on action_states using btree (ref);
-- might need index on platform

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

-- todo add domains, organisations and teams, perhaps new db/app.
