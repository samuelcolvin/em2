-- includes both local and remote users
CREATE TABLE users (
  id BIGSERIAL PRIMARY KEY,
  address VARCHAR(255) NOT NULL,
  display_name VARCHAR(127)
);
CREATE UNIQUE INDEX user_address ON users USING btree (address);

CREATE TABLE conversations (
  id BIGSERIAL PRIMARY KEY,
  key VARCHAR(64) UNIQUE,
  published BOOL DEFAULT False,
  creator INT NOT NULL REFERENCES users ON DELETE RESTRICT,
  created_ts TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_ts TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  subject VARCHAR(255) NOT NULL,
  last_action_id INT NOT NULL DEFAULT 0 CHECK (last_action_id >= 0),
  snippet JSON
  -- TODO expiry, ref?
);
CREATE INDEX conversations_created_ts ON conversations USING btree (created_ts);

CREATE TABLE participants (
  id BIGSERIAL PRIMARY KEY,
  conv INT NOT NULL REFERENCES conversations ON DELETE CASCADE,
  user_id INT NOT NULL REFERENCES users ON DELETE RESTRICT,
  -- TODO permissions, hidden, status, has_seen/unread
  UNIQUE (conv, user_id)
);

-- see core.Relationships enum which matches this
CREATE TYPE RELATIONSHIP AS ENUM ('sibling', 'child');
CREATE TYPE MSG_FORMAT AS ENUM ('markdown', 'plain', 'html');

-- see core.Verbs enum which matches this
CREATE TYPE VERB AS ENUM ('create', 'publish', 'add', 'modify', 'delete', 'recover', 'lock', 'unlock');
-- see core.Components enum which matches this
CREATE TYPE COMPONENT AS ENUM ('subject', 'expiry', 'label', 'message', 'participant', 'attachment');

CREATE TABLE actions (
  _id BIGSERIAL PRIMARY KEY,
  id INT NOT NULL CHECK (id >= 0),
  conv INT NOT NULL REFERENCES conversations ON DELETE CASCADE,
  verb VERB NOT NULL,
  component COMPONENT NOT NULL,
  actor INT NOT NULL REFERENCES users ON DELETE RESTRICT,
  timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

  participant INT REFERENCES participants,

  body TEXT,
  msg INT REFERENCES actions,  -- follows or modifies depending on whether the verb is add or modify
  msg_relationship RELATIONSHIP,
  msg_position INT[] DEFAULT ARRAY[1],
  msg_format MSG_FORMAT,

  -- TODO participant details, attachment details, perhaps JSON for other types

  UNIQUE (conv, id)
);
CREATE INDEX action_conv_comp_verb_id ON actions USING btree (conv, component, verb, id);

-- this could be run on every "migration"
CREATE OR REPLACE FUNCTION action_inserted() RETURNS trigger AS $$
  -- could replace all this with plv8
  DECLARE
    -- TODO add actor name when we have it, could add attachment count etc. here too
    snippet_ JSON = json_build_object(
      'comp', NEW.component,
      'verb', NEW.verb,
      'addr', (SELECT address FROM users WHERE id=NEW.actor),
      'body', left(
          CASE WHEN NEW.component='message' AND NEW.body IS NOT NULL THEN
            NEW.body
          ELSE
            (SELECT body FROM actions WHERE conv=NEW.conv and component='message' ORDER BY id DESC LIMIT 1)
          END, 100
      ),
      'prts', (SELECT COUNT(*) FROM participants WHERE conv=NEW.conv),
      'msgs', (
        SELECT COUNT(*) FILTER (WHERE verb='add') - COUNT(*) FILTER (WHERE verb='delete')
        FROM actions WHERE conv=NEW.conv and component='message'
      )
    );
  BEGIN
    -- update the conversation timestamp and snippet on new actions
    UPDATE conversations SET updated_ts=NEW.timestamp, snippet=snippet_ WHERE id=NEW.conv;
    RETURN NULL;
  END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER action_insert AFTER INSERT ON actions FOR EACH ROW EXECUTE PROCEDURE action_inserted();

-- see core.ActionStatuses enum which matches this
CREATE TYPE ACTION_STATUS AS ENUM ('temporary_failure', 'failed', 'successful');

CREATE TABLE action_states (
  action INT NOT NULL REFERENCES actions ON DELETE CASCADE,
  ref VARCHAR(100),
  status ACTION_STATUS NOT NULL,
  node VARCHAR(255),  -- null for fallback TODO rename to node
  errors JSONB[],
  UNIQUE (action, node)
);
CREATE INDEX action_state_ref ON action_states USING btree (ref);
-- might need index on platform

-- TODO attachments


----------------------------------------------------------------------------------
-- Auth tables, currently in the the same database as everything else, but with --
-- no links so could easily be moved to a separate db.                          --
----------------------------------------------------------------------------------
-- TODO table of supported domains/nodes

CREATE TYPE ACCOUNT_STATUS AS ENUM ('pending', 'active', 'suspended');

CREATE TABLE auth_users (
  id BIGSERIAL PRIMARY KEY,
  address VARCHAR(255) NOT NULL UNIQUE,
  first_name VARCHAR(63),
  last_name VARCHAR(63),
  password_hash VARCHAR(63),
  otp_secret VARCHAR(20),
  recovery_address VARCHAR(63) UNIQUE,
  account_status ACCOUNT_STATUS NOT NULL DEFAULT 'pending'
  -- TODO: node that the user is registered to
);
CREATE UNIQUE INDEX auth_users_address ON auth_users USING btree (address);
CREATE INDEX auth_users_account_status ON auth_users USING btree (account_status);  -- could be a composite index with address

CREATE TABLE auth_sessions (
  id BIGSERIAL PRIMARY KEY,
  auth_user INT NOT NULL REFERENCES auth_users ON DELETE CASCADE,
  started TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_active TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  active BOOLEAN DEFAULT TRUE,  -- TODO need a cron job to close expired sessions just so they look sensible
  events JSONB[]
);

-- TODO add domains, organisations and teams, perhaps new db/app.
