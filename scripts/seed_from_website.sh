#!/usr/bin/env bash
# Seed the workspace with the published site state from the `website` branch.
#
# CI checks out `main`, whose committed docs/ is a stale snapshot from the old
# systemd runs. Two things must come from the deployed branch instead:
#
#   * docs/data/*   — articles.parquet is the durable article store that
#                     hydrates the ephemeral Postgres; top_news.json and
#                     source_health.json carry forward UI state.
#   * docs/archive/ — the published per-day pages. generate_archive_index()
#                     builds the index by SCANNING this directory, so without
#                     the deployed pages the index silently lists only the
#                     stale months committed to main (observed: the index
#                     stopped at 2026-03-09 while April–July pages were live
#                     on the website branch the whole time).
#
# Best-effort throughout: a missing file or a first-ever run is not an error.
set -uo pipefail

mkdir -p docs/data docs/archive

# Resolve the website branch. actions/checkout configures a single-branch
# fetch refspec, so `git fetch origin website` updates FETCH_HEAD without
# necessarily creating refs/remotes/origin/website — resolve both ways.
WEBSITE_REF=""
if git fetch origin website --depth=1 2>/dev/null; then
  WEBSITE_REF=FETCH_HEAD
fi
if git rev-parse --verify --quiet origin/website >/dev/null 2>&1; then
  WEBSITE_REF=origin/website
fi

if [ -z "$WEBSITE_REF" ]; then
  echo "No website branch yet (first run); nothing to seed"
  exit 0
fi
echo "Seeding from website branch ($(git rev-parse --short "$WEBSITE_REF"))"

# ── Durable data files ────────────────────────────────────────────────────
# The website branch holds these under docs/data/ (current publish path) or
# data/ (older flattened publishes) — try both.
seed_data_file() {
  local name="$1"
  if git show "$WEBSITE_REF:docs/data/$name" > "docs/data/$name" 2>/dev/null; then
    echo "Seeded docs/data/$name"
  elif git show "$WEBSITE_REF:data/$name" > "docs/data/$name" 2>/dev/null; then
    echo "Seeded docs/data/$name (from root data/)"
  else
    rm -f "docs/data/$name"
    echo "No previous docs/data/$name found"
  fi
}

seed_data_file articles.parquet
seed_data_file top_news.json
seed_data_file source_health.json

# ── Published archive pages ───────────────────────────────────────────────
# Restore every deployed day page so the regenerated index covers the full
# history. Checking out over the stale committed copies is intentional: the
# deployed page is always the newer render.
seed_archive_dir() {
  local path="$1"
  if ! git cat-file -e "$WEBSITE_REF:$path" 2>/dev/null; then
    return 1
  fi
  git checkout "$WEBSITE_REF" -- "$path" 2>/dev/null || return 1
  # Older publishes put pages at archive/; normalize onto docs/archive/.
  if [ "$path" != "docs/archive" ] && [ -d "archive" ]; then
    cp -r archive/. docs/archive/ 2>/dev/null || true
  fi
  return 0
}

if seed_archive_dir "docs/archive" || seed_archive_dir "archive"; then
  # The checkout stages files; unstage so the workspace stays clean for any
  # later git operations in the job.
  git reset --quiet -- docs/archive archive 2>/dev/null || true
  echo "Seeded $(find docs/archive -maxdepth 1 -name '20*.html' | wc -l) published archive pages"
else
  echo "No published archive pages found on the website branch"
fi
