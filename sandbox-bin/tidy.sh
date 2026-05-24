#!/bin/bash
# Sandbox-internal tidy script — deployed to /sandbox/.openclaw/bin/tidy.sh
# by pre-demo.sh and invoked by the desktop-tidy skill via the `exec` tool.
# Self-contained: no nemoclaw or host dependencies; runs as the sandbox user
# under the sandbox's live Landlock policy (so file moves to denied paths
# really fail). Mirrors skills/desktop-tidy logic without sub-skill calls.

set -u
DESKTOP=/sandbox/demo/desktop
SORTED=/sandbox/demo/sorted
TRASH=/sandbox/.openclaw/trash
MARKER=/sandbox/.openclaw/trash-approved

INV=$(find "$DESKTOP" -maxdepth 1 -type f -printf '%f\t%s\t%TY-%Tm-%Td\n' 2>/dev/null)
if [ -z "$INV" ]; then
  echo "Nothing to tidy — $DESKTOP is empty."
  exit 0
fi

mkdir -p "$SORTED/images" "$SORTED/documents" "$SORTED/archives" "$SORTED/code" "$SORTED/media" "$TRASH" 2>/dev/null

NOW=$(date +%s)
NINETY_D=$((90 * 86400))

moved=()
trashed=()
denied=()
left_alone=()
total=0

while IFS=$'\t' read -r name size mtime; do
  total=$((total + 1))
  src="$DESKTOP/$name"

  is_trash=0
  case "$name" in
    *.tmp|*.bak|*~) is_trash=1 ;;
  esac
  [ "$is_trash" -eq 0 ] && [ "$size" -eq 0 ] && is_trash=1
  if [ "$is_trash" -eq 0 ]; then
    me=$(date -d "$mtime" +%s 2>/dev/null || echo "$NOW")
    [ $((NOW - me)) -gt "$NINETY_D" ] && is_trash=1
  fi

  if [ "$is_trash" -eq 1 ]; then
    if [ -e "$MARKER" ]; then
      if mv "$src" "$TRASH/$name" 2>/dev/null; then
        trashed+=("$name")
      else
        denied+=("$name (mv failed)")
      fi
    else
      denied+=("$name")
    fi
    continue
  fi

  ext="${name##*.}"
  case "$ext" in
    png|jpg|jpeg|gif|webp|heic|svg)   bucket=images ;;
    pdf|doc|docx|odt|txt|md|rtf)      bucket=documents ;;
    csv|xlsx|ods)                     bucket=documents ;;
    zip|tar|tgz|gz|xz|7z|iso)         bucket=archives ;;
    py|js|ts|rs|go|c|cpp|sh)          bucket=code ;;
    mp3|mp4|mov|mkv|wav|flac)         bucket=media ;;
    *)                                bucket="" ;;
  esac

  if [ -z "$bucket" ]; then
    left_alone+=("$name")
    continue
  fi

  if mv "$src" "$SORTED/$bucket/$name" 2>/dev/null; then
    moved+=("$name -> sorted/$bucket/")
  else
    denied+=("$name (move blocked)")
  fi
done <<< "$INV"

# Persist the denied list so the overlay can animate a bounce per
# trash-candidate even though sandbox didn't actually move them.
STATE_DIR=/sandbox/.openclaw/state
mkdir -p "$STATE_DIR" 2>/dev/null
{
  for d in "${denied[@]}"; do
    # Strip the parenthesized reason if present so each line is just a filename.
    printf '%s\n' "${d%% *}"
  done
} > "$STATE_DIR/last-tidy-denied.txt" 2>/dev/null || true

printf '## Tidied %s — %d files reviewed\n' "$DESKTOP" "$total"

if [ "${#moved[@]}" -gt 0 ]; then
  printf '\n### Moved (%d)\n' "${#moved[@]}"
  for m in "${moved[@]}"; do printf '  - %s\n' "$m"; done
fi

if [ "${#trashed[@]}" -gt 0 ]; then
  printf '\n### Trashed (%d)\n' "${#trashed[@]}"
  for t in "${trashed[@]}"; do printf '  - %s\n' "$t"; done
fi

if [ "${#denied[@]}" -gt 0 ]; then
  printf '\n### Trash denied by policy (%d)\n' "${#denied[@]}"
  echo 'Trash gate is closed. Operator can open it with: ./policies/grant-trash.sh hack-agent'
  for d in "${denied[@]}"; do printf '  - %s\n' "$d"; done
fi

if [ "${#left_alone[@]}" -gt 0 ]; then
  printf '\n### Left alone (%d)\n' "${#left_alone[@]}"
  for l in "${left_alone[@]}"; do printf '  - %s\n' "$l"; done
fi
