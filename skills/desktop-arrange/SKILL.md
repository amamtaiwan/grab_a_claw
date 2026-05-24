---
name: desktop-arrange
description: "Arrange files on the user's real ~/Desktop in response to natural language. Examples: 'move screenshot.png to bottom-left', 'arrange all images in upper-right A-Z', 'put PDFs in a folder called Drafts', 'tidy these icons into a grid'. For DELETE/TRASH the host-side gate file /tmp/meet_a_claw-gate-state must contain 'open'; everything else is free."
metadata: { "openclaw": { "emoji": "🦞" } }
---

# desktop-arrange

User wants the agent to organize/move files on their actual ~/Desktop. The agent calls the `openclaw:core:exec` tool with **`host: 'gateway'`** so the command runs on the host machine (where `~/Desktop` actually lives), and uses `gio set` to move icons or `mv` to relocate files.

## How to invoke

Run JS verbatim via tool_search_code, with the shell command the user's intent implies:

```javascript
const result = await openclaw.tools.call('openclaw:core:exec', {
  command: 'YOUR SHELL COMMAND HERE',
  host: 'gateway',
});
return result?.content?.[0]?.text ?? JSON.stringify(result);
```

Default `host` is `sandbox` — you MUST pass `host: 'gateway'` or commands won't see `~/Desktop`.

## Coordinate system (natural-language zones)

Screen is 1920x1080. Top-left origin, y goes down.

| Zone | x range | y range |
|---|---|---|
| upper-left   | 80–960    | 80–540   |
| upper-right  | 960–1920  | 80–540   |
| bottom-left  | 80–960    | 540–1000 |
| bottom-right | 960–1920  | 540–1000 |
| center       | 480–1440  | 280–760  |

For a single file, pick the center of the requested zone. For multiple files, lay them out in a grid (e.g., 4 rows × N columns, 130 px row pitch, 200 px column pitch).

## Operations

### Move an icon to a position (file stays in place; icon visually moves)

```bash
gio set ~/Desktop/<filename> metadata::nautilus-icon-position "X,Y"
```

### Move a file into a folder ON the desktop

```bash
mkdir -p ~/Desktop/<folder>
mv ~/Desktop/<file> ~/Desktop/<folder>/
```

### Arrange a set of files A-Z in a region (example: upper-right, 4 per column)

```bash
i=0
for f in $(ls ~/Desktop/*.png 2>/dev/null | sort); do
  x=$((1500 - (i / 4) * 200))
  y=$((100 + (i % 4) * 130))
  gio set "$f" metadata::nautilus-icon-position "$x,$y"
  i=$((i + 1))
done
```

### Listing what's on the desktop

```bash
ls -1 ~/Desktop
```

## Trash gate (DELETE/TRASH operations)

Before ANY `gio trash` or `rm` against a desktop file, check the gate:

```bash
state=$(cat /tmp/meet_a_claw-gate-state 2>/dev/null || echo closed)
if [ "$state" != "open" ]; then
  echo "Trash gate is CLOSED. Ask the operator to click the red gate on the desktop, or run ./policies/grant-trash.sh hack-agent, then ask me to retry."
  exit 0
fi
gio trash ~/Desktop/<filename>
```

If the gate is closed and the user asked for deletion, refuse and stop. Do NOT delete any other files. Do NOT touch the gate file yourself; only the operator opens it.

Non-trash operations (move, arrange, mkdir) are NOT gated. Run them freely.

## Output

Return a short Markdown paragraph telling the user what you did and where things ended up. Don't paste raw bash; describe the outcome ("Moved 3 PNGs A-Z in the upper-right" / "Trash gate closed — refused to delete old_disk.iso").

## Rules

- One `exec` call per logical task. If the user wants several distinct things, you can chain calls within the same response.
- Always pass `host: 'gateway'`. Sandbox-target exec won't see `~/Desktop`.
- For ambiguous zones, pick a sensible interpretation and SAY which zone you picked in the summary.
- On any non-zero exit code, report the stderr verbatim and stop.
- The lobster overlay watches `~/Desktop` independently and animates each position change / removal you make — you don't need to coordinate timing; just do the operation.
