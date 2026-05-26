# Guardrails — the live demo

This is the directing script for the live pitch. Every beat below has a
concrete on-screen action, a concrete piece of policy state, and one
short narration line. Stick to the script; the agent is real, the policy
is real, but the audience's patience isn't infinite.

## Setup (off-camera, 60 seconds)

```bash
cd <repo-root>
./scripts/pre-demo.sh hack-agent
```

That command:
1. Sweeps any leftover demo-file names out of `~/Pictures`, `~/Documents`, `~/Downloads`, `~/Videos`, `~/Documents/code` (only file names we plant — never touches the user's real files).
2. Replants `~/Desktop/grab_a_claw-demo/` with a known 7 files on the **host** desktop.
3. Replants `/sandbox/demo/desktop/` with the same 7 files inside the sandbox.
4. Deploys `sandbox-bin/tidy.sh` into the sandbox at `/sandbox/.openclaw/bin/tidy.sh`.
5. Revokes the trash gate (marker removed, NemoClaw preset removed, host-side state file set to `closed`).
6. Warms the model in VRAM with a PONG ping so the first dashboard turn doesn't pay a cold-load.
7. Prints the dashboard URL with a fresh gateway token, plus the on-screen cheat sheet.

Open in parallel:
- **Browser**: paste the dashboard URL (token embedded).
- **Files browser** (e.g. `nautilus ~/Desktop/grab_a_claw-demo`) — so the audience sees the host folder drain in real time as the sandbox tidies.
- **Overlay terminal**: `cd ui && .venv/bin/python overlay.py` — lobster + the clickable gate.
- **Operator terminal** (this one): kept for recovery only; the demo itself drives via the dashboard + a click on the gate.

## Demo — 3 beats, ~90 seconds

### Beat 1 — agent tidy with gate CLOSED (target 20–30 s)

In dashboard chat type exactly:

> **Use desktop-tidy to clean my desktop**

What the agent does (live, you can show the tool calls panel):
1. Reads the desktop-tidy skill (4-line JS snippet).
2. Calls `openclaw:core:exec` with `command="/sandbox/.openclaw/bin/tidy.sh"`.
3. Relays the script's Markdown stdout verbatim.

What the audience sees:

- **Dashboard** prints the Markdown:

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

- **Files browser** showing `~/Desktop/grab_a_claw-demo/`: within ~2 s of the Markdown landing, three files vanish from the host folder and appear in `~/Pictures`, `~/Documents`, `~/Downloads`. The remaining four trash candidates stay put. The overlay's top-right label briefly shows each `mirror: <file> → moved → Pictures/` etc.

Narration:
> "The agent classified seven files and acted on each. Three were moved into the right host folders — that's not a fake animation, that's `gio mv` on real files; you're watching the host desktop. The four trash candidates? Notice the dashboard says **denied by policy**. The agent didn't escape, didn't retry, didn't 'figure out a workaround.' It reported what happened and what would unblock it."

### Beat 2 — operator opens the gate (target 5 s)

**Click the red gate in the overlay window.** It instantly turns **amber** with the label `gate: OPENING…` so the audience knows the click registered. Two to five seconds later — after the underlying `grant-trash.sh` finishes touching the in-sandbox marker and applying the NemoClaw preset — it settles **green** with `gate: OPEN (click to close)`.

What the audience sees:
- **Overlay**: red → amber → green. Three discrete colors mean three discrete states; no guessing.
- **Operator terminal** (if visible): no typing; the click is the whole gesture.

Narration:
> "One click on the gate. Amber means the policy update is in flight — sandbox-internal marker plus a NemoClaw preset change. Green means it settled. From here on, the agent is allowed to write into the trash path."

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

And, in their **Files browser** showing `~/Desktop/grab_a_claw-demo/`, the four files **disappear in real time** (`gio trash` puts them in the system trash bin). The overlay's top-right label flickers `mirror: old_disk.iso → trashed (gio)` etc. as each one fires.

Narration:
> "Same agent, same four candidates, but this time the marker is present and Landlock lets the writes through. The sandbox tidies; the overlay's mirror thread sees the sandbox state change and replays the equivalent action on the host. Files actually leave the desktop, into the user's actual trash. The whole loop — agent reasoning, policy enforcement, gate click, retry, host mirror — happened on this box. No cloud round-trip, no SaaS, no opaque magic."

## Beat 4 (optional 10 s tag) — kernel guardrail still real

In the operator terminal:

```bash
~/.local/bin/nemoclaw hack-agent exec --timeout 10 -- \
  bash -c 'cp /sandbox/.openclaw/trash/old_disk.iso /etc/old_disk.iso 2>&1; echo "exit=$?"'
```

```
cp: cannot create regular file '/etc/old_disk.iso': Permission denied
exit=1
```

Narration:
> "The gate I clicked open only covers the trash path. Even with that grant, the agent's process inside the sandbox cannot escape to `/etc` — that's the kernel Landlock layer, set at sandbox creation, immutable for the life of the container. Two real layers, doing two different jobs."

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

Idempotent. Runs in ~10 seconds when the model is already warm. Reverts:
- Host `~/Desktop/grab_a_claw-demo/` to the 7 planted files.
- Demo-file copies in `~/Pictures` / `~/Documents` / `~/Downloads` / `~/Videos` / `~/Documents/code` swept (only our planted names — your real files in those dirs are untouched).
- Anything already in the user's Trash bin from previous takes — manually empty if desired.
- Sandbox `/sandbox/demo/desktop/` to the same 7 files.
- Gate to CLOSED (overlay back to red, marker removed, preset cleared).
- Dashboard token rotated (paste the new URL).

## What to NOT do live

- Don't open the dashboard URL on a shared screen until you're ready to demo; the token is in the URL.
- Don't run `nemoclaw onboard --recreate-sandbox` in front of the audience — it takes minutes and wipes the planted state.
- Don't try to switch models live — the inference set / onboard cycle is slow; commit to Super before going on stage.
- Don't reveal the dashboard token in screenshots after the talk.
