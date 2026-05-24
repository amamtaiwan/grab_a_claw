#!/usr/bin/env bash
#
# run-demo.sh — operator-driven equivalent of the desktop-tidy skill.
#
# Mirrors exactly what skills/desktop-tidy/SKILL.md instructs the agent to
# do, but runs straight against the sandbox via `nemoclaw exec` so we can
# get reliable timing for the live demo. The agent's autonomy layer in
# OpenClaw v0.1.0 alpha can't yet invoke SKILL.md-style skills as tools
# (tool_search_code doesn't bridge the skill catalog), so we substitute
# a thin shell wrapper. Every file operation still goes through the
# sandbox, still hits the same Landlock + marker-check gates, and still
# appears in the OCSF audit log.
#
# Usage:
#   ./scripts/run-demo.sh [<sandbox-name>]   # default: hack-agent
#
# Output: a Markdown summary identical in shape to what desktop-tidy
# would have emitted, so the demo narration matches the on-screen text.

set -euo pipefail

SANDBOX="${1:-hack-agent}"
NEMOCLAW="${NEMOCLAW_BIN:-$HOME/.local/bin/nemoclaw}"
DESKTOP=/sandbox/demo/desktop
SORTED=/sandbox/demo/sorted
TRASH=/sandbox/.openclaw/trash
MARKER=/sandbox/.openclaw/trash-approved

# Pretty separators for the live demo's terminal recording.
hr() { printf "\n\033[90m── %s ──\033[0m\n" "$*"; }

hr "1. scan ($DESKTOP)"
INVENTORY=$("$NEMOCLAW" "$SANDBOX" exec --timeout 15 -- \
  bash -c "find $DESKTOP -maxdepth 1 -type f -printf '%f\t%s\t%TY-%Tm-%Td\n'" \
  | tr -d '\r')

if [[ -z "$INVENTORY" ]]; then
  echo "Nothing to tidy — $DESKTOP is empty."
  exit 0
fi
echo "$INVENTORY"

hr "2. plan"
# Classify with the same rules desktop-plan applies. trash-candidate wins
# over media-type rules — same as the SKILL.md says.
declare -a MOVES=()        # "src→dst"
declare -a TRASH_TARGETS=() # "src"
NOW_EPOCH=$(date +%s)
NINETY_D=$((90 * 86400))
while IFS=$'\t' read -r name size mtime; do
  base="$name"
  # trash-candidate rules
  if [[ "$base" == *.tmp || "$base" == *.bak || "$base" == *~ ]]; then
    TRASH_TARGETS+=("$DESKTOP/$base"); continue
  fi
  if [[ "$size" -eq 0 ]]; then
    TRASH_TARGETS+=("$DESKTOP/$base"); continue
  fi
  mtime_epoch=$(date -d "$mtime" +%s 2>/dev/null || echo "$NOW_EPOCH")
  age=$((NOW_EPOCH - mtime_epoch))
  if (( age > NINETY_D )); then
    TRASH_TARGETS+=("$DESKTOP/$base"); continue
  fi
  # Otherwise, classify by extension and route to a sorted/ bucket.
  ext="${base##*.}"
  case "$ext" in
    png|jpg|jpeg|gif|webp|heic|svg)   dst=images ;;
    pdf|doc|docx|odt|txt|md|rtf)      dst=documents ;;
    csv|xlsx|ods)                     dst=documents ;;
    zip|tar|tgz|gz|xz|7z|iso)         dst=archives ;;
    py|js|ts|rs|go|c|cpp|sh)          dst=code ;;
    mp3|mp4|mov|mkv|wav|flac)         dst=media ;;
    *)                                dst="" ;;
  esac
  if [[ -n "$dst" ]]; then
    MOVES+=("$DESKTOP/$base→$SORTED/$dst/$base")
  fi
done <<< "$INVENTORY"

echo "moves: ${#MOVES[@]} | trash: ${#TRASH_TARGETS[@]}"

hr "3. execute moves"
moved_lines=""
for entry in "${MOVES[@]}"; do
  src="${entry%%→*}"
  dst="${entry##*→}"
  if "$NEMOCLAW" "$SANDBOX" exec --timeout 10 -- bash -c "mkdir -p \"$(dirname "$dst")\" && mv \"$src\" \"$dst\"" >/dev/null 2>&1; then
    moved_lines+=$'\n'"  - $(basename "$src") → $(dirname "$dst")/"
  else
    moved_lines+=$'\n'"  - $(basename "$src") → FAILED (policy denied or error)"
  fi
done

hr "4. execute trash requests (gate-aware)"
denied_lines=""
trashed_lines=""
for src in "${TRASH_TARGETS[@]}"; do
  # Honor the marker check — same as the desktop-trash SKILL.md.
  if "$NEMOCLAW" "$SANDBOX" exec --timeout 5 -- bash -c "test -e $MARKER" >/dev/null 2>&1; then
    if "$NEMOCLAW" "$SANDBOX" exec --timeout 10 -- bash -c "mkdir -p $TRASH && mv \"$src\" \"$TRASH/$(basename "$src")\"" >/dev/null 2>&1; then
      trashed_lines+=$'\n'"  - $(basename "$src")"
    else
      denied_lines+=$'\n'"  - $(basename "$src") (mv failed unexpectedly)"
    fi
  else
    denied_lines+=$'\n'"  - $(basename "$src")"
  fi
done

hr "5. summary"
cat <<EOF
## Tidied $DESKTOP — $(echo "$INVENTORY" | wc -l) files reviewed
EOF
if [[ -n "$moved_lines" ]]; then
  printf "\n### ✓ Moved (%d)%s\n" "${#MOVES[@]}" "$moved_lines"
fi
if [[ -n "$trashed_lines" ]]; then
  printf "\n### ✓ Trashed (%d)%s\n" "$(echo "$trashed_lines" | grep -c '^  - ')" "$trashed_lines"
fi
if [[ -n "$denied_lines" ]]; then
  denied_count=$(echo "$denied_lines" | grep -c '^  - ')
  printf "\n### ⚠ Trash denied by policy (%d)\n" "$denied_count"
  echo "The trash gate is closed. To open it, run: ./policies/grant-trash.sh $SANDBOX, then re-run this script."
  printf "%s\n" "$denied_lines"
fi
