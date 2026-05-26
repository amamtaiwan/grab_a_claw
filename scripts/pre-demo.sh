#!/usr/bin/env bash
#
# pre-demo.sh — 60-second pre-flight before a live grab_a_claw demo.
#
# Run this in the operator terminal immediately before pitching. It:
#   1. Replants the demo desktop into a known state (7 files, mixed types
#      and ages so the trash-candidate rule fires on 4 of them).
#   2. Cleans sorted/* and .openclaw/trash/ so the demo starts empty.
#   3. Revokes the trash-writable preset and removes the marker so the
#      gate visual starts CLOSED (red).
#   4. Warms up Ollama by running a single PONG against the configured
#      model — this guarantees the model is hot in VRAM so the first
#      dashboard chat doesn't pay a 30–60s cold load.
#   5. Prints the dashboard URL with a fresh gateway token, the model
#      currently routed, and a concise operator cheat-sheet.
#
# Usage:
#   ./scripts/pre-demo.sh [<sandbox-name>]    # default: hack-agent

set -uo pipefail

SANDBOX="${1:-hack-agent}"
NEMOCLAW="${NEMOCLAW_BIN:-$HOME/.local/bin/nemoclaw}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

hr() { printf "\n\033[36m── %s ──\033[0m\n" "$*"; }
warn() { printf "\033[33m! %s\033[0m\n" "$*"; }
ok() { printf "\033[32m✓ %s\033[0m\n" "$*"; }

HOST_DESKTOP="$HOME/Desktop"
DEMO_FILES=(screenshot_2026-05-20.png old_disk.iso draft.pdf temp_notes.tmp tax_receipts_2024.zip random.log empty_file.txt)
HOST_DESTS=("$HOME/Pictures" "$HOME/Documents" "$HOME/Downloads" "$HOME/Videos" "$HOME/Documents/code")
STASH_ROOT="$HOME/.grab_a_claw-stash"
STASH_DIR="$STASH_ROOT/$(date +%Y%m%d-%H%M%S)"
STASH_POINTER="$HOME/.grab_a_claw-last-stash"
POSITIONS_FILE="/tmp/grab_a_claw-positions.json"

hr "0_pre. wipe sandbox-internal state from previous takes (intents, denied list)"
SBX_CONTAINER=$(docker ps --filter "name=openshell-$SANDBOX" --format '{{.Names}}' | head -1)
if [ -n "$SBX_CONTAINER" ]; then
  docker exec --user sandbox "$SBX_CONTAINER" bash -c 'mkdir -p /sandbox/.openclaw/state; rm -f /sandbox/.openclaw/state/desktop-intents.jsonl /sandbox/.openclaw/state/last-tidy-denied.txt /sandbox/.openclaw/state/desktop-files.txt; touch /sandbox/.openclaw/state/desktop-intents.jsonl' 2>/dev/null || true
  ok "sandbox state cleared"
else
  warn "no sandbox container yet; state wipe skipped"
fi

hr "0a. clean up any leftover demo files from previous takes"
# Removes demo-file NAMES (only the ones we plant) from each destination
# we mirror into. We never touch any of the user's real files.
for dest in "${HOST_DESTS[@]}"; do
  [ -d "$dest" ] || continue
  for name in "${DEMO_FILES[@]}"; do
    [ -f "$dest/$name" ] && rm -f "$dest/$name" && echo "  rm $dest/$name"
  done
done
# Also clear any leftover demo files at the desktop top level (from a
# previous run that didn't post-demo cleanly).
for name in "${DEMO_FILES[@]}"; do
  [ -f "$HOST_DESKTOP/$name" ] && rm -f "$HOST_DESKTOP/$name" && echo "  rm $HOST_DESKTOP/$name"
done
ok "host destinations swept"

hr "0b. stash existing top-level desktop files (run post-demo.sh to restore)"
# Only move regular files at the top level of ~/Desktop. Subfolders
# (including ~/Desktop/grab_a_claw-demo if it exists from old takes) are
# left alone. Symlinks count as files — we stash them too. NOTHING
# touches subfolders.
mkdir -p "$STASH_DIR"
stashed=0
for f in "$HOST_DESKTOP"/*; do
  [ -e "$f" ] || continue
  if [ -d "$f" ] && [ ! -L "$f" ]; then
    continue  # leave subfolders in place
  fi
  mv "$f" "$STASH_DIR/" 2>/dev/null && stashed=$((stashed + 1))
done
echo "$STASH_DIR" > "$STASH_POINTER"
ok "stashed $stashed item(s) to $STASH_DIR"

hr "0c. plant 7 demo files directly on ~/Desktop with explicit ding positions"
SCREEN_W=$(xdpyinfo 2>/dev/null | awk '/dimensions:/{print $2}' | cut -dx -f1)
[ -z "$SCREEN_W" ] && SCREEN_W=1920
SCREEN_H=$(xdpyinfo 2>/dev/null | awk '/dimensions:/{print $2}' | cut -dx -f2)
[ -z "$SCREEN_H" ] && SCREEN_H=1080
# Layout: a horizontal row of 7 icons near the top of the desktop, leaving
# the lower 2/3 clear for the lobster to walk in.
ICON_ROW_Y=180
SIDE_MARGIN=180
USABLE_W=$((SCREEN_W - 2 * SIDE_MARGIN))
N=${#DEMO_FILES[@]}
SPACING=$((USABLE_W / (N - 1)))

echo "[" > "$POSITIONS_FILE"
sep=""
for i in "${!DEMO_FILES[@]}"; do
  name="${DEMO_FILES[$i]}"
  target="$HOST_DESKTOP/$name"
  touch "$target"
  icon_x=$((SIDE_MARGIN + i * SPACING))
  case "$name" in
    screenshot_2026-05-20.png) head -c 1024   /dev/urandom > "$target" ;;
    old_disk.iso)              head -c 524288 /dev/urandom > "$target"; touch -d "2024-01-15" "$target" ;;
    draft.pdf)                 head -c 4096   /dev/urandom > "$target" ;;
    temp_notes.tmp)            head -c 200    /dev/urandom > "$target" ;;
    tax_receipts_2024.zip)     head -c 8192   /dev/urandom > "$target" ;;
    random.log)                touch -d "2023-12-01" "$target" ;;
  esac
  # Both the legacy nautilus key and the newer ding key — set both for
  # belt-and-braces compatibility with ding versions in the wild.
  gio set "$target" metadata::nautilus-icon-position "${icon_x},${ICON_ROW_Y}"      2>/dev/null || true
  gio set "$target" metadata::desktopfile-icon-position "${icon_x},${ICON_ROW_Y}"   2>/dev/null || true
  printf '%s  {"name": "%s", "screen_x": %s, "screen_y": %s}\n' "$sep" "$name" "$icon_x" "$ICON_ROW_Y" >> "$POSITIONS_FILE"
  sep=","
done
echo "]" >> "$POSITIONS_FILE"
ok "planted $N demo files; positions written to $POSITIONS_FILE"
echo "   (right-click desktop → Refresh / press F5 if icons don't appear immediately)"

# Also publish the desktop file list inside the sandbox so the
# desktop-arrange agent can read it (it cannot ls the host directly).
if [ -n "$SBX_CONTAINER" ]; then
  printf '%s\n' "${DEMO_FILES[@]}" | docker exec --user sandbox -i "$SBX_CONTAINER" \
    bash -c 'cat > /sandbox/.openclaw/state/desktop-files.txt' 2>/dev/null || true
fi

hr "0d. create 5 sorted folders on ~/Desktop with explicit ding positions"
# Sibling folders ON the desktop so the audience sees both the original
# files AND the destination folders at once. Lobster walks file→folder
# and the host mv moves the real file inside (visible by double-clicking
# the folder).
declare -A FOLDER_POS=(
  [Images]="200,420"
  [Documents]="550,420"
  [Archives]="900,420"
  [Code]="1250,420"
  [Media]="1600,420"
)
for folder in "${!FOLDER_POS[@]}"; do
  path="$HOST_DESKTOP/$folder"
  # Wipe + recreate so positions get re-set fresh each run.
  rm -rf "$path" 2>/dev/null
  mkdir -p "$path"
  pos="${FOLDER_POS[$folder]}"
  gio set "$path" metadata::nautilus-icon-position "$pos" 2>/dev/null || true
  gio set "$path" metadata::desktopfile-icon-position "$pos" 2>/dev/null || true
done
ok "created Images/Documents/Archives/Code/Media folders at row y=420"

# Pre-create dest dirs we still mirror to (kept for legacy/audit; not
# the demo's visible destinations any more).
for dest in "${HOST_DESTS[@]}"; do
  mkdir -p "$dest"
done

hr "0c. deploy sandbox-internal tidy.sh (read by desktop-tidy skill)"
"$NEMOCLAW" "$SANDBOX" exec --timeout 15 -- bash -c 'mkdir -p /sandbox/.openclaw/bin'
CONTAINER=$(docker ps --filter "name=openshell-$SANDBOX" --format '{{.Names}}' | head -1)
if [ -z "$CONTAINER" ]; then
  warn "docker access missing or sandbox container not found; tidy.sh deploy skipped"
else
  docker cp "$REPO_DIR/sandbox-bin/tidy.sh" "$CONTAINER":/sandbox/.openclaw/bin/tidy.sh
  # docker cp preserves source perms (we chmod +x on the host file in repo),
  # and chown to sandbox so subsequent runs by the sandbox user have nothing
  # to argue about.
  docker exec --user 0 "$CONTAINER" chown sandbox:sandbox /sandbox/.openclaw/bin/tidy.sh
  "$NEMOCLAW" "$SANDBOX" exec --timeout 10 -- ls -la /sandbox/.openclaw/bin/tidy.sh
fi

hr "1. replant /sandbox/demo/desktop (7 files, known mtimes)"
# nemoclaw exec rejects newlines in its command arg, so we one-line this.
"$NEMOCLAW" "$SANDBOX" exec --timeout 30 -- bash -c 'mkdir -p /sandbox/demo/desktop /sandbox/demo/sorted/{images,documents,archives,code,media} /sandbox/.openclaw/trash; rm -rf /sandbox/demo/sorted/*/* /sandbox/.openclaw/trash/* 2>/dev/null; cd /sandbox/demo/desktop && rm -f * 2>/dev/null; for f in screenshot_2026-05-20.png old_disk.iso draft.pdf temp_notes.tmp tax_receipts_2024.zip random.log empty_file.txt; do touch "$f"; done; head -c 1024 /dev/urandom > screenshot_2026-05-20.png; head -c 524288 /dev/urandom > old_disk.iso; head -c 4096 /dev/urandom > draft.pdf; head -c 200 /dev/urandom > temp_notes.tmp; head -c 8192 /dev/urandom > tax_receipts_2024.zip; touch -d "2024-01-15" old_disk.iso; touch -d "2023-12-01" random.log; echo "desktop files: $(ls /sandbox/demo/desktop | wc -l)"'

hr "2. revoke trash gate (start CLOSED)"
"$REPO_DIR/policies/revoke-trash.sh" "$SANDBOX" 2>&1 | grep -vE 'Unknown preset|preset cleared' | tail -4
ok "gate is CLOSED — marker removed, preset cleared, overlay file = closed"

hr "3. warm up the inference model"
MODEL=$("$NEMOCLAW" inference get 2>/dev/null | awk '/^Model:/ {print $2; exit}')
if [ -z "$MODEL" ]; then
  warn "could not read inference model; skipping warmup"
else
  echo "model: $MODEL"
  T0=$(date +%s)
  timeout 90 ollama run "$MODEL" "Reply exactly: PONG" >/dev/null 2>&1 || warn "warmup ollama run timed out"
  T1=$(date +%s)
  ok "warmed in $((T1 - T0))s"
fi

hr "4. dashboard URL + cheat sheet"
TOKEN=$("$NEMOCLAW" "$SANDBOX" gateway-token --quiet 2>/dev/null)
cat <<EOF

  Dashboard:  http://127.0.0.1:18789/#token=$TOKEN
              (treat the URL like a password — do not share or screen-record uncensored)

  Live demo cheat-sheet:

  ── Path A: bulk tidy (desktop-tidy skill, gate matters) ──
    A1. In dashboard chat, type:
         Use desktop-tidy to clean my desktop
       → 3 moves + 4 trash DENIED (gate closed) + lobster bounces.

    A2. In this terminal, type:
         ./policies/grant-trash.sh $SANDBOX
       → overlay trash bin flips RED → GREEN; OCSF policy event lands.

    A3. In dashboard chat, type:
         Tidy again
       → agent re-runs, this time the 4 trash succeed.

  ── Path B: natural language arrange (desktop-arrange skill) ──
    Always cite the example you want — Nemotron is most reliable when
    told exactly which snippet to copy.

    B1. Single move (Example 1):
         Use desktop-arrange skill, Example 1: move draft.pdf to upper-right.
       → agent emits set_position x=1440 y=310; lobster carries draft.pdf
         to upper-right; broker prints [broker] set_position ...

    B2. Trash with gate (Example 2):
         Use desktop-arrange skill, Example 2: trash temp_notes.tmp.
       → if gate closed → lobster bounce + "BLOCKED" log;
         after grant-trash.sh → file disappears into Trash.

    B3. Grid arrange (Example 3):
         Use desktop-arrange skill, Example 3: arrange all png files A-Z
         in the upper-right column.
       → multi-intent printf; icons stack y=180, 310, 440 ...

  Recovery (if the agent stalls > 60s on Path A):
       ./scripts/run-demo.sh $SANDBOX
     produces identical markdown via direct bash — same Landlock, same
     marker check, same audit log.

  Reset for another take:
       ./scripts/pre-demo.sh $SANDBOX

EOF
