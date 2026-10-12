#!/usr/bin/env bash
# Source this file, then call s2_python. It prints the path of the first Python >= 3.11 from:
# python3.12, /opt/homebrew/bin/python3, /usr/local/bin/python3, python3. If none qualifies it
# prints an error to stderr and returns 1. A caller can pin one with S2_PYTHON=/path/to/python.
s2_python() {
  if [[ -n "${S2_PYTHON:-}" ]]; then printf '%s\n' "$S2_PYTHON"; return 0; fi
  local c p
  for c in python3.12 /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
    p="$(command -v "$c" 2>/dev/null)" || continue
    if "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
      printf '%s\n' "$p"; return 0
    fi
  done
  echo "Python 3.11+ required → brew install python@3.12" >&2
  return 1
}
