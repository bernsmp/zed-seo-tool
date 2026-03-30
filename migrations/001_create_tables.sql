-- Run via: wrangler d1 execute tm-studio --file=migrations/001_create_tables.sql

CREATE TABLE IF NOT EXISTS client_profiles (
  slug TEXT PRIMARY KEY,
  profile TEXT NOT NULL,
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  client_slug TEXT NOT NULL REFERENCES client_profiles(slug) ON DELETE CASCADE,
  result_type TEXT NOT NULL,
  data TEXT NOT NULL,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_results_lookup
  ON results (client_slug, result_type, created_at DESC);
