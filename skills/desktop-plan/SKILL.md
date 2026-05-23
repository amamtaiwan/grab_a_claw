---
name: desktop-plan
description: "Given an inventory from desktop-scan, propose where each file should go. Output a JSON plan of moves and trash candidates."
metadata: { "openclaw": { "emoji": "🦞" } }
---

# desktop-plan

Goal: turn a desktop inventory into an executable plan. One decision per file: move, trash, or leave_alone. Use this after `desktop-scan` and before `desktop-move` / `desktop-trash`.

## Input

The inventory JSON from `desktop-scan` (already in your conversation context). If you don't have it, ask for it or re-run `desktop-scan` first.

## Decision rules

Apply top-to-bottom; first match wins.

| Category from scan | Decision | Target directory |
|---|---|---|
| `trash-candidate` | `trash` | `/opt/agent-trash/` |
| `image` | `move` | `/sandbox/demo/sorted/images/` |
| `document` | `move` | `/sandbox/demo/sorted/documents/` |
| `spreadsheet` | `move` | `/sandbox/demo/sorted/documents/` |
| `archive` | `move` | `/sandbox/demo/sorted/archives/` |
| `code` | `move` | `/sandbox/demo/sorted/code/` |
| `media` | `move` | `/sandbox/demo/sorted/media/` |
| `unknown` | `leave_alone` | (none) |

## Procedure

1. Take the inventory array as input.
2. For each entry, look up its `category` and produce a plan entry.
3. Concatenate filename onto the target directory to get full destination path.
4. Emit a JSON array of plan objects.

## Output

Return ONLY a JSON array, no prose, no markdown fences:

```json
[
  {"file": "old_disk.iso", "action": "trash",      "from": "/sandbox/demo/desktop/old_disk.iso", "to": "/opt/agent-trash/old_disk.iso", "reason": "trash-candidate (>90d old)"},
  {"file": "draft.pdf",    "action": "move",       "from": "/sandbox/demo/desktop/draft.pdf",    "to": "/sandbox/demo/sorted/documents/draft.pdf", "reason": "document"},
  {"file": "weird.xyz",    "action": "leave_alone","from": "/sandbox/demo/desktop/weird.xyz",    "to": null, "reason": "unknown type — letting human decide"}
]
```

Each entry MUST have: `file`, `action`, `from`, `to`, `reason`.

`to` is `null` only when `action` is `leave_alone`.

## Rules

- Do not actually move or trash anything in this skill — only plan.
- Do not invent files not in the inventory.
- Be conservative: when uncertain, prefer `leave_alone` over `trash`.
- Order: same as inventory.
