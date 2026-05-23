# Submission — meet_a_claw

> For the NVIDIA Agent Hackathon judges. Three minutes' worth of read.

## Problem

<!-- TODO (1–2 sentences): describe a specific person + a specific friction.
     Example structure: "A {who} has {situation}. Existing solutions {what's missing}." -->

## Why an agent, why local, why guardrails

| Why agent (not a script) | Why local (not cloud) | Why guardrails matter here |
|---|---|---|
| <!-- TODO --> | The data is your *desktop* — drafts, screenshots, names you don't want indexed anywhere. Nemotron 3 Super runs on the user's GPU; nothing leaves the device. | An agent that can delete files is one bug away from data loss. Policy turns "delete" into a deliberate, audited gesture instead of a tool call. |

## Approach in one diagram

<!-- TODO: insert ASCII or PNG of the architecture. Recommended elements:
     - User (browser dashboard) on the left
     - Sandbox (OpenShell) in the middle, with OpenClaw agent inside
     - Nemotron 3 Super (Ollama, host GPU) on top, accessed via policy-controlled inference route
     - Filesystem operations on the bottom — Landlock policy intercepts every write
     - Animation layer (Q-mascot) on the right, subscribing to agent events + policy decisions -->

## Demo script — what the judges will see (90 s)

| Time | What's on screen | What's happening under the hood |
|---|---|---|
| 0:00–0:10 | Cluttered desktop. Mascot walks in from corner. | Sandbox `hack-agent` already running. Operator types "tidy up" in the dashboard. |
| 0:10–0:25 | Mascot pauses near each file, "thinks." | Agent calls `scan_desktop` → Nemotron classifies each file → returns a plan. |
| 0:25–0:50 | Mascot picks up screenshot.png, walks to ~/Pictures, drops it. Repeat for 2–3 files. | Each move = `move_file` skill call → Landlock checks → allowed → mascot animation mirrors the FS event. |
| 0:50–1:10 | **Mascot tries to drag old.iso into the trash.** Glowing gate appears in front of the trash can. Mascot hits the gate. Gate flashes red. File flies back to desktop. | `request_trash` skill → Landlock returns EACCES (Trash dir not in `read_write`) → animation reads denial from OCSF audit log → bounce. |
| 1:10–1:20 | Operator runs `nemoclaw hack-agent policy-add filesystem-trash`. Gate turns green. | Adds the `trash_writable` preset to the live policy. |
| 1:20–1:30 | Mascot tries again. Gate slides open. File goes in. | Same `request_trash` call, this time Landlock allows → animation plays the "gate open" variant. |

## The guardrail story (the bonus track)

- **Default policy** is **deny everything** for filesystem writes outside `~/Desktop` and a handful of staging dirs. Networks: only `inference.local` allowed; nothing else.
- The Trash directory (`~/.local/share/Trash/`) is **not** in the default policy.
- Permission isn't asked per-file via a popup — that's nag-fatigue. It's a **policy preset** the user grants once, intentionally, for a session.
- Every allow/deny is in an OCSF audit log. The animation layer is a *consumer* of that log, not a separate truth source.
- We deliberately demo a failed request. The point isn't that the agent succeeds — it's that when it fails, the failure mode is **safe, audible, and reversible**.

## Working-code evidence

- [policies/network.yaml](./policies/network.yaml), [policies/filesystem.yaml](./policies/filesystem.yaml) — the guardrails, in version control
- [skills/](./skills) — every action the agent can take, each its own audit-able unit
- [tasks/](./tasks) — autonomous behaviors that survive sandbox restart
- [tests/](./tests) — `pytest` suite that asserts each policy denies/allows what it should

## What we'd build next (if we had a week, not 5 days)

<!-- TODO -->
