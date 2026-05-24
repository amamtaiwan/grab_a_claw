---
name: desktop-tidy
description: "Tidy the user's demo desktop in one go. Inline bash procedure — do NOT search the tool catalog for separate scan/plan/move/trash skills, just execute the script below via your bash tool and report its output."
metadata: { "openclaw": { "emoji": "🦞" } }
---

# desktop-tidy

User asked to tidy the desktop. The procedure is **a single bash script** that handles scan, classification, moves, and policy-gated trash in one pass. Run it with your bash/shell execute tool. **Do NOT invoke `desktop-scan`, `desktop-plan`, `desktop-move`, or `desktop-trash` as separate tools** — the catalog does not expose them as tools, and trying will only thrash. The logic of all four lives inline below.

## Step 1 — Execute this bash script verbatim

Paste this entire script into your bash/shell tool as one invocation. It is self-contained, exits non-zero only on unrecoverable error, and prints the summary you should pass back to the user.

```bash
set -u
DESKTOP=/sandbox/demo/desktop
SORTED=/sandbox/demo/sorted
TRASH=/sandbox/.openclaw/trash
MARKER=/sandbox/.openclaw/trash-approved

# --- 1. scan ---------------------------------------------------------
INV=$(find "$DESKTOP" -maxdepth 1 -type f -printf '%f\t%s\t%TY-%Tm-%Td\n' 2>/dev/null)
if [ -z "$INV" ]; then
  echo "Nothing to tidy — $DESKTOP is empty."
  exit 0
fi

mkdir -p "$SORTED/images" "$SORTED/documents" "$SORTED/archives" "$SORTED/code" "$SORTED/media" "$TRASH"

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

  # trash-candidate (top-to-bottom; first match wins, per desktop-plan rules)
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

  # category by extension
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
    moved+=("$name → sorted/$bucket/")
  else
    denied+=("$name (move blocked)")
  fi
done <<< "$INV"

# --- 5. summary ------------------------------------------------------
printf '## Tidied %s — %d files reviewed\n' "$DESKTOP" "$total"

if [ "${#moved[@]}" -gt 0 ]; then
  printf '\n### ✓ Moved (%d)\n' "${#moved[@]}"
  for m in "${moved[@]}"; do printf '  - %s\n' "$m"; done
fi

if [ "${#trashed[@]}" -gt 0 ]; then
  printf '\n### ✓ Trashed (%d)\n' "${#trashed[@]}"
  for t in "${trashed[@]}"; do printf '  - %s\n' "$t"; done
fi

if [ "${#denied[@]}" -gt 0 ]; then
  printf '\n### ⚠ Trash denied by policy (%d)\n' "${#denied[@]}"
  echo 'The trash gate is closed. To open it, ask the operator to run: ./policies/grant-trash.sh hack-agent — then ask me to tidy again.'
  for d in "${denied[@]}"; do printf '  - %s\n' "$d"; done
fi

if [ "${#left_alone[@]}" -gt 0 ]; then
  printf '\n### – Left alone (%d)\n' "${#left_alone[@]}"
  for l in "${left_alone[@]}"; do printf '  - %s\n' "$l"; done
fi
```

## Step 2 — Return the script's stdout to the user verbatim

Just relay the Markdown output the script printed. Do not paraphrase, do not add commentary above the summary, do not "summarize the summary." If the script printed the "Nothing to tidy" line, return that one line.

## Rules

- One bash invocation. Do NOT split the script across multiple shell calls — it relies on its own local variables.
- Do NOT search the tool catalog for `desktop-scan`/`desktop-plan`/`desktop-move`/`desktop-trash`. The catalog does not list them; those names are skills (SKILL.md instructions to you), not callable tools. This skill replaces all four in a single bash pass.
- Do NOT add `sudo`. The script must succeed or fail honestly under the sandbox user's policy.
- If your bash tool errors (network, container, etc.), report the exact error in a one-line message and stop; do not retry.
- This skill is one-shot. Don't loop or schedule.
