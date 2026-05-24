---
name: desktop-tidy
description: "Tidy the user's demo desktop. Call the openclaw exec tool with command='/sandbox/.openclaw/bin/tidy.sh', then return the script's stdout verbatim. Do not search for sub-skills; the entire procedure lives in that one script."
metadata: { "openclaw": { "emoji": "🦞" } }
---

# desktop-tidy

User wants the desktop tidied. The full procedure (scan, classify, move, policy-gated trash, Markdown summary) lives in a sandbox-resident script. Run it via the `exec` tool.

## Procedure

Call the **`exec`** tool (id `openclaw:core:exec`) with:

```
command = "/sandbox/.openclaw/bin/tidy.sh"
```

That's the entire skill. The script handles scan, classification, the trash-approval marker check, and the Markdown summary. You don't need to read its source or post-process its output.

## Output

Return the script's stdout **verbatim** as your reply to the user. Do not paraphrase, summarize, or add commentary. The script already formats a clean Markdown report (with `### Moved`, `### Trashed`, `### Trash denied by policy`, `### Left alone` sections as applicable).

## Rules

- One `exec` call. Do not split, retry, or call other tools.
- Do not search the tool catalog for other skills — there are none to find; everything is in `tidy.sh`.
- If `exec` fails (script not found, sandbox unhealthy), report the exact error in one line and stop.
