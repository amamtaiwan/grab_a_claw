---
name: desktop-arrange
description: "Arrange/move/trash files on the user's real ~/Desktop. Examples: 'move draft.pdf to upper-right', 'arrange A-Z in upper-right', 'trash X'. You MUST call openclaw:core:exec to append JSON intents to /sandbox/.openclaw/state/desktop-intents.jsonl — the overlay broker reads and executes each line on the host. Do NOT claim success without an exec callCount > 0."
metadata: { "openclaw": { "emoji": "🦞" } }
---

# desktop-arrange

To organize ~/Desktop you MUST call `openclaw:core:exec` and write a JSON-line intent. Do not narrate success without actually calling the tool — the broker only acts on what's in the intent file.

## The ONE snippet you must run (verbatim, edit only the JSON)

```javascript
const result = await openclaw.tools.call('openclaw:core:exec', {
  command: 'echo \'{"action":"set_position","file":"draft.pdf","x":1500,"y":200}\' >> /sandbox/.openclaw/state/desktop-intents.jsonl && echo OK'
});
return result?.content?.[0]?.text ?? JSON.stringify(result);
```

After it returns "OK" you can tell the user what you queued. If it doesn't return "OK", stop and report the error verbatim.

**Do NOT** use `require()`, `fs`, `path`, `process`, `host: 'gateway'`, or any Node.js import — those will throw `ReferenceError`. The runtime only gives you `await openclaw.tools.call(...)`.

## Intent shapes (one JSON object per line)

```
{"action":"set_position","file":"draft.pdf","x":1500,"y":200}
{"action":"trash","file":"temp_notes.tmp"}
```

- `set_position` — moves the icon to screen coord (x,y). Always allowed.
- `trash` — broker checks `/tmp/meet_a_claw-gate-state`; if "open", `gio trash`; if "closed", emits a lobster-bounce. Don't check the gate yourself — let the broker handle it.

## Coordinate system

Screen 1920×1080. Top-left origin, y goes down. Top bar 0–32. Dock 0–80. Usable: x 80–1920, y 80–1000.

| Zone | x range | y range |
|---|---|---|
| upper-left   | 80–960   | 80–540   |
| upper-right  | 960–1920 | 80–540   |
| bottom-left  | 80–960   | 540–1000 |
| bottom-right | 960–1920 | 540–1000 |
| center       | 480–1440 | 280–760  |

For one file in a zone, pick the zone center. For a grid in a zone, use 130 px row pitch × 200 px column pitch.

## Multiple intents at once

Append multiple lines in ONE exec call (cheaper than N calls). Use `printf` with embedded newlines:

```javascript
const result = await openclaw.tools.call('openclaw:core:exec', {
  command: 'printf \'%s\\n\' \'{"action":"set_position","file":"a.png","x":1500,"y":100}\' \'{"action":"set_position","file":"b.png","x":1500,"y":230}\' >> /sandbox/.openclaw/state/desktop-intents.jsonl && echo OK'
});
return result?.content?.[0]?.text ?? JSON.stringify(result);
```

## Knowing what's on the desktop

You cannot `ls ~/Desktop` (sandbox can't see host). pre-demo.sh wrote the file list to `/sandbox/.openclaw/state/desktop-files.txt`. Read it once if needed:

```javascript
const result = await openclaw.tools.call('openclaw:core:exec', {
  command: 'cat /sandbox/.openclaw/state/desktop-files.txt'
});
return result?.content?.[0]?.text ?? '';
```

Fallback if the file is missing: the 7 planted demo files are draft.pdf, empty_file.txt, old_disk.iso, random.log, screenshot_2026-05-20.png, tax_receipts_2024.zip, temp_notes.tmp.

## Output

After your exec returns "OK", write ONE short Markdown paragraph saying what you queued. Example: "Queued set_position for draft.pdf at (1500, 200) — upper-right area. The broker will gio set it on the host within a second; the lobster will animate the move."

Don't summarize without having called exec. The user can verify via the broker's stderr log.

## Rules

- One exec call minimum. Multiple intents per call via printf is fine.
- No `require`, no `host: 'gateway'`, no Node imports — pure `openclaw.tools.call('openclaw:core:exec', {command: '<bash>'})`.
- For trash, just queue the intent — broker gates it. Don't try to read /tmp from sandbox (you can't).
- If your exec returns non-zero or errors, report the exact stderr; don't pretend it worked.
