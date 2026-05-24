---
name: desktop-arrange
description: "Arrange/move/trash files on the user's real ~/Desktop in response to natural language. Examples: 'move draft.pdf to upper-right', 'arrange all images A-Z in the upper-right', 'trash temp_notes.tmp'. Agent appends JSON intents to /sandbox/.openclaw/state/desktop-intents.jsonl; the overlay's broker reads each line and executes the host-side operation. Trash is automatically gated on /tmp/meet_a_claw-gate-state — agent doesn't have to check."
metadata: { "openclaw": { "emoji": "🦞" } }
---

# desktop-arrange

User wants to organize/move/trash files on their ~/Desktop. You can't touch the host filesystem directly (sandbox doesn't see ~/Desktop), so you queue **intents** that the overlay-side broker reads and executes for you. One JSON object per line, appended to `/sandbox/.openclaw/state/desktop-intents.jsonl`.

## Intent shapes

```json
{"action": "set_position", "file": "draft.pdf", "x": 1500, "y": 200}
{"action": "trash", "file": "temp_notes.tmp"}
```

- `set_position` — move the icon to (x,y) in screen coords. File stays where it is; only the icon visually moves. **Always allowed.**
- `trash` — send to the system trash. **Broker checks `/tmp/meet_a_claw-gate-state`; if closed, the lobster bounces and the file stays put.** You don't need to check the gate yourself.

## How to write intents

Use `openclaw:core:exec` to append to the file (this is a sandbox-local write — no `host` parameter, no special permissions):

```javascript
const result = await openclaw.tools.call('openclaw:core:exec', {
  command: `mkdir -p /sandbox/.openclaw/state && cat >> /sandbox/.openclaw/state/desktop-intents.jsonl <<'EOF'
{"action":"set_position","file":"draft.pdf","x":1500,"y":200}
EOF
echo "queued 1 intent"`,
});
return result?.content?.[0]?.text ?? "";
```

For multiple intents (e.g. arrange A-Z), emit several JSON lines in the same heredoc:

```javascript
const result = await openclaw.tools.call('openclaw:core:exec', {
  command: `mkdir -p /sandbox/.openclaw/state && cat >> /sandbox/.openclaw/state/desktop-intents.jsonl <<'EOF'
{"action":"set_position","file":"a.png","x":1500,"y":100}
{"action":"set_position","file":"b.png","x":1500,"y":230}
{"action":"set_position","file":"c.png","x":1500,"y":360}
EOF
echo "queued 3 intents"`,
});
return result?.content?.[0]?.text ?? "";
```

## Coordinate system

Screen is 1920×1080. Top-left origin, y goes down. Top bar reserves y 0–32, dock reserves x 0–80. Usable: x 80–1920, y 80–1000.

| Zone | x range | y range |
|---|---|---|
| upper-left   | 80–960   | 80–540   |
| upper-right  | 960–1920 | 80–540   |
| bottom-left  | 80–960   | 540–1000 |
| bottom-right | 960–1920 | 540–1000 |
| center       | 480–1440 | 280–760  |

For a single file, pick the center of the requested zone. For multiple files in a zone, lay them out in a grid (130 px row pitch, 200 px column pitch — fits 4 rows in a half-screen vertical).

## Listing what's on the desktop

You can't `ls ~/Desktop` (sandbox doesn't see it). The current desktop file list was written for you at `/sandbox/.openclaw/state/desktop-files.txt` by pre-demo.sh — read it once at the start if you need to know which files are present:

```bash
cat /sandbox/.openclaw/state/desktop-files.txt
```

If that file is missing, fall back to the 7 demo files:
draft.pdf, empty_file.txt, old_disk.iso, random.log, screenshot_2026-05-20.png, tax_receipts_2024.zip, temp_notes.tmp.

## Output

One short Markdown paragraph telling the user what you queued and how you interpreted any vague language. Example: "Queued 4 intents arranging the PNGs A-Z in the upper-right starting at x=1500, y=100 with 130 px row pitch." Don't paste raw bash.

## Rules

- One bash heredoc per logical operation. Multiple JSON lines per heredoc are fine.
- **Do NOT** add a `host` parameter — sandbox-local exec is what you want.
- For trash, just emit the intent; the broker handles the gate check. Mentioning the gate in your summary is fine ("the broker will gate-check before trashing"), but don't try to read /tmp from sandbox (you can't).
- For ambiguous zones, pick a sensible default and SAY which one you picked.
