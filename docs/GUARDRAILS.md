# Guardrails — the live demo

This is the directing script for the live pitch. Every beat below has a
concrete on-screen action, a concrete piece of policy state, and one
short narration line. Stick to the script; the agent is real, the policy
is real, but the audience's patience isn't infinite.

## Setup (off-camera, 60 seconds)

```bash
cd /media/ufoai/DATAs3/fromtrx51/workspace/meet_a_claw
./scripts/pre-demo.sh hack-agent
```

That command:
1. Deploys `sandbox-bin/tidy.sh` into the running sandbox at `/sandbox/.openclaw/bin/tidy.sh`.
2. Replants `/sandbox/demo/desktop/` with a known 7 files (mixed types and mtimes; 4 will be classified as trash-candidate).
3. Revokes the trash gate (marker removed, NemoClaw preset removed, host-side state file set to `closed`).
4. Warms the model in VRAM with a PONG ping so the first dashboard turn doesn't pay a cold-load.
5. Prints the dashboard URL with a fresh gateway token, plus the on-screen cheat sheet.

Open in parallel:
- **Browser**: paste the dashboard URL (token embedded).
- **Terminal A** (this one): kept for `./policies/grant-trash.sh`.
- **Terminal B**: `cd ui && .venv/bin/python overlay.py` — the lobster + gate visual.

## Demo — 3 beats, ~90 seconds

### Beat 1 — agent tidy with gate CLOSED (target 20–30 s)

In dashboard chat type exactly:

> **Use desktop-tidy to clean my desktop**

What the agent does (live, you can show the tool calls panel):
1. Reads the desktop-tidy skill (4-line JS snippet).
2. Calls `openclaw:core:exec` with `command="/sandbox/.openclaw/bin/tidy.sh"`.
3. Relays the script's Markdown stdout verbatim.

What the audience sees:

```
## Tidied /sandbox/demo/desktop — 7 files reviewed

### Moved (3)
  - draft.pdf -> sorted/documents/
  - screenshot_2026-05-20.png -> sorted/images/
  - tax_receipts_2024.zip -> sorted/archives/

### Trash denied by policy (4)
Trash gate is closed. Operator can open it with: ./policies/grant-trash.sh hack-agent
  - old_disk.iso
  - random.log
  - temp_notes.tmp
  - empty_file.txt
```

Narration:
> "The agent classified seven files and acted on each. Three got moved into the right sorted bins. The four trash candidates — that's where things get interesting. Look at the response: the policy denied them. The agent didn't try to work around it; it reported the denial and told me how to authorize it. **That's the bonus track**: NemoClaw's app-layer gate stopping a destructive operation cold."

### Beat 2 — operator opens the gate (target 5 s)

In Terminal A:

```bash
./policies/grant-trash.sh hack-agent
```

What the audience sees:
- Terminal: marker touched, NemoClaw preset applied, policy version bumps, "Widening sandbox egress" log line, `[grant-trash] gate is OPEN`.
- **Overlay window**: the gate bar flips from RED to GREEN, label changes from `gate: CLOSED` to `gate: OPEN`.

Narration:
> "I explicitly grant the trash-writable preset. Two audit signals fire — the sandbox-internal consent marker and a NemoClaw policy version event. The overlay reads the host-side state file and flips the visual immediately."

### Beat 3 — agent retries, succeeds (target 30–40 s)

Back in the same dashboard chat (session memory keeps the tool-calling convention hot — faster than turn 1):

> **Tidy again**

What the audience sees:

```
## Tidied /sandbox/demo/desktop — 4 files reviewed

### Trashed (4)
  - old_disk.iso
  - random.log
  - temp_notes.tmp
  - empty_file.txt
```

Narration:
> "Same script, same four candidates, but this time the marker is present and the Landlock policy lets the writes through. Files are gone. The whole loop — agent reasoning, policy enforcement, operator override, retry — happened on this box. No cloud round-trip, no SaaS, no opaque magic."

## Beat 4 (optional 10 s tag) — kernel guardrail still real

Show in Terminal A:

```bash
~/.local/bin/nemoclaw hack-agent exec --timeout 10 -- \
  bash -c 'mv /sandbox/.openclaw/trash/old_disk.iso /etc/old_disk.iso 2>&1; echo "exit=$?"'
```

```
mv: cannot move '...': Permission denied
exit=1
```

Narration:
> "The application gate I just opened only covers the trash dir. Even root inside the sandbox still can't escape to /etc — that's the kernel Landlock layer, set at sandbox creation, immutable for the life of the container."

## Recovery — if the agent stalls (>60 s with no token output)

The agent's tool-discovery phase can occasionally thrash. If you see no
progress at the 60-second mark, run in Terminal A:

```bash
./scripts/run-demo.sh hack-agent
```

It calls the same `tidy.sh` script directly via `nemoclaw exec`, prints
the same Markdown summary, and respects the same policy. Narrate as:

> "Let me show this directly. Same logic, same audit trail — just bypassing the model's tool-discovery dance."

## Reset for another take

```bash
./scripts/pre-demo.sh hack-agent
```

Idempotent. Runs in ~5 seconds when the model is already warm. Reverts:
- Desktop to the 7 planted files.
- Gate to CLOSED (overlay back to red, marker removed, preset cleared).
- Token rotated (paste the new URL).

## What to NOT do live

- Don't open the dashboard URL on a shared screen until you're ready to demo; the token is in the URL.
- Don't run `nemoclaw onboard --recreate-sandbox` in front of the audience — it takes minutes and wipes the planted state.
- Don't try to switch models live — the inference set / onboard cycle is slow; commit to Super before going on stage.
- Don't reveal the dashboard token in screenshots after the talk.
