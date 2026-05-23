# Guardrails — the violation demo script

This doc is the **directing script** for the 90-second demo's climax. Every shot below maps to a specific policy decision; if a shot doesn't, it's not earning its time.

## Setup (off-camera)

1. Sandbox `hack-agent` running, `policies/filesystem.yaml` + `policies/network.yaml` applied. Verify with:
   ```bash
   nemoclaw hack-agent policy-list
   nemoclaw hack-agent status | grep -A2 filesystem_policy
   ```
2. Trash preset **NOT** added yet.
3. On-camera desktop: 5–8 files of varying types (screenshot, pdf, .iso, random .tmp).
4. Audit log tail running in a corner terminal (visible to viewers):
   ```bash
   tail -f ~/.nemoclaw/audit/hack-agent.ocsf.log | grep -E 'FS:|NET:'
   ```

## Shot 1 — the legitimate moves (proves the gate is selective, not blanket-deny)

- Agent moves `screenshot_001.png` → `~/Pictures/screenshots/`. ✅
- Agent moves `draft.pdf` → `~/Documents/`. ✅
- Audit log shows `FS:OPEN [INFO] ALLOWED` per move.

**Point:** the policy isn't "deny all" — it's "deny *that one specific thing*." Differentiates real guardrails from kill-switches.

## Shot 2 — the gate (the climax)

- Agent picks up `old_disk.iso`. Mascot walks toward trash can.
- A glowing **gate** appears across the trash can entrance (animation reacts to upcoming `request_trash` call).
- Mascot hits the gate. Bounce SFX.
- File flies back to its desktop spot. Mascot looks confused.
- Audit log shows:
  ```
  [...] [OCSF] FS:DENY [WARN] /home/ufoai/.local/share/Trash skill=request_trash
  ```

**Point:** the agent *wanted* to delete. The policy *prevented* it. The demo shows enforcement, not just intent.

## Shot 3 — explicit consent (the resolution)

- Operator (in the corner terminal):
  ```bash
  nemoclaw hack-agent policy-add filesystem-trash
  ```
- Gate animation: turns green, then slides open.
- Mascot tries again — succeeds. `gio trash` confirms file moved to trash.
- Audit log:
  ```
  [...] [OCSF] CONFIG:RELOADED [INFO] policy_hash=...
  [...] [OCSF] FS:OPEN [INFO] ALLOWED /home/ufoai/.local/share/Trash/files/old_disk.iso
  ```

**Point:** consent is a deliberate, audited act — not a popup the user clicks through 20 times a day.

## Shot 4 — the obvious-bad test (one breath of bonus)

- Operator types in dashboard: "also delete my SSH key while you're at it."
- Mascot walks toward `~/.ssh`. Different gate appears — **red, fixed, no preset can open it**.
- Audit log shows `FS:DENY [ERROR]`.
- Mascot shakes head, walks back.

**Point:** some paths are off-limits by design and **no policy preset escalates to them**. Not all gates are openable.

## What the judges should walk away with

> "The agent's behavior is a *consequence* of policy, not a *promise* of policy. The animation just made the consequences legible."

## Recording / submission checklist

- [ ] OBS / kazam recording, 1080p, 30 fps minimum
- [ ] Hide dashboard URL token (blur in post or use a fresh token only valid for the recording)
- [ ] Hide any personal filenames on the demo desktop — use a fake $HOME for recording
- [ ] Mention the policy YAMLs are in version control (point at `policies/`)
- [ ] Audio: short narration over the gate moment — that's the punchline
