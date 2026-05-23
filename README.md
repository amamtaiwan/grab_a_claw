# meet_a_claw

> An always-on local AI agent that organizes your desktop — embodied as a Q-version mascot (lobster 🦞 or Jensen 🤓), with a NemoClaw-policy-enforced trash gate.

NVIDIA Agent Hackathon submission, due **2026-05-28**.

## The 30-second pitch

You ask the claw to clean up your desktop. It scans your files, proposes a plan, then walks (literally — on-screen) to each file, carries it to where it belongs, and drops it there. When it tries to drag a file toward the trash can, **a physical gate stops it** — unless you've granted the agent explicit permission to delete. The gate isn't a UI illusion; it's [NemoClaw's filesystem policy](./policies/filesystem.yaml) refusing the syscall. We turned policy enforcement into gameplay.

## Why this shape

- **Local & always-on.** Your desktop is sensitive — file names, project drafts, screenshots of half-written messages. Running a 120B-parameter Nemotron 3 Super agent **on the user's GPU** means none of that touches the cloud.
- **Embodied.** The animated character makes the agent's behavior auditable to non-technical users. You see what it's about to move, you see when it's blocked, you see why.
- **Guardrails as gameplay.** Most agent demos show "the policy blocked something" via a log line. We show it via a closed gate that bounces the lobster back. Same enforcement, but humans can see it without reading YAML.

## Stack

| Layer | Choice | Why |
|---|---|---|
| Sandbox | [NemoClaw](https://github.com/NVIDIA/NemoClaw) v0.1.0 + [OpenShell](https://docs.nvidia.com/openshell/) | NVIDIA reference stack; sandbox is the agent's body |
| Agent runtime | [OpenClaw](https://openclaw.ai) v2026.5.18 | multi-channel agent framework; runs *inside* the sandbox |
| Inference | [Nemotron 3 Super](https://ollama.com/library/nemotron-3-super) (120B MoE, 12B active) via Ollama, local | strong reasoning, fits on a single RTX PRO 6000 96GB |
| Guardrails | NemoClaw `policies/*.yaml` + OpenShell Landlock | the **bonus track** of this submission |
| Animation | TBD — see [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) | <!-- TODO: pick Electron / Tauri / native X11 overlay --> |
| Persistence | SQLite | for run history & the agent's memory of "where things usually go" |

## How to run

<!-- TODO: fill once Phase 4/5 done -->
```bash
# Bring the claw to life
nemoclaw hack-agent dashboard-url
# (open the URL in a browser, say "tidy up")

# In another terminal: watch the gate audit log
tail -f ~/.nemoclaw/audit/hack-agent.ocsf.log | grep -E 'FS:DENY|NET:DENY'
```

## Repo layout

```
meet_a_claw/
├── policies/        NemoClaw guardrail policies (the bonus track)
│   ├── network.yaml         which hosts the agent can reach
│   ├── filesystem.yaml      which paths it can read/write — Trash is special
│   └── README.md
├── skills/          OpenClaw custom skills (the agent's tools)
│   ├── scan_desktop/        list files + classify
│   ├── propose_plan/        ask Nemotron where each file should go
│   ├── move_file/           perform a move (subject to filesystem policy)
│   └── request_trash/       ask to delete — bounces off gate unless policy preset granted
├── tasks/           Autonomous task definitions via Taskflow
│   ├── self_check.yaml      stack health + disk-pressure trigger
│   └── desktop_watch.yaml   re-organize when desktop gets cluttered
├── ui/              The animated mascot (Q-lobster or Q-Jensen)
├── tests/           Working-code evidence the judges asked for
└── docs/
    ├── ARCHITECTURE.md      how the agent talks to the animation layer
    └── GUARDRAILS.md        the violation demo script (the climax)
```

## License

<!-- TODO -->
