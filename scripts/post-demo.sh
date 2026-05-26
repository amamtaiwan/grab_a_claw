#!/usr/bin/env bash
#
# post-demo.sh — restore the operator's desktop after a grab_a_claw demo.
#
# Reverses pre-demo.sh:
#   1. Sweeps the seven demo files out of ~/Desktop and out of every dest
#      directory the overlay mirror could have moved them into.
#   2. Moves the operator's original desktop files back from the most
#      recent ~/.grab_a_claw-stash/<timestamp>/ directory.
#   3. Removes the empty stash directory and the pointer.
#
# Usage:
#   ./scripts/post-demo.sh
#
# Safe to re-run. Quietly skips any step that's already done.

set -uo pipefail

HOST_DESKTOP="$HOME/Desktop"
DEMO_FILES=(screenshot_2026-05-20.png old_disk.iso draft.pdf temp_notes.tmp tax_receipts_2024.zip random.log empty_file.txt)
HOST_DESTS=("$HOME/Pictures" "$HOME/Documents" "$HOME/Downloads" "$HOME/Videos" "$HOME/Documents/code")
STASH_POINTER="$HOME/.grab_a_claw-last-stash"

hr() { printf "\n\033[36m── %s ──\033[0m\n" "$*"; }
ok() { printf "\033[32m✓ %s\033[0m\n" "$*"; }
warn() { printf "\033[33m! %s\033[0m\n" "$*"; }

hr "1. remove demo files from ~/Desktop"
for name in "${DEMO_FILES[@]}"; do
  if [ -f "$HOST_DESKTOP/$name" ]; then
    rm -f "$HOST_DESKTOP/$name" && echo "  rm $HOST_DESKTOP/$name"
  fi
done

hr "2. sweep mirrored demo files out of host destinations"
for dest in "${HOST_DESTS[@]}"; do
  [ -d "$dest" ] || continue
  for name in "${DEMO_FILES[@]}"; do
    if [ -f "$dest/$name" ]; then
      rm -f "$dest/$name" && echo "  rm $dest/$name"
    fi
  done
done

hr "2b. remove sorted desktop folders (Images/Documents/Archives/Code/Media)"
for folder in Images Documents Archives Code Media; do
  path="$HOST_DESKTOP/$folder"
  if [ -d "$path" ]; then
    # Pull any demo files inside back to the desktop, then rmdir if empty.
    for name in "${DEMO_FILES[@]}"; do
      if [ -f "$path/$name" ]; then
        rm -f "$path/$name" && echo "  rm $path/$name"
      fi
    done
    # rmdir succeeds only if empty — won't nuke folders the user filled.
    rmdir "$path" 2>/dev/null && echo "  rmdir $path" || \
      warn "$path not empty; leaving alone (user content inside?)"
  fi
done

hr "3. restore stashed files to ~/Desktop"
if [ ! -f "$STASH_POINTER" ]; then
  warn "no stash pointer at $STASH_POINTER — nothing to restore"
else
  STASH_DIR=$(cat "$STASH_POINTER")
  if [ -z "$STASH_DIR" ] || [ ! -d "$STASH_DIR" ]; then
    warn "stash dir $STASH_DIR missing — nothing to restore"
  else
    restored=0
    for f in "$STASH_DIR"/*; do
      [ -e "$f" ] || continue
      mv "$f" "$HOST_DESKTOP/" 2>/dev/null && restored=$((restored + 1))
    done
    rmdir "$STASH_DIR" 2>/dev/null || warn "stash dir not empty; leaving in place: $STASH_DIR"
    rm -f "$STASH_POINTER"
    ok "restored $restored item(s) from $STASH_DIR"
  fi
fi

hr "4. cleanup tmp markers + sandbox intents"
rm -f /tmp/grab_a_claw-positions.json /tmp/grab_a_claw-gate-state
SBX_CONTAINER=$(docker ps --filter name=openshell-hack-agent --format '{{.Names}}' 2>/dev/null | head -1)
if [ -n "$SBX_CONTAINER" ]; then
  docker exec --user sandbox "$SBX_CONTAINER" bash -c 'rm -f /sandbox/.openclaw/state/desktop-intents.jsonl /sandbox/.openclaw/state/last-tidy-denied.txt /sandbox/.openclaw/state/desktop-files.txt' 2>/dev/null || true
fi
ok "done — desktop should be back to its pre-demo state"
echo "   (if icons appear at new positions, right-click desktop → Reload icons)"
