-- TODO add domains, organisations and teams, perhaps new db/app.

-- recipients includes both local and remote users
CREATE TABLE recipients (
  id SERIAL PRIMARY KEY,
  address VARCHAR(255) NOT NULL UNIQUE
  -- TODO perhaps display name
);

CREATE TABLE conversations (
  id SERIAL PRIMARY KEY,
  key VARCHAR(64) UNIQUE,
  published BOOL DEFAULT False,
  creator INT NOT NULL REFERENCES recipients ON DELETE RESTRICT,
  created_ts TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_ts TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  subject VARCHAR(255) NOT NULL,
  snippet JSONB
  -- TODO expiry, ref?
);

CREATE TABLE participants (
  id SERIAL PRIMARY KEY,
  conv INT NOT NULL REFERENCES conversations ON DELETE CASCADE,
  recipient INT NOT NULL REFERENCES recipients ON DELETE RESTRICT,
  -- TODO permissions, hidden, status, has_seen/unread
  UNIQUE (conv, recipient)
);

-- see core.Relationships enum which matches this
CREATE TYPE RELATIONSHIP AS ENUM ('sibling', 'child');
CREATE TYPE MSG_FORMAT AS ENUM ('markdown', 'plain', 'html');

CREATE TABLE messages (
  id SERIAL PRIMARY KEY,
  key CHAR(20) NOT NULL,
  conv INT NOT NULL REFERENCES conversations ON DELETE CASCADE,
  after INT REFERENCES messages,
  relationship RELATIONSHIP,
  position INT[] NOT NULL DEFAULT ARRAY[1],
  deleted BOOLEAN DEFAULT FALSE,
  body TEXT,
  format MSG_FORMAT NOT NULL DEFAULT 'markdown',
  UNIQUE (conv, key)
);
CREATE INDEX message_key ON messages USING btree (key);

-- see core.Verbs enum which matches this
CREATE TYPE VERB AS ENUM ('create', 'publish', 'add', 'modify', 'delete', 'recover', 'lock', 'unlock');
-- see core.Components enum which matches this
CREATE TYPE COMPONENT AS ENUM ('subject', 'expiry', 'label', 'message', 'participant', 'attachment');

CREATE TABLE actions (
  id SERIAL PRIMARY KEY,
  key CHAR(20) NOT NULL,
  conv INT NOT NULL REFERENCES conversations ON DELETE CASCADE,
  verb VERB NOT NULL,
  component COMPONENT,
  actor INT NOT NULL REFERENCES recipients ON DELETE RESTRICT,
  timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  parent INT REFERENCES actions,

  recipient INT REFERENCES recipients,
  message INT REFERENCES messages,

  body TEXT,
  UNIQUE (conv, key)
);
CREATE INDEX action_key ON actions USING btree (key);

-- this could be run on every "migration"
CREATE OR REPLACE FUNCTION action_inserted() RETURNS trigger AS $$
  -- could replace all this with plv8
  DECLARE
    -- TODO add actor name when we have it, could add attachment count etc. here too
    snippet_ JSONB = json_build_object(
      'comp', NEW.component,
      'verb', NEW.verb,
      'addr', (SELECT address FROM recipients WHERE id=NEW.actor),
      'body', left(
          CASE WHEN NEW.component='message' AND NEW.body IS NOT NULL THEN
            NEW.body
          ELSE
            (SELECT body FROM messages WHERE conv=NEW.conv ORDER BY id DESC LIMIT 1)
          END, 100
      ),
      'prts', (SELECT COUNT(*) FROM participants WHERE conv=NEW.conv),
      'msgs', (SELECT COUNT(*) FROM messages WHERE conv=NEW.conv)
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
-- no links so could go in a separate db.                                       --
----------------------------------------------------------------------------------
-- TODO table of supported domains

CREATE TYPE ACCOUNT_STATUS AS ENUM ('pending', 'active', 'suspended');

CREATE TABLE auth_users (
  id SERIAL PRIMARY KEY,
  address VARCHAR(255) NOT NULL UNIQUE,
  first_name VARCHAR(63),
  last_name VARCHAR(63),
  password_hash VARCHAR(63),
  otp_secret VARCHAR(20),
  recovery_address VARCHAR(63) UNIQUE,
  account_status ACCOUNT_STATUS NOT NULL DEFAULT 'pending'
);
CREATE INDEX user_address ON auth_users USING btree (address);

CREATE TABLE auth_sessions (
  id SERIAL PRIMARY KEY,
  auth_user INT NOT NULL REFERENCES auth_users ON DELETE CASCADE,
  started TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_active TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  active BOOLEAN DEFAULT TRUE,  -- TODO need a cron job to close expired sessions just so they look sensible
  events JSONB[]
);
