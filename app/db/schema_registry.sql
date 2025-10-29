-- Global registry database schema
-- Tracks users and discovered libraries

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- Users table (single admin for MVP)
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'admin',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_login_at TEXT
);

-- Libraries registry
CREATE TABLE IF NOT EXISTS libraries (
  id TEXT PRIMARY KEY,  -- UUID from library.json
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  type TEXT NOT NULL,  -- photo_video, documents, music
  path TEXT NOT NULL,  -- absolute path to library directory
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_scanned_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_libraries_slug ON libraries(slug);
CREATE INDEX IF NOT EXISTS idx_libraries_type ON libraries(type);

