create extension pg_trgm;

create type UserTypes as enum ('new', 'local', 'remote_em2', 'remote_other');
create type ProfileTypes as enum ('personal', 'work', 'organisation');
create type ProfileVisibility as enum ('private', 'public', 'public-searchable');
create type ProfileStatus as enum ('active', 'away', 'dormant');

-- includes both local and remote users, TODO somehow record unsubscribed when people repeatedly complain
create table users (
  id bigserial primary key,
  user_type UserTypes not null default 'new',
  email varchar(255) not null unique,
  v bigint default 1,  -- null for remote users, set thus when the local check returns false
  update_ts timestamptz,
  visibility ProfileVisibility,
  profile_type ProfileTypes,
  main_name varchar(63),
  last_name varchar(63),
  strap_line varchar(127),  -- organisation, titles, industry or legal name
  image_url varchar(2047),
  profile_status ProfileStatus,
  profile_status_message varchar(511),
  body text,
  vector tsvector
);
create index idx_user_visibility on users using btree (visibility);
create index idx_user_type on users using btree (user_type);
-- for looking up partial email address
create index idx_user_email_trgm on users using gin (email gin_trgm_ops);

create table labels (
  id bigserial primary key,
  user_id bigint not null references users on delete cascade,
  -- TODO add team and make either team or user but not both required
  name varchar(255),
  ordering float not null default 0,
  description varchar(1027),
  color varchar(31)
);
create index idx_labels_user_id on labels using btree (user_id);
create index idx_labels_ordering on labels using btree (ordering);

create or replace function remove_labels_on_delete() returns trigger as $$
  begin
    update participants
    set label_ids = array_remove(label_ids, old.id)
    where user_id=old.user_id and label_ids @> array[old.id];
    return null;
  end;
$$ language plpgsql;

create trigger remove_labels after delete on labels for each row execute procedure remove_labels_on_delete();

create table conversations (
  id bigserial primary key,
  key varchar(64) unique,
  creator bigint not null references users on delete restrict,
  created_ts timestamptz not null,
  updated_ts timestamptz not null,
  publish_ts timestamptz,
  last_action_id int not null default 0 check (last_action_id >= 0),
  leader_node varchar (255),  -- null when this node is leader,
  live bool not null,  -- used when conversations are created but not yet ready to be read, also perhaps for deletion
  details json
);
create index idx_conversations_key on conversations using btree (key);
create index idx_conversations_creator on conversations using btree (creator);
create index idx_conversations_created_ts on conversations using btree (created_ts);
create index idx_conversations_updated_ts on conversations using btree (updated_ts);
create index idx_conversations_publish_ts on conversations using btree (publish_ts);
create index idx_conversations_leader_node on conversations using btree (leader_node);
-- for looking up conversations by key prefix
create index idx_conversations_key_trgm on conversations using gin (key gin_trgm_ops);

create table participants (
  id bigserial primary key,
  conv bigint not null references conversations on delete cascade,
  user_id bigint not null references users on delete restrict,
  removal_action_id int,
  removal_updated_ts timestamptz,
  removal_details json,
  seen boolean,
  inbox boolean default true,
  deleted boolean,
  deleted_ts timestamptz,
  spam boolean,
  -- TODO maybe cache sent and draft here for simpler queries
  label_ids bigint[],
  -- todo permissions, hidden
  unique (conv, user_id)  -- like normal composite index can be used to scan on conv but not user_id
);
create index idx_participants_user_removal_action on participants using btree (user_id, removal_action_id);
create index idx_participants_user_seen on participants using btree (user_id, seen);
create index idx_participants_user_inbox on participants using btree (user_id, inbox);
create index idx_participants_user_deleted on participants using btree (user_id, deleted);
create index idx_participants_user_spam on participants using btree (user_id, spam);
create index idx_participants_conv on participants using btree (conv);
create index idx_participants_deleted_ts on participants using btree (deleted_ts);
create index idx_participants_label_ids on participants using gin (label_ids);

-- see core.ActionTypes enum which matches this
create type ActionTypes as enum (
  'conv:publish', 'conv:create',
  'subject:modify', 'subject:lock', 'subject:release',
  'seen',
  'expiry:modify',
  'message:add', 'message:modify', 'message:delete', 'message:recover', 'message:lock', 'message:release',
  'participant:add', 'participant:remove', 'participant:modify'
);
-- see core.MsgFormat enum which matches this
create type MsgFormat as enum ('markdown', 'plain', 'html');

create table actions (
  pk bigserial primary key,
  id int not null check (id >= 0),
  conv bigint not null references conversations on delete cascade,
  act ActionTypes not null,
  actor bigint not null references users on delete restrict,
  ts timestamptz not null default current_timestamp,

  follows bigint references actions,  -- when modifying/deleting etc. a component
  participant_user bigint references users on delete restrict,
  body text,
  preview text,
   -- used for child message "comments", the thing seen, could also be used on message updates?
  parent bigint references actions,
  msg_format MsgFormat,

  -- user display of spam, virus, phishing, dkim failed etc.
  warnings json,

  -- todo participant details, attachment details, perhaps json for other types
  -- could have json lump summarising files to improve performance

  unique (conv, id),
  -- only one action can follow a given action: where follows is required, a linear direct time line is enforced
  unique (conv, follows)
);
create index idx_action_id on actions using btree (id);
create index idx_action_act_id on actions using btree (conv, act, id);
create index idx_action_conv_parent on actions using btree (conv, parent);

-- { action-insert
create or replace function action_insert() returns trigger as $$
  -- could replace all this with plv8
  declare
    -- todo add actor name when we have it, could add attachment count etc. here too
    old_details_ json;
    creator_ varchar(255);
    details_ json;
    new_id_ int;
    subject_ats ActionTypes[] = array['conv:publish', 'conv:create', 'subject:modify'];
    add_del_msg_ats ActionTypes[] = array['message:add', 'message:delete'];
    meta_ats ActionTypes[] = array['seen','subject:release','subject:lock','message:lock','message:release'];
  begin
    if new.act=any(meta_ats) then
      update conversations
        set last_action_id=case when new.id is null then last_action_id + 1 else new.id end
        where id=new.conv
        returning last_action_id into new_id_;
    else
      select details, u.email into old_details_, creator_
      from conversations c
      join users u on u.id = c.creator
      where c.id=new.conv;

      details_ := json_build_object(
        'act', new.act,
        'sub', case when new.act=any(subject_ats) then new.body else old_details_->>'sub' end,
        'email', (select email from users where id=new.actor),
        'creator', creator_,
        'prev', left(coalesce(new.preview, old_details_->>'prev'), 140),
        'prts', (select count(*) from participants where conv=new.conv),
        'msgs', (
          select count(*) filter (where act='message:add') - count(*) filter (where act='message:delete')
          from actions where conv=new.conv and act=any(add_del_msg_ats)
        ) + case new.act when 'message:add' then 1
                         when 'message:delete' then -1
                         else 0 end
      );
      update conversations
        set updated_ts=new.ts, details=details_,
            last_action_id=case when new.id is null then last_action_id + 1 else new.id end
        where id=new.conv
        returning last_action_id into new_id_;
    end if;

    if new.id is null then
      new.id := new_id_;
    end if;

    return new;
  end;
$$ language plpgsql;
-- } action-insert

create trigger action_insert before insert on actions for each row execute procedure action_insert();

create table sends (
  id bigserial primary key,
  action bigint not null references actions,
  outbound boolean not null default false,
  node varchar(255),  -- null for smtp
  ref varchar(500),
  complete boolean not null default false,
  storage varchar(100),
  unique (action, node),
  unique (action, ref)
);
create index idx_sends_ref on sends using btree (outbound, node, ref);

create table send_events (
  id bigserial primary key,
  send bigint not null references sends,
  status varchar(100),
  ts timestamptz not null default current_timestamp,
  user_ids int[],
  extra json
);
create index idx_send_events_send on send_events using btree (send);
create index idx_send_events_user_ids on send_events using gin (user_ids);

create type ContentDisposition as enum ('attachment', 'inline');

create table files (
  id bigserial primary key,
  conv bigint not null references conversations on delete cascade,
  action bigint not null references actions on delete cascade,
  send bigint references sends,
  storage varchar(255),
  storage_expires timestamptz,
  content_disp ContentDisposition not null,
  hash varchar(65) not null,
  content_id varchar(255) not null,
  name varchar(1023),
  content_type varchar(63),
  -- URL used for original download
  download_url varchar(2047),
  error varchar(63),
  size bigint,
  unique (conv, content_id)
);
create index idx_files_action on files using btree (action);

create table image_cache (
  id bigserial primary key,
  conv bigint not null references conversations on delete restrict,
  action bigint not null references actions,
  storage varchar(255),
  error varchar(63),
  created timestamptz not null default current_timestamp,
  last_access timestamptz,

  url varchar(2047) not null,
  hash varchar(65),
  size int,
  content_type varchar(63),
  unique (url, conv)
);
create index idx_image_cache_created on image_cache using btree (created);

-------------------------------------------------------------------------
-- contacts                                                            --
-------------------------------------------------------------------------

create table contacts (
  id bigserial primary key,
  owner bigint not null references users,
  profile_user bigint not null references users,
  profile_type ProfileTypes,
  main_name varchar(63),
  last_name varchar(63),
  strap_line varchar(127),  -- organisation, titles, industry or legal name
  image_url varchar(2047),
  profile_status ProfileStatus,
  profile_status_message varchar(511),
  -- TODO search index
  body text,
  vector tsvector,
  unique (owner, profile_user)
);

-------------------------------------------------------------------------
-- search table, this references conversations so must be the same db, --
-- other search solutions would need to record conv details and key    --
-- in search entries.                                                  --
-------------------------------------------------------------------------
create table search (
  id bigserial primary key,
  conv bigint references conversations,
  action int not null,
  freeze_action int not null default 0,
  user_ids bigint[] not null,
  ts timestamptz,

  -- might need other things like size, files, participants
  creator_email varchar(255) not null,
  vector tsvector,
  unique (conv, freeze_action)
);
create index idx_search_conv on search using btree (conv);
create index idx_search_action on search using btree (conv, action);
create index idx_search_user_ids on search using gin (user_ids);
create index idx_search_ts on search using btree (ts);
create index idx_search_creator_email on search using gin (creator_email gin_trgm_ops);
create index idx_search_vector on search using gin (vector);

----------------------------------------------------------------------------------
-- auth tables, currently in the the same database as everything else, but with --
-- no links so could easily be moved to a separate db.                          --
----------------------------------------------------------------------------------
-- todo table of supported domains/nodes

create type AccountStatuses as enum ('pending', 'active', 'suspended');

create table auth_users (
  id bigserial primary key,
  email varchar(255) not null unique,
  first_name varchar(63),
  last_name varchar(63),
  password_hash varchar(63),
  otp_secret varchar(20),
  recovery_email varchar(63) unique,
  account_status AccountStatuses not null default 'pending'
  -- todo: node that the user is registered to
);
-- could be a composite index with email:
create index idx_auth_users_account_status on auth_users using btree (account_status);

create table auth_sessions (
  id bigserial primary key,
  user_id bigint not null references auth_users on delete cascade,
  started timestamptz not null default current_timestamp,
  last_active timestamptz not null default current_timestamp,
  active boolean default true  -- todo need a cron job to close expired sessions just so they look sensible
);
create index idx_auth_sessions_user_id on auth_sessions using btree (user_id);
create index idx_auth_sessions_active on auth_sessions using btree (active, last_active);

create type SessionEventTypes as enum ('login-pw', 'update', 'logout', 'expired', 'expired-hard');

create table auth_user_agents (
  id bigserial primary key,
  value varchar(255) not null unique,
  _dummy bool -- just used for "on conflict (value) do update set _dummy=null"
);

create table auth_session_events (
  id bigserial primary key,
  session bigint not null references auth_sessions on delete cascade,
  ts timestamptz not null default current_timestamp,
  action SessionEventTypes not null,
  user_agent bigint not null references auth_user_agents on delete restrict,
  ip inet not null
);
create index idx_auth_session_event_session on auth_session_events using btree (session);

-- todo add domains, organisations and teams, perhaps new db/app.

create or replace function or_now(v timestamptz) returns timestamptz as $$
  begin
    return coalesce(v, now());
  end;
$$ language plpgsql;
