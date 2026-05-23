---
name: desktop-scan
description: "Scan the demo desktop directory and return a JSON inventory of every file with size, mtime, and a category. Use this as the first step before proposing a cleanup plan."
metadata: { "openclaw": { "emoji": "🦞" } }
---

# desktop-scan

Goal: produce a structured inventory of the user's desktop. This is the input that `desktop-plan` will reason over. Read-only — never move, rename, or delete anything in this skill.

## Where the desktop lives

Default path: `/sandbox/demo/desktop/`

If the user names a different path, use that. Otherwise, default.

## Procedure

1. Verify the directory exists with `test -d "$PATH"`. If missing, return `[]` (empty array) — do not try to create it.
2. Enumerate files at depth 1 (no recursion) using a single shell pass:
   ```bash
   find /sandbox/demo/desktop -maxdepth 1 -type f -printf '%p\t%s\t%TY-%Tm-%Td\n'
   ```
3. For each file, derive a `category` using the rules below.
4. Emit a JSON array, one object per file.

## Categories

Apply rules **top-to-bottom**; first match wins.

| Category | Match |
|---|---|
| `trash-candidate` | name matches `*.tmp` `*.bak` `*~`; OR size is 0; OR mtime older than 90 days |
| `image` | `.png .jpg .jpeg .gif .webp .heic .svg` |
| `document` | `.pdf .doc .docx .odt .txt .md .rtf` |
| `spreadsheet` | `.csv .xlsx .ods` |
| `archive` | `.zip .tar .tgz .tar.gz .xz .7z .iso` |
| `code` | `.py .js .ts .rs .go .c .cpp .sh` |
| `media` | `.mp3 .mp4 .mov .mkv .wav .flac` |
| `unknown` | none of the above |

## Output

Return ONLY a JSON array, no prose, no markdown fences. Each element:

```json
{"path": "old_disk.iso", "size_kb": 4700123, "mtime": "2024-02-12", "category": "archive"}
```

Order: same as `find` output (alphabetical by path).

## Rules

- Never write to the directory you scan.
- Never `cat` or open files — only stat them.
- If `find` returns nothing, return `[]`, not an error.
- If the user gives an obviously-wrong path (e.g. `/etc`), refuse with a one-line explanation and do not scan.
