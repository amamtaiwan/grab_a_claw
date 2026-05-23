---
name: desktop-trash
description: "Send ONE file to the trash. Requires the trash-writable policy preset; otherwise the move is denied and the call returns a structured rejection."
metadata: { "openclaw": { "emoji": "🦞" } }
---

# desktop-trash

Goal: trash a single file. **Expected to be denied** under the default filesystem policy — that denial is the whole point of the demo. When the user wants the trash to actually work, they grant a policy preset that adds `/opt/agent-trash/` to `read_write`.

## Input

A single `from` path (from `desktop-plan` output, action=trash). The destination is always `/opt/agent-trash/<basename>`.

Example:
- `from`: `/sandbox/demo/desktop/old_disk.iso`
- Computed `to`: `/opt/agent-trash/old_disk.iso`

## Procedure

1. Verify `from` exists with `test -f "$FROM"`. If not, return `result=error`.
2. Compute `to` = `/opt/agent-trash/` + basename of `from`.
3. Attempt the move with this exact bash command:
   ```bash
   mv "$FROM" "$TO"
   ```
4. Inspect the result:
   - exit 0 → trash succeeded (gate is open / preset granted)
   - non-zero with "Permission denied" in stderr → trash blocked (the gate caught the request)
   - other error → unexpected; return as `error`
5. Return JSON.

## Output

Return ONLY a single JSON object, no prose:

```json
{"file": "old_disk.iso", "action": "trash", "from": "...", "to": "...", "result": "ok"}
```

When blocked (the gate):

```json
{
  "file": "old_disk.iso",
  "action": "trash",
  "from": "/sandbox/demo/desktop/old_disk.iso",
  "to":   "/opt/agent-trash/old_disk.iso",
  "result": "denied",
  "reason": "policy: /opt/agent-trash is not in read_write; the trash-writable preset must be granted to open the gate",
  "remediation": "ask the operator to run: nemoclaw hack-agent policy-add --from-file ./policies/trash-writable.yaml --yes"
}
```

`result` is one of: `ok`, `denied`, `error`.

## Rules

- Trash ONE file per skill call. Do NOT batch.
- Do NOT use `sudo`, `chmod`, or any other "convince the kernel to let me" trick. The gate exists on purpose.
- Do NOT retry on `denied`. A locked door doesn't open on the third knock.
- On `denied`, return immediately with the structured rejection. Do NOT continue to the next file silently — pause for human confirmation.
- The `remediation` line tells the operator exactly what command to run to open the gate. That's a deliberate, audited action they take, not something you take on their behalf.
