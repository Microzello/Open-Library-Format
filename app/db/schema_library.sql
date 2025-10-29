-- Per-library database schema
-- Content-addressed file storage with tags and FTS

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- Schema versioning and metadata
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', '1');

-- Files table: one row per unique content blob
CREATE TABLE IF NOT EXISTS files (
  id INTEGER PRIMARY KEY,
  sha256 TEXT NOT NULL UNIQUE,
  size INTEGER NOT NULL,
  ext TEXT,
  mime TEXT,
  original_name TEXT NOT NULL,
  added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  captured_at TEXT,  -- EXIF date/time or NULL (stored as UTC)
  deleted_at TEXT,   -- NULL if active, timestamp if in trash
  notes TEXT         -- user notes
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_files_captured_at ON files(captured_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_files_deleted_at ON files(deleted_at);
CREATE INDEX IF NOT EXISTS idx_files_added_at ON files(added_at DESC);

-- Tags table (collections/albums are tags too)
CREATE TABLE IF NOT EXISTS tags (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_tags_name ON tags(name);

-- File-tag mapping (many-to-many)
CREATE TABLE IF NOT EXISTS file_tags (
  file_id INTEGER NOT NULL,
  tag_id INTEGER NOT NULL,
  added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(file_id, tag_id),
  FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE,
  FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_file_tags_tag ON file_tags(tag_id);

-- Attributes: sparse key-value pairs per file
CREATE TABLE IF NOT EXISTS attributes (
  file_id INTEGER NOT NULL,
  key TEXT NOT NULL,
  value TEXT,
  PRIMARY KEY(file_id, key),
  FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_attributes_key ON attributes(key);

-- Full-text search (external content FTS5)
CREATE VIRTUAL TABLE IF NOT EXISTS file_fts USING fts5(
  title,
  notes,
  content=''
);

-- FTS maintenance triggers
CREATE TRIGGER IF NOT EXISTS files_ai AFTER INSERT ON files BEGIN
  INSERT INTO file_fts(rowid, title, notes)
  VALUES (new.id, COALESCE(new.original_name, ''), COALESCE(new.notes, ''));
END;

CREATE TRIGGER IF NOT EXISTS files_au AFTER UPDATE OF original_name, notes ON files BEGIN
  INSERT INTO file_fts(file_fts, rowid, title, notes)
  VALUES('delete', old.id, '', '');
  INSERT INTO file_fts(rowid, title, notes)
  VALUES (new.id, COALESCE(new.original_name, ''), COALESCE(new.notes, ''));
END;

CREATE TRIGGER IF NOT EXISTS files_ad AFTER DELETE ON files BEGIN
  INSERT INTO file_fts(file_fts, rowid, title, notes)
  VALUES('delete', old.id, '', '');
END;

