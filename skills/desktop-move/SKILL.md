---
name: desktop-move
description: "Move ONE file from one location to another. Subject to the sandbox filesystem policy. Use after desktop-plan, once per file with action=move."
metadata: { "openclaw": { "emoji": "🦞" } }
---

# desktop-move

Goal: perform a single file move. The sandbox filesystem policy decides whether it's allowed. This skill does NOT bypass policy; failures are reported, not retried.

## Input

A single `{from, to}` pair (you'll get these from the `desktop-plan` output). Example:
- `from`: `/sandbox/demo/desktop/draft.pdf`
- `to`:   `/sandbox/demo/sorted/documents/draft.pdf`

## Procedure

1. Verify `from` exists with `test -f "$FROM"`. If not, return failure (do not retry).
2. Ensure `to`'s parent directory exists. Execute this exact bash command:
   ```bash
   mkdir -p "$(dirname "$TO")"
   ```
   If `mkdir` fails (likely because policy blocks creating that dir), return failure.
3. Move with this exact bash command:
   ```bash
   mv "$FROM" "$TO"
   ```
4. Verify with `test -f "$TO" && ! test -f "$FROM"`.
5. Return JSON.

## Output

Return ONLY a single JSON object, no prose:

```json
{"file": "draft.pdf", "action": "move", "from": "...", "to": "...", "result": "ok"}
```

On failure:

```json
{"file": "draft.pdf", "action": "move", "from": "...", "to": "...", "result": "denied", "reason": "mv: cannot create '/sandbox/demo/sorted/documents/draft.pdf': Permission denied"}
```

`result` is one of: `ok`, `denied` (policy-related), `error` (other).

## Rules

- Move ONE file per skill call. Do NOT batch.
- Do NOT use `sudo` or any escalation. The policy decides; respect it.
- Do NOT retry on `denied`. The deny is the system telling you it's not allowed; loop bashing it will spam the audit log.
- Do NOT use `cp` + `rm` as a workaround. Atomic `mv` is the only allowed move primitive.
- If you find yourself wanting to disable the policy or work around it, stop and report the denial honestly. The denial is information, not a problem to work around.
