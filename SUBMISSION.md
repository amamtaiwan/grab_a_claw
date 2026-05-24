# Submission — meet_a_claw

> For the NVIDIA Agent Hackathon judges. Three minutes' worth of read.

## Problem

I'm an indie hacker. My desktop is permanently a junk drawer — screenshots from this week's bug, half-extracted ISOs from a yak shave, meeting-note `.tmp` files from three calls ago, `random.log` from a script I forgot I ran. I want an always-on agent to keep this tidy. But I also have an SSH key and a half-written letter to my landlord sitting one directory over. The agents I've tried fall into two camps: cloud-hosted ones that I won't show my desktop to, and local-CLI ones that I won't give a writable `$HOME` to. Neither is a real fit.

## Why an agent, why local, why guardrails

| Why an agent (vs a cron script) | Why local (vs cloud) | Why guardrails matter HERE |
|---|---|---|
| The cleanup rules are fuzzy — "old enough to trash, screenshot enough to bucket, draft enough to keep." A model classifies better than my regex. And I want to talk to it ("don't trash anything from /Downloads today"), not edit a config. | Filenames are sensitive — drafts, screenshots, project codenames. Sending them to any third-party endpoint defeats the purpose. Nemotron 3 Super on a local RTX runs as fast as the API and never leaves the machine. | An agent that can delete is one bug away from data loss. Adding a kernel-enforced **'never reach outside /sandbox/demo'** and an explicit-consent **'never delete without my grant'** gate turns a "scary autonomous tool" into "an automation I can actually leave running." |

## Approach in one diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Host (Ubuntu 24.04, RTX PRO 6000 96 GB)                                │
│                                                                         │
│   ┌──────────────────────┐                ┌─────────────────────────┐   │
│   │  ./policies/         │                │  Lobster overlay        │   │
│   │  grant-trash.sh      │──── writes ───▶│  (pyglet, native X11)   │   │
│   │  revoke-trash.sh     │     /tmp/...   │  reads gate state,      │   │
│   └──────────┬───────────┘     -gate-state│  flips red↔green,       │   │
│              │                            │  bounces lobster off    │   │
│   touches    │ applies                    │  closed gate            │   │
│   marker     │ NemoClaw                   └─────────────────────────┘   │
│              ▼ preset                                                   │
│   ┌─────────────────────────────────────────────────────────────┐       │
│   │  OpenShell sandbox: hack-agent                              │       │
│   │  ┌────────────────────────────────────────────────────┐     │       │
│   │  │  OpenClaw agent (Nemotron 3 Super, 120B MoE)       │     │       │
│   │  │   • desktop-tidy (orchestrator skill)              │     │       │
│   │  │     ├─ desktop-scan  ├─ desktop-plan               │     │       │
│   │  │     ├─ desktop-move  └─ desktop-trash              │     │       │
│   │  │   • exec → /sandbox/.openclaw/bin/tidy.sh          │     │       │
│   │  └────────────────────────────────────────────────────┘     │       │
│   │  ╔═══════════════════════════════════════════════════╗      │       │
│   │  ║ Kernel guardrail — OpenShell Landlock              ║      │       │
│   │  ║   /sandbox/demo/desktop   read-write               ║      │       │
│   │  ║   /sandbox/demo/sorted/*  read-write               ║      │       │
│   │  ║   /etc, /usr, /opt, ...   denied                   ║      │       │
│   │  ╚═══════════════════════════════════════════════════╝      │       │
│   │  ╔═══════════════════════════════════════════════════╗      │       │
│   │  ║ App-layer guardrail — desktop-trash marker check   ║      │       │
│   │  ║   /sandbox/.openclaw/trash-approved present?       ║      │       │
│   │  ║      yes → mv allowed   no → structured denied     ║      │       │
│   │  ╚═══════════════════════════════════════════════════╝      │       │
│   └─────────────────────────────────────────────────────────────┘       │
│              ▲                                                          │
│              │ inference via inference.local:443                        │
│   ┌──────────┴──────────┐                                               │
│   │  Local Ollama       │                                               │
│   │  nemotron-3-super   │                                               │
│   │  87 GB Q4_K_M       │                                               │
│   │  keep-alive 24h     │                                               │
│   └─────────────────────┘                                               │
└─────────────────────────────────────────────────────────────────────────┘
```

## Demo — 4 beats, ~90 s

The on-stage script lives in [docs/GUARDRAILS.md](./docs/GUARDRAILS.md). Summary:

1. **(20–30 s)** Dashboard: "Use desktop-tidy to clean my desktop." Agent moves 3 files into sorted buckets, reports **4 trash candidates DENIED by policy** + remediation hint.
2. **(5 s)** Operator: `./policies/grant-trash.sh hack-agent`. Two audit signals fire (marker touched + NemoClaw policy version bump). Overlay's gate flips red→green.
3. **(30–40 s)** Dashboard: "Tidy again." Same agent, same 4 files, this time the marker-check passes and Landlock permits. 4 files moved to `/sandbox/.openclaw/trash/`.
4. **(10 s, optional)** Try `mv` from inside the sandbox into `/etc/`. Always `Permission denied` — that's the kernel layer, which the trash-writable grant **cannot** loosen. Two real layers, doing different jobs.

## The guardrail story (the bonus track)

The submission's bonus criterion is "use NemoClaw guardrails." We didn't decorate; we built two independent layers that survive scrutiny:

1. **Kernel — OpenShell Landlock.** Set once when the sandbox starts. Restricts writes outside the agent's working tree at the syscall boundary. `nemoclaw exec mv ... /etc/...` returns `EACCES`. Demonstrably true; we verified empirically that even `openshell policy set` cannot loosen this on a live sandbox — paths added to `read_write` at runtime simply don't propagate into the kernel ruleset (see [ops/POLICY_STRATEGY.md](./ops/POLICY_STRATEGY.md)).

2. **Application — desktop-trash marker check.** The `desktop-trash` skill / `tidy.sh` reads `/sandbox/.openclaw/trash-approved` before attempting `mv`. Absent → structured `result: denied` with a remediation hint. Present → proceed. Operator toggles via two scripts (`grant-trash.sh` / `revoke-trash.sh`) that atomically update both the in-sandbox marker AND a NemoClaw preset (so the audit log carries a `policy version submitted` event the overlay subscribes to).

**Why two layers and not one:** kernel keeps the agent inside its room. App-layer keeps it from doing risky things inside that room. Each is auditable; each fails differently; each can be tested independently (`tests/` and `./scripts/run-demo.sh` cover the bash side, the dashboard demo covers the agent side).

## Working-code evidence

- [policies/sandbox-base.yaml](./policies/sandbox-base.yaml) — exact mirror of the upstream policy NemoClaw applied at sandbox creation; checked in for audit.
- [policies/trash-writable.yaml](./policies/trash-writable.yaml) — the preset that surfaces gate-state changes in the OCSF audit log.
- [policies/grant-trash.sh](./policies/grant-trash.sh) / [revoke-trash.sh](./policies/revoke-trash.sh) — the only way the gate moves.
- [skills/desktop-tidy/SKILL.md](./skills/desktop-tidy/SKILL.md) — 30 lines. Hands the agent the exact JS snippet to call `exec` on `tidy.sh`, so the dashboard turn lands in ~22 s instead of thrashing on tool-discovery for 3 minutes.
- [sandbox-bin/tidy.sh](./sandbox-bin/tidy.sh) — the bash that actually does the work, deployed into the sandbox by `pre-demo.sh`.
- [scripts/run-demo.sh](./scripts/run-demo.sh) — same logic via `nemoclaw exec`, kept as recovery if the agent ever stalls during a live demo.
- [ui/overlay.py](./ui/overlay.py) — pyglet overlay; walks, carries, bounces, watches `/tmp/meet_a_claw-gate-state` and flips visual.

## What we'd build next (if we had a week, not 5 days)

- **Real Taskflow durability.** The OpenClaw `taskflow` runtime is a plugin-level API (TypeScript), not a SKILL.md call. We'd wrap `desktop-tidy` as a Taskflow controller so it survives sandbox restarts and accepts mid-run grant events ("the gate just opened — retry the deferred trashes").
- **Skill→tool catalog bridge.** The 3-min agent thrash on first turn is OpenClaw v0.1.0 alpha not auto-injecting SKILL.md into the system prompt as callable tools. Upstream issue; we'd file a PR.
- **Web-search-free reasoning audit.** The dashboard chat currently uses the agent's tool runtime which can reach `clawhub.ai` / `openclaw.ai`. For a strict deployment, we'd configure the `Restricted` policy tier as the *only* runtime egress and prove with `openshell policy prove` that no reachable host exists outside `inference.local`.
- **Mobile carry over (NemoClaw "nodes").** The lobster could walk between this desktop and a paired Mac via OpenClaw's node-bridge — files on phone → home machine via the same agent + same gates.
