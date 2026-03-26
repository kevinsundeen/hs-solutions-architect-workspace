#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Usage: ./scripts/new-client.sh \"Client Name\""
  exit 1
fi

client_name="$1"
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
template_dir="$repo_root/TEMPLATE_CLIENT"
target_dir="$repo_root/$client_name"

if [ -d "$target_dir" ]; then
  echo "Target already exists: $target_dir"
  exit 1
fi

cp -R "$template_dir" "$target_dir"
echo "Created client workspace: $target_dir"
