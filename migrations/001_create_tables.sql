-- Run this in Supabase SQL Editor to set up persistence tables.

create table if not exists client_profiles (
  slug text primary key,
  profile jsonb not null,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists results (
  id bigint generated always as identity primary key,
  client_slug text not null references client_profiles(slug) on delete cascade,
  result_type text not null,  -- 'cleaning' or 'mapping'
  data jsonb not null,
  created_at timestamptz default now()
);

-- Index for fast latest-result lookups
create index if not exists idx_results_lookup
  on results (client_slug, result_type, created_at desc);
