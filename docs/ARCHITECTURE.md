# Architecture

## Layers

```
┌───────────────────────────────────────────────────────────────┐
│  Host (Ubuntu 24.04, RTX PRO 6000 96GB)                       │
│                                                               │
│  ┌─────────────┐         ┌──────────────────────────────┐     │
│  │  Animation  │◀───────▶│   Ollama (host)              │     │
│  │  layer      │  events │   nemotron-3-super:latest    │     │
│  │  (Q-mascot) │         │   :11434 (raw)               │     │
│  └─────────────┘         │   :11435 (auth proxy)        │     │
│        ▲                 └──────────────────────────────┘     │
│        │                                ▲                     │
│  reads OCSF audit log                   │  inference          │
│        │                                │                     │
│  ┌─────┴───────────────────────────────────────────────┐      │
│  │  OpenShell sandbox  (hack-agent)                    │      │
│  │  ┌───────────────────────────────────────────┐      │      │
│  │  │  OpenClaw agent (Nemotron-backed)         │      │      │
│  │  │   ├─ skills/scan_desktop                  │      │      │
│  │  │   ├─ skills/propose_plan                  │      │      │
│  │  │   ├─ skills/move_file                     │      │      │
│  │  │   └─ skills/request_trash  ← gate target  │      │      │
│  │  └───────────────────────────────────────────┘      │      │
│  │   Landlock (filesystem)  +  net-policy (network)    │      │
│  └─────────────────────────────────────────────────────┘      │
└───────────────────────────────────────────────────────────────┘
```

## Decisions still open (Phase 3 hand-off)

These three choices shape Phase 4. Each is reversible but cheaper to nail early.

### D1. Animation layer technology — **picked: Python + pyglet 2.1, native X11 borderless overlay**

Why: the demo's core argument is "the policy stopped a real action on the user's real desktop." Drawing inside a regular browser tab undermines that — the overlay needs to feel native. Tauri or Electron would have worked but bigger binary and slower iteration. pyglet 2.1's GL-backed sprite/shape pipeline keeps the lobster + gate at 60 fps with negligible CPU; the trade-off is X11-only, which is fine because the demo machine runs Ubuntu 24.04 with an X11 session (verified `XDG_SESSION_TYPE=x11`).

### D2. Agent ↔ animation communication — **picked: filesystem watcher + sandbox-state polling**

Two channels, both file-based, both auditable:
- **Gate state**: the host-side `/tmp/grab_a_claw-gate-state` file written by `grant-trash.sh` / `revoke-trash.sh`. The overlay watches it with `watchdog.observers.polling.PollingObserver` (500 ms interval — avoids inotify saturation on dev boxes with lots of file watchers). When the file changes, the overlay flips the gate visual.
- **Mirror trigger**: a daemon thread polls the sandbox via `docker exec ls` every ~1.5 s, looking for new files in `/sandbox/demo/sorted/<bucket>/` and `/sandbox/.openclaw/trash/`. For each unseen sandbox arrival, it mirrors the equivalent host action (`shutil.move` or `gio trash`).

We considered WebSockets / unix sockets for lower latency, but the polling overhead is invisible at human scale and the filesystem channel doesn't need NemoClaw network policy carve-outs.

### D3. Character art — **picked: Twemoji lobster (🦞, U+1F99E)**

CC-BY-4.0, render-as-PNG-at-2× via pyglet, attribution in `ui/assets/sprites/ATTRIBUTION.md` and the project LICENSE. Replaceable: the overlay only loads one sprite file from `assets/sprites/`; a custom lobster (or Q-Jensen) could swap in by replacing that PNG, no code change.
