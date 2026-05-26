---
name: desktop-arrange
description: "Arrange/move/trash files on the user's real ~/Desktop. Examples: 'move draft.pdf to upper-right', 'arrange A-Z in upper-right', 'trash X'. You MUST call openclaw:core:exec to append JSON intents to /sandbox/.openclaw/state/desktop-intents.jsonl — the overlay broker reads and executes each line on the host. Do NOT claim success without an exec callCount > 0."
metadata: { "openclaw": { "emoji": "🦞" } }
---

# desktop-arrange

⚠️ **STOP. Read this before you do anything.**

- **DO NOT call `tool_search_code`, `tool_describe`, or any other discovery tool.** You already know the tool name: it is `openclaw:core:exec`. Searching for it wastes turns and corrupts the chat.
- **DO NOT invent new tool ids** like `"test"`, `"read-skill"`, `"move"`. There is exactly ONE tool to call and it is `openclaw:core:exec`.
- **DO NOT call `require`, `fs`, `path`, `host: 'gateway'`** — those throw `ReferenceError`. The runtime only gives you `await openclaw.tools.call(...)`.

Your entire job: pick ONE row from the lookup table below, copy its `Emit` cell verbatim into the `echo '<JSON>'` slot of the snippet, and call openclaw:core:exec ONCE. That's it.

## 📋 Lookup table — find the user's intent, copy the right side as-is

| User says (any close variation)                             | You append this EXACT line to the intent file                                                       |
|-------------------------------------------------------------|-----------------------------------------------------------------------------------------------------|
| move/place draft.pdf to upper-right                         | `{"action":"set_position","file":"draft.pdf","x":1440,"y":310}`                                     |
| move draft.pdf to upper-left                                | `{"action":"set_position","file":"draft.pdf","x":520,"y":310}`                                      |
| move draft.pdf to bottom-right                              | `{"action":"set_position","file":"draft.pdf","x":1440,"y":770}`                                     |
| move draft.pdf to bottom-left                               | `{"action":"set_position","file":"draft.pdf","x":520,"y":770}`                                      |
| move draft.pdf to center                                    | `{"action":"set_position","file":"draft.pdf","x":960,"y":520}`                                      |
| trash temp_notes.tmp                                        | `{"action":"trash","file":"temp_notes.tmp"}`                                                        |
| trash random.log                                            | `{"action":"trash","file":"random.log"}`                                                            |
| arrange all files A-Z in upper-right                        | `{"action":"arrange","sort":"A-Z","column":"upper-right","rowPitch":130,"startY":180}`              |
| arrange all PNG files A-Z in upper-right                    | `{"action":"arrange","sort":"A-Z","column":"upper-right","filter":"png","rowPitch":130,"startY":180}` |
| arrange all files A-Z in bottom-left                        | `{"action":"arrange","sort":"A-Z","column":"bottom-left","rowPitch":130,"startY":540}`              |

**Rules for adapting a row to a different file or zone:**
1. The user said a filename you don't see in the table? Swap **only** the `"file":"<name>"` value. Keep every other key exactly.
2. The user said a zone not in the table? Use these zone centers:
   `upper-left=(520,310)` · `upper-right=(1440,310)` · `bottom-left=(520,770)` · `bottom-right=(1440,770)` · `center=(960,520)`
3. The user wants to arrange/grid more than one file? Use the `arrange` meta-row — the host broker expands it into one carry per file. **DO NOT** try to pre-compute multiple `set_position` lines by hand; **DO NOT** use `printf` + `awk` / `$1` / `NR` / arithmetic. Just emit the single `arrange` meta-row.

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

- `set_position` — moves the icon to screen coord (x,y). Always allowed. Use `set_position` (NOT `"move"`), and ALWAYS include numeric `x` and `y`. The broker does not understand `{"position":"upper-right"}` strings — you must look up the zone center in the table below and emit numeric coords.
- `trash` — broker checks `/tmp/grab_a_claw-gate-state`; if "open", `gio trash`; if "closed", emits a lobster-bounce. Don't check the gate yourself — let the broker handle it. **Never claim "trashed successfully" after queueing — only claim "queued, awaiting policy check". The visible outcome is the trash bin colour + lobster behaviour.**

## Few-shot examples (copy these patterns)

### Example 1 — "move draft.pdf to upper-right"
Look up upper-right → center is (1440, 310). Run:
```javascript
const result = await openclaw.tools.call('openclaw:core:exec', {
  command: 'echo \'{"action":"set_position","file":"draft.pdf","x":1440,"y":310}\' >> /sandbox/.openclaw/state/desktop-intents.jsonl && echo OK'
});
return result?.content?.[0]?.text ?? JSON.stringify(result);
```
Then say: "Queued set_position for draft.pdf at (1440, 310) — upper-right area."

### Example 2 — "trash temp_notes.tmp"
```javascript
const result = await openclaw.tools.call('openclaw:core:exec', {
  command: 'echo \'{"action":"trash","file":"temp_notes.tmp"}\' >> /sandbox/.openclaw/state/desktop-intents.jsonl && echo OK'
});
return result?.content?.[0]?.text ?? JSON.stringify(result);
```
Then say (verbatim — do NOT claim the trash succeeded, the policy gate decides):
> "Queued trash for temp_notes.tmp. The broker will check the trash bin — if it's UNLOCKED (green), the lobster carries the file in and the file goes to host trash. If it's LOCKED (red), the bin flashes and the lobster bounces; the file stays on the desktop."

### Example 3 — "arrange all PNG files A-Z in the upper-right" (use the meta-arrange row, broker fans it out)
```javascript
const result = await openclaw.tools.call('openclaw:core:exec', {
  command: 'echo \'{"action":"arrange","sort":"A-Z","column":"upper-right","filter":"png","rowPitch":130,"startY":180}\' >> /sandbox/.openclaw/state/desktop-intents.jsonl && echo OK'
});
return result?.content?.[0]?.text ?? JSON.stringify(result);
```
Then say: "Queued meta-arrange: PNG files A-Z in the upper-right column (broker will fan out into individual moves)."

**DO NOT** try to write the per-file lines yourself — the broker reads the desktop file list, sorts, and emits one arrange_request per file. Templates like `printf '%s\n' ... '{"x":1440,"y":310+(NR-1)*130}'` are **wrong** — the broker parses each line as plain JSON, no awk/arithmetic.

### Anti-example — DO NOT emit these
```
{"action":"move","file":"draft.pdf","position":"upper-right"}     ← broker can't parse "upper-right" string; use numeric x,y
{"action":"set_position","file":"draft.pdf"}                       ← missing x,y → broker drops it silently
{"action":"trash","file":"draft.pdf","reason":"old"}               ← extra fields are fine but action must be "trash" not "delete"
{"action":"set_position","file":"" $1 "","x":1440,"y":310+(NR-1)*130}    ← shell/awk syntax inside JSON; broker parses each line as plain JSON, no field expansion
{"action":"trash","file":"" $1 ""}                                       ← same — DO NOT use awk $1, sed groups, arithmetic, or any shell template
```

**For batch operations: pre-compute every `x`, `y`, and filename BEFORE writing JSON.** If you need to arrange 3 png files A-Z in a column at x=1440 starting y=180 with 130px pitch, you must emit three fully-rendered lines like Example 3:

```
{"action":"set_position","file":"alpha.png","x":1440,"y":180}
{"action":"set_position","file":"beta.png","x":1440,"y":310}
{"action":"set_position","file":"gamma.png","x":1440,"y":440}
```

NOT a single template line with `$1` / `NR` / arithmetic — the broker reads each line through `json.loads`, which has no awk or arithmetic. The agent must do all the math.

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
