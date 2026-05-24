# meet_a_claw

> An always-on local AI agent that tidies your desktop — embodied as a Q-version lobster mascot 🦞 — with a NemoClaw policy-enforced trash gate the agent literally cannot punch through.

NVIDIA Agent Hackathon submission, due **2026-05-28**.

## The 30-second pitch

I'm an indie hacker. My desktop fills up with screenshots, ISOs, half-written meeting notes, and `.tmp` files from every prototype I touch. I want an always-on local agent to keep it organized — but I don't trust any agent enough to give it root. One stray `rm` and my SSH keys are gone.

**meet_a_claw** is what you build when both halves of that sentence matter. A 120B local Nemotron sorts files into the right buckets. A NemoClaw policy gate refuses to let the agent delete anything unless I explicitly say so. An on-screen lobster watches the gate flip and bounces off it when it's closed, so I can see what the agent tried to do and why it couldn't.

## Why this shape

- **Local & always-on.** Your desktop is sensitive — file names, screenshots of half-written DMs, project drafts. Running [Nemotron 3 Super](https://ollama.com/library/nemotron-3-super) (120B MoE, 12B active) **on your own GPU** means none of that touches the cloud.
- **Policy-gated, not just policy-decorated.** Most "AI agent + policy" pitches mean a system prompt that politely asks the LLM not to do bad things. We layer two real mechanisms: **OpenShell Landlock** at the kernel for "you can't escape the sandbox," and a **NemoClaw policy preset** + sandbox-internal marker check for "you can't delete inside the sandbox without my consent."
- **Guardrails as gameplay.** Most agent demos show "the policy blocked something" via a log line. meet_a_claw shows it via a closed gate that bounces the lobster back when it tries to drag a file in. Same enforcement, but humans (and judges) see it without reading YAML.

## What's in the box

| Layer | Choice | Why |
|---|---|---|
| Sandbox | [NemoClaw](https://github.com/NVIDIA/NemoClaw) v0.1.0 + [OpenShell](https://docs.nvidia.com/openshell/) 0.0.44 | NVIDIA reference stack; sandbox is the agent's body |
| Agent runtime | [OpenClaw](https://openclaw.ai) v2026.5.18 | multi-channel agent framework; runs *inside* the sandbox |
| Inference | [Nemotron 3 Super](https://ollama.com/library/nemotron-3-super) (120B MoE, 12B active, Q4_K_M, 87 GB) via local Ollama | strong enough to follow nuanced skill rules; Nano-8B couldn't |
| Guardrails | NemoClaw `policies/*.yaml` + sandbox-internal marker + OpenShell Landlock | **the bonus track** of this submission |
| Animation | Python + [pyglet](https://pyglet.org) 2.1, native X11 overlay | "on your desktop" feel; runs against the actual host display |
| Persistence | SQLite (planned), `/sandbox/.openclaw/trash/` for trashed files | the sandbox keeps its own history of what it did |

## How to run

Prereqs: a Linux box with Docker, an NVIDIA GPU, [NemoClaw installed](https://www.nvidia.com/nemoclaw.sh) (the installer pulls Nemotron into Ollama for you).

```bash
# 1. Clone and enter the repo.
cd meet_a_claw

# 2. Set up the overlay's Python env (one-time).
python3 -m venv ui/.venv
ui/.venv/bin/pip install -r ui/requirements.txt

# 3. Install the agent's skills into the sandbox.
for s in desktop-scan desktop-plan desktop-move desktop-trash desktop-tidy; do
  nemoclaw hack-agent skill install ./skills/$s
done

# 4. Run the 60-second pre-flight (replants demo files, revokes the gate,
#    warms the model, prints the dashboard URL + on-screen cheat sheet).
./scripts/pre-demo.sh hack-agent

# 5. In a second terminal, launch the lobster overlay.
cd ui && .venv/bin/python overlay.py
```

Open the dashboard URL `pre-demo.sh` printed, and in the chat type:

```
Use desktop-tidy to clean my desktop
```

The agent will tidy three files into their sorted buckets, then report the four trash candidates as **denied by policy**. To open the gate:

```bash
./policies/grant-trash.sh hack-agent
```

The overlay's red gate flips green; ask the agent to tidy again and the four trash candidates land in `/sandbox/.openclaw/trash/`.

Full live-demo script (4 beats, ~90 s with narration) is in [docs/GUARDRAILS.md](./docs/GUARDRAILS.md).

## Repo layout

```
meet_a_claw/
├── policies/                  Guardrail policies + operator gate toggles
│   ├── sandbox-base.yaml      Stock upstream policy, kept for audit (read-only)
│   ├── trash-writable.yaml    The preset that opens the trash gate
│   ├── grant-trash.sh         Apply preset + touch sandbox marker + signal overlay
│   ├── revoke-trash.sh        Reverse of grant-trash.sh
│   └── README.md
├── skills/                    OpenClaw skills — SKILL.md format, Markdown only
│   ├── desktop-scan/          List + classify files on /sandbox/demo/desktop
│   ├── desktop-plan/          Propose action per file (move / trash / leave alone)
│   ├── desktop-move/          Atomic mv, policy enforced
│   ├── desktop-trash/         Marker-checked mv to /sandbox/.openclaw/trash/
│   └── desktop-tidy/          Orchestrator — one tool call, one Markdown report
├── sandbox-bin/
│   └── tidy.sh                The script desktop-tidy points at (lives inside the sandbox)
├── scripts/
│   ├── pre-demo.sh            60s pre-flight before a live pitch
│   └── run-demo.sh            Recovery — identical Markdown via direct bash if agent stalls
├── ui/
│   ├── overlay.py             pyglet overlay: walk, carry, bounce, gate watcher
│   ├── assets/sprites/        Twemoji lobster (CC-BY 4.0)
│   └── requirements.txt
├── ops/
│   └── POLICY_STRATEGY.md     Why two layers, what we tried that didn't work
└── docs/
    ├── ARCHITECTURE.md        Stack diagram + the open decisions
    └── GUARDRAILS.md          Live demo script (3+1 beats with narration)
```

## License

Apache-2.0 — matches NemoClaw upstream. See [LICENSE](./LICENSE) once added.
