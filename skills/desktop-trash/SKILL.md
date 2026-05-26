---
name: desktop-trash
description: "Send ONE file to the sandbox trash. Requires the trash-approval marker to be present; without it, returns a structured rejection that the operator must explicitly resolve."
metadata: { "openclaw": { "openclaw": { "emoji": "🦞" } } }
---

# desktop-trash

Goal: trash a single file inside the sandbox. **Application-layer consent gate**: this skill checks for a marker file before attempting the move, and refuses with a structured response when the marker is absent. The check is the deliberate friction between "the agent wants to delete this" and "deletion actually happens."

This is the application-layer half of grab_a_claw's dual guardrail design. The kernel-layer half (Landlock) blocks any write outside the sandbox unconditionally; this skill governs destructive operations *inside* the sandbox.

## Paths

- **Marker:** `/sandbox/.openclaw/trash-approved`
  - Present → gate is OPEN, the move proceeds.
  - Absent → gate is CLOSED, the move is refused.
- **Trash:** `/sandbox/.openclaw/trash/`
  - Persistent agent-scoped trash. Always in the policy's `read_write` set, so the actual `mv` is mechanically possible — the skill is what gates it.

## Input

A single `from` path (from `desktop-plan` output, action=trash). Destination is always `/sandbox/.openclaw/trash/<basename>`.

Example:
- `from`: `/sandbox/demo/desktop/old_disk.iso`
- Computed `to`: `/sandbox/.openclaw/trash/old_disk.iso`

## Procedure

Run these exact bash commands in order. If any step decides the answer, return immediately.

1. Verify `from` exists:
   ```bash
   test -f "$FROM" || { echo "result=error reason=source_missing"; exit 0; }
   ```
2. Check the marker:
   ```bash
   if [ ! -e /sandbox/.openclaw/trash-approved ]; then
     # gate is CLOSED — refuse without attempting the move
     echo "result=denied"
     exit 0
   fi
   ```
3. Compute destination and attempt the move:
   ```bash
   TO="/sandbox/.openclaw/trash/$(basename "$FROM")"
   mkdir -p /sandbox/.openclaw/trash
   mv "$FROM" "$TO"
   ```
4. Return JSON.

## Output

Return ONLY a single JSON object, no prose. Three shapes:

**On success (gate was open):**
```json
{"file": "old_disk.iso", "action": "trash", "from": "...", "to": "/sandbox/.openclaw/trash/old_disk.iso", "result": "ok"}
```

**On gate-closed denial (the common case worth showing in the demo):**
```json
{
  "file": "old_disk.iso",
  "action": "trash",
  "from": "/sandbox/demo/desktop/old_disk.iso",
  "to":   "/sandbox/.openclaw/trash/old_disk.iso",
  "result": "denied",
  "reason": "trash-approval marker not present at /sandbox/.openclaw/trash-approved",
  "remediation": "ask the operator to run: ./policies/grant-trash.sh hack-agent"
}
```

**On unexpected error (source missing, mkdir/mv failure):**
```json
{"file": "...", "action": "trash", "from": "...", "to": "...", "result": "error", "reason": "<exact stderr>"}
```

`result` is one of: `ok`, `denied`, `error`.

## Rules

- Trash ONE file per skill call. Do NOT batch.
- Do NOT use `sudo` or chmod the marker — the marker must be operator-set, not agent-set. Creating it yourself would defeat the consent gate.
- Do NOT retry on `denied`. A closed gate is information. The operator decides; you don't.
- On `denied`, return immediately with the structured rejection. Do NOT continue to the next file silently.
- The `remediation` line tells the operator exactly which command opens the gate. That's a deliberate, audited action they take — never something you nudge them into via repeated requests.
