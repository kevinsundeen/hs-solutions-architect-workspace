#!/usr/bin/env bash
# One-command macOS installer for the HubSpot Solutions Architect workspace.
#   curl -fsSL https://raw.githubusercontent.com/kevinsundeen/hs-solutions-architect-workspace/main/install.sh | bash -s -- [--overlay OWNER/REPO]
# Safe to re-run: every step is skipped when already done.
set -euo pipefail

CORE_NAME="hs-solutions-architect-workspace"
CORE_URL="${S2_CORE_URL:-https://github.com/kevinsundeen/hs-solutions-architect-workspace.git}"
CORE_REF="${S2_CORE_REF:-}"
DEFAULT_DIR="~/Documents/GitHub"

OVERLAY=""
DIR=""
OPEN=1

usage() {
  cat <<HELP
Usage: install.sh [--overlay OWNER/REPO] [--dir PATH] [--no-open] [--help]

  --overlay OWNER/REPO  Also clone a private overlay repo (needs a GitHub collaborator invite)
                        and link it into the workspace.
  --dir PATH            Parent folder for the workspace (skips the location prompt).
  --no-open             Do not open VS Code at the end.
  --help                Show this help.

Testing only (environment variables):
  S2_CORE_URL   Clone the core from this URL or local path instead of GitHub.
  S2_CORE_REF   Check out this branch or tag of the core (git clone -b).
HELP
}

say()  { printf '%s\n' "$*"; }
ok()   { printf '✓ %s\n' "$*"; }
step() { printf '→ %s\n' "$*"; }
die()  { printf '✖ %s\n' "$*" >&2; exit 1; }

need_val() { [[ $# -ge 2 && -n "$2" && "$2" != --* ]] || die "$1 needs a value. Run: install.sh --help"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --overlay) need_val "$@"; OVERLAY="$2"; shift 2 ;;
    --dir)     need_val "$@"; DIR="$2"; shift 2 ;;
    --no-open) OPEN=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1. Run: install.sh --help" ;;
  esac
done

[[ "$(uname -s)" == "Darwin" ]] || die "This installer supports macOS only."
if [[ -n "$OVERLAY" && ! "$OVERLAY" =~ ^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$ ]]; then
  die "--overlay must look like OWNER/REPO"
fi

# Under curl | bash, stdin is the script: read prompts from the terminal when there is one.
TTY_OK=0
if { : </dev/tty; } 2>/dev/null; then TTY_OK=1; fi
ask() {  # ask "prompt" -> answer (empty on EOF)
  local ans=""
  if [[ $TTY_OK -eq 1 ]]; then read -r -p "$1" ans </dev/tty || true
  else read -r -p "$1" ans || true; fi
  printf '%s' "$ans"
}

# 0. VS Code first, so nothing is installed for someone who cannot finish.
if [[ ! -d "/Applications/Visual Studio Code.app" ]]; then
  say "Install VS Code from https://code.visualstudio.com first, then re-run"
  exit 1
fi
ok "VS Code"

# a. Xcode Command Line Tools
if xcode-select -p >/dev/null 2>&1; then
  ok "Xcode Command Line Tools"
else
  step "Installing Xcode Command Line Tools"
  xcode-select --install || true
  say "Finish the dialog that just opened, then re-run the same command."
  exit 0
fi

# b. Homebrew
brew_env() {
  if [[ -x /opt/homebrew/bin/brew ]]; then eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [[ -x /usr/local/bin/brew ]]; then eval "$(/usr/local/bin/brew shellenv)"; fi
}
if command -v brew >/dev/null 2>&1; then
  ok "Homebrew"
else
  brew_env
  if command -v brew >/dev/null 2>&1; then
    ok "Homebrew (found; not on PATH in new shells until ~/.zprofile is set)"
  else
    step "Installing Homebrew (it asks for your Mac password)"
    if [[ $TTY_OK -eq 1 ]]; then
      /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" </dev/tty
    else
      /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
    brew_env
    command -v brew >/dev/null 2>&1 || die "Homebrew installed but brew was not found. Open a new Terminal and re-run."
  fi
  if [[ -x /opt/homebrew/bin/brew ]]; then LINE='eval "$(/opt/homebrew/bin/brew shellenv)"'
  else LINE='eval "$(/usr/local/bin/brew shellenv)"'; fi
  if ! grep -qsF "$LINE" "$HOME/.zprofile"; then
    printf '%s\n' "$LINE" >> "$HOME/.zprofile"
    ok "Added Homebrew to ~/.zprofile"
  fi
fi

# c. brew packages (skip each one that is already available)
have_pkg() {
  case "$1" in
    python@3.12) command -v python3.12 >/dev/null 2>&1 || brew list --formula python@3.12 >/dev/null 2>&1 ;;
    *) command -v "$1" >/dev/null 2>&1 || brew list --formula "$1" >/dev/null 2>&1 ;;
  esac
}
for pkg in python@3.12 node gh; do
  if have_pkg "$pkg"; then ok "$pkg"
  else step "brew install $pkg"; brew install "$pkg"; fi
done

# d. Claude Code
if command -v claude >/dev/null 2>&1; then
  ok "Claude Code"
else
  step "Installing Claude Code"
  npm install -g @anthropic-ai/claude-code
fi

# Location
if [[ -z "$DIR" ]]; then
  DIR="$(ask "Where should the workspace live? [$DEFAULT_DIR] ")"
  DIR="${DIR:-$DEFAULT_DIR}"
fi
case "$DIR" in "~") DIR="$HOME" ;; "~/"*) DIR="$HOME/${DIR#"~/"}" ;; esac
mkdir -p "$DIR"
DIR="$(cd "$DIR" && pwd)"
ok "Workspace folder: $DIR"

# clone_or_pull <label> <url> <dest> [ref]; returns 0 ok, 1 clone failed, exits on a conflicting path
sync_repo() {
  local label="$1" url="$2" dest="$3" ref="${4:-}"
  if [[ -e "$dest" ]]; then
    if [[ -d "$dest/.git" ]]; then
      local origin; origin="$(git -C "$dest" remote get-url origin 2>/dev/null || true)"
      origin="${origin%.git}"
      if [[ "$origin" == "${url%.git}" || "$(basename "$origin")" == "$(basename "${url%.git}")" ]]; then
        step "Updating $label"
        git -C "$dest" pull --ff-only
        return 0
      fi
    fi
    die "$dest already exists and is not a checkout of $label. Move it or pick another --dir."
  fi
  step "Cloning $label"
  if [[ -n "$ref" ]]; then git clone -b "$ref" "$url" "$dest"; else git clone "$url" "$dest"; fi
}

CORE="$DIR/$CORE_NAME"
sync_repo "the workspace" "$CORE_URL" "$CORE" "$CORE_REF"
ok "Workspace ready: $CORE"

OVERLAY_ARGS=()
if [[ -n "$OVERLAY" ]]; then
  ONAME="${OVERLAY#*/}"
  if ! gh auth status >/dev/null 2>&1; then
    step "Logging in to GitHub (follow the prompts in your browser)"
    if [[ $TTY_OK -eq 1 ]]; then
      gh auth login --web --git-protocol https -h github.com </dev/tty || true
    else
      gh auth login --web --git-protocol https -h github.com || true
    fi
    gh auth setup-git || true
  fi
  ODEST="$DIR/$ONAME"
  if [[ -d "$ODEST/.git" ]]; then
    sync_repo "overlay $OVERLAY" "https://github.com/$OVERLAY.git" "$ODEST"
    OVERLAY_ARGS=(--overlay "../$ONAME")
  elif [[ -e "$ODEST" ]]; then
    die "$ODEST already exists and is not a git checkout. Move it or pick another --dir."
  elif gh repo clone "$OVERLAY" "$ODEST"; then
    OVERLAY_ARGS=(--overlay "../$ONAME")
  else
    say "No access to $OVERLAY yet. Ask its owner for a GitHub collaborator invite, accept it, then re-run this command"
    say "Continuing with the core workspace only."
  fi
fi

# Setup
step "Running bin/s2 setup"
cd "$CORE"
if [[ $TTY_OK -eq 1 ]]; then
  bin/s2 setup ${OVERLAY_ARGS[@]+"${OVERLAY_ARGS[@]}"} </dev/tty
else
  bin/s2 setup ${OVERLAY_ARGS[@]+"${OVERLAY_ARGS[@]}"}
fi

if [[ $OPEN -eq 1 ]]; then
  open -a "Visual Studio Code" "$CORE/s2.code-workspace" "$CORE/ONBOARDING.md" || true
fi

cat <<NEXT

Next
  1. Read $CORE/ONBOARDING.md (open in VS Code).
  2. Open a Terminal in that folder and run: claude   (log in once when it asks)
  3. Create your first client: bin/s2 new client <Name>
NEXT
