-- Phase 0: raw log of bot traffic, deletions and key/value metadata.
-- Timestamps are ISO-8601 strings in UTC.

CREATE TABLE messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id         INTEGER NOT NULL,
    msg_id          INTEGER NOT NULL,
    event           TEXT    NOT NULL CHECK (event IN ('new', 'edit')),
    sender_id       INTEGER,
    is_bot          INTEGER NOT NULL CHECK (is_bot IN (0, 1)),
    is_outgoing     INTEGER NOT NULL CHECK (is_outgoing IN (0, 1)),
    sent_at         TEXT    NOT NULL,
    edited_at       TEXT,
    received_at     TEXT    NOT NULL,
    reply_to_msg_id INTEGER,
    media           TEXT,
    text            TEXT    NOT NULL,
    entities        TEXT    NOT NULL DEFAULT '[]',
    buttons         TEXT    NOT NULL DEFAULT '[]'
);

CREATE INDEX ix_messages_chat_msg ON messages (chat_id, msg_id);
CREATE INDEX ix_messages_received_at ON messages (received_at);

CREATE TABLE deletions (
    chat_id    INTEGER NOT NULL,
    msg_id     INTEGER NOT NULL,
    deleted_at TEXT    NOT NULL,
    PRIMARY KEY (chat_id, msg_id)
);

CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
