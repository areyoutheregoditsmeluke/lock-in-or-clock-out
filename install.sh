#!/usr/bin/env bash
# Installs lioco: symlinks the Hammerspoon module, writes a starter config,
# and installs the two tools it leans on (Hammerspoon, icalBuddy).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HS_DIR="$HOME/.hammerspoon"
CFG_DIR="$HOME/.config/lioco"
CFG="$CFG_DIR/config.json"

if [[ "$(uname)" != "Darwin" ]]; then
  echo "lioco runs on macOS (it needs Hammerspoon)." >&2
  exit 1
fi

if command -v brew >/dev/null 2>&1; then
  if ! [[ -d /Applications/Hammerspoon.app ]]; then
    echo "→ installing Hammerspoon"; brew install --cask hammerspoon
  fi
  if ! command -v icalBuddy >/dev/null 2>&1; then
    echo "→ installing icalBuddy (calendar access)"; brew install ical-buddy
  fi
else
  echo "Homebrew not found. Install Hammerspoon and ical-buddy by hand, then rerun." >&2
fi

mkdir -p "$HS_DIR" "$CFG_DIR" "$HOME/.local/share/lioco"

ln -sfn "$REPO/hammerspoon/lioco" "$HS_DIR/lioco"
echo "→ linked $HS_DIR/lioco"

if ! grep -q 'require("lioco")' "$HS_DIR/init.lua" 2>/dev/null; then
  printf '\nlioco = require("lioco")\n' >> "$HS_DIR/init.lua"
  echo "→ added require(\"lioco\") to $HS_DIR/init.lua"
fi

if [[ ! -f "$CFG" ]]; then
  python3 - "$REPO" "$CFG" <<'PY'
import json, sys, os
repo, cfg = sys.argv[1], sys.argv[2]
with open(os.path.join(repo, "config.example.json")) as f:
    data = json.load(f)
data["brain_path"] = os.path.join(repo, "brain", "lioco.py")
with open(cfg, "w") as f:
    json.dump(data, f, indent=2)
PY
  echo "→ wrote $CFG (edit hours, work_dirs, bear tags to taste)"
else
  echo "→ keeping existing $CFG"
fi

cat <<MSG

Next:
  1. Open Hammerspoon, grant Accessibility (System Settings → Privacy & Security → Accessibility).
  2. If Bear todos do not show up, give Hammerspoon Full Disk Access (it reads Bear's database).
  3. First run of icalBuddy asks for Calendar access. Approve it.
  4. Optional: export LINEAR_API_KEY and SLACK_USER_TOKEN in your login shell, then
     launch Hammerspoon from a terminal once (open -a Hammerspoon) so it inherits them.
  5. Reload Hammerspoon. A colored dot appears in the menubar.

Check everything:  python3 "$REPO/brain/lioco.py" doctor
Test the card:     menubar dot → "Nudge me now (test)"
MSG
