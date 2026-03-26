#!/usr/bin/env bash
# Run Fathom fetch from repo root so env and _inbox are found. Pass any args (e.g. --date 2026-02-12).
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"
exec python3 _meta/scripts/fathom-fetch-inbox.py "$@"

