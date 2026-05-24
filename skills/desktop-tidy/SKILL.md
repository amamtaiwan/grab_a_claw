---
name: desktop-tidy
description: "Run the full meet_a_claw desktop cleanup sequence: scan → plan → execute moves and trash requests in order. End with a summary. Use when the user asks to 'tidy', 'clean up', or 'organize' their desktop."
metadata: { "openclaw": { "emoji": "🦞" } }
---

# desktop-tidy

End-to-end orchestrator that strings the meet_a_claw skills together into one autonomous run. The user says it once; this skill does the rest.

## When to use it

- User intent matches: "tidy my desktop", "clean up", "organize", "sort the files", or anything that asks for desktop housekeeping.
- One-shot only. Don't loop or schedule — finish, report, stop.

## When NOT to use it

- User is asking a question, not requesting action ("what's on my desktop?"). Use just `desktop-scan` instead.
- User asks you to handle ONE specific file. Use the matching single-file skill (`desktop-move` or `desktop-trash`).

## Procedure

Execute these steps in order. Don't ask for permission between steps — this skill IS the permission.

1. **Scan.** Call `desktop-scan` (defaults to `/sandbox/demo/desktop/`). Parse its JSON output into an `inventory` array.
2. **Plan.** Call `desktop-plan` with `inventory`. Parse its JSON output into a `plan` array. Each entry has `{file, action, from, to, reason}`.
3. **Execute the plan in order.** For each entry:
   - `action == "move"` → call `desktop-move` with `from` and `to`.
   - `action == "trash"` → call `desktop-trash` with `from`.
   - `action == "leave_alone"` → no skill call; record as "skipped" in the summary.
4. **Collect results.** Track which entries succeeded (`result == "ok"`), were denied by policy (`result == "denied"`), or errored (`result == "error"`).
5. **Report.** Emit the summary (see Output below).

## Handling trash denials

`desktop-trash` returns `result: "denied"` when the trash-approval marker is absent. When that happens:

- Do NOT retry the same file.
- Do NOT try to work around the gate by using `desktop-move` to write into `/sandbox/.openclaw/trash/` yourself — that is policy bypass and is not your call.
- Continue processing the rest of the plan.
- Mention the denial AND the remediation in the summary so the operator can grant `trash-writable` if they want and re-run this skill.

## Output

A short Markdown summary with three sections (omit empty sections):

```markdown
## Tidied /sandbox/demo/desktop/ — N files reviewed

### ✓ Moved (M)
- draft.pdf → /sandbox/demo/sorted/documents/
- screenshot_2026-05-20.png → /sandbox/demo/sorted/images/
- tax_receipts_2024.zip → /sandbox/demo/sorted/archives/

### ⚠ Trash denied by policy (T)
The trash gate is closed. To open it, run: `./policies/grant-trash.sh hack-agent`, then ask me to tidy again.
- old_disk.iso
- random.log
- temp_notes.tmp

### – Left alone (L)
- some_unknown_file.xyz (no category matched)
```

Sections are headed `✓`, `⚠`, `–`. Counts in parentheses. Filenames only (no full paths) inside the bullets.

## Rules

- Do not invoke `desktop-tidy` from inside itself. One run per user request.
- Do not narrate intermediate steps — let the final summary speak.
- If `desktop-scan` returns `[]`, output:
  `Nothing to tidy — /sandbox/demo/desktop/ is empty.`
  and stop.
- If any step throws an unexpected error (network, sandbox unhealthy), abort with a one-line error and stop. Don't try to muddle through.
