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

### D1. Animation layer technology

| Option | Pros | Cons |
|---|---|---|
| **Electron** | Easy to draw cute character + run anywhere on the screen, mature toolchain | Heavy binary (~150 MB), slow startup |
| **Tauri** (Rust + webview) | ~10 MB binary, modern stack, web-tech UI | Less ecosystem for "on-desktop pet" libraries |
| **Native X11 transparent overlay** (Python + GTK or pyglet) | Truly draws *on* the desktop, can sit above all windows | X11-specific (we're on Ubuntu, GNOME defaults to Wayland; need to confirm session type or force X11) |
| **Browser tab** (just a webpage) | Zero setup, easiest dev | Lives inside a window, not "on the desktop" — loses the embodied feel |

<!-- TODO: pick one. Recommend Tauri for binary size + cross-platform optionality.
     Recommend native X11 if the "feels physically on my desktop" effect is the core of the demo. -->

### D2. Agent ↔ animation communication

The animation needs to know (a) where the mascot should walk to, (b) what file it's carrying, (c) whether a policy just allowed or denied something.

| Option | Notes |
|---|---|
| **WebSocket server in animation app, agent skill POSTs** | Lowest latency; needs network policy to allow the loopback port |
| **Unix domain socket** | No network policy needed; sandbox needs the socket bind-mounted in |
| **Tail OCSF audit log file from animation** | Single source of truth = the audit log. Beautiful for the "see what the policy did" story. Slight latency from log flush. |

<!-- TODO: pick one. Audit-log-tail has the strongest demo story; combine with a
     direct skill→animation channel for low-latency "walk to (x,y)" commands. -->

### D3. Character art

- **Lobster (claw mascot)** — matches `OpenClaw` / `NemoClaw` / `meet_a_claw` name puns. Original design needed.
- **Q-version Jensen Huang** — appeals to NVIDIA judges directly. Caricature — need to be careful about likeness/parody handling for a public submission.
- **Both, user-selectable** — fun bonus. Adds ~1 evening of work.

<!-- TODO: pick one. -->
