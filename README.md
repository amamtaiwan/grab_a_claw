# grab_a_claw

> A local AI agent that tidies your real Ubuntu desktop — embodied as a Q-version lobster mascot 🦞 walking across the screen — with a NemoClaw policy-enforced trash bin the agent literally cannot punch through.

NVIDIA Agent Hackathon submission · due **2026-05-28** · Apache-2.0.

---

## The 30-second pitch

I'm an indie hacker. My desktop fills up with screenshots, ISOs, half-written meeting notes, and `.tmp` files from every prototype I touch. I want an always-on local agent to keep it organised — but I don't trust any agent enough to give it root. One stray `rm` and my SSH keys are gone.

**grab_a_claw** is what you build when both halves of that sentence matter. A 120B Nemotron 3 Super running on my own GPU sorts files into the right buckets and emits canonical move/trash intents. A NemoClaw policy gate refuses to let the agent delete anything unless I tap the on-screen trash bin to unlock it. An animated lobster walks across the real desktop, carries the file, and bounces off the red bin when it's locked — same enforcement as a YAML deny line, but humans (and judges) see it without reading audit logs.

## Why this shape

- **Local & always-on.** Your desktop is sensitive — file names, screenshots of half-written DMs, project drafts. Running Nemotron 3 Super (120B MoE, 12B active) **on your own GPU** means none of it touches the cloud.
- **Policy-gated, not just policy-decorated.** Most "AI agent + policy" pitches mean a system prompt that politely asks the LLM not to do bad things. We layer two real mechanisms:
  - **OpenShell Landlock** at the kernel boundary — the agent literally cannot escape the sandbox.
  - **NemoClaw policy preset + sandbox-internal marker check** — destructive ops (`gio trash`) need the operator to flip the on-screen bin from red to green.
- **Guardrails as gameplay.** Most agent demos show "the policy blocked something" via a log line. grab_a_claw shows it via a red trash bin that flashes when the agent tries to throw a file in, while the lobster recoils. Same audit signal, visible enforcement.

## What's in the box

| Layer | Choice | Notes |
|---|---|---|
| Sandbox | [NemoClaw](https://github.com/NVIDIA/NemoClaw) v0.1.0 + [OpenShell](https://docs.nvidia.com/openshell/) 0.0.44 | NVIDIA reference stack; sandbox is the agent's body |
| Agent runtime | [OpenClaw](https://openclaw.ai) v2026.5.18 | runs *inside* the sandbox, talks OpenAI-compatible /v1 to inference |
| Inference | Nemotron 3 Super 120B-A12B (Q4_K_M, ~87 GB VRAM) via local Ollama | reasoning mode `medium`; compact tool catalog **disabled** (`tools.toolSearch=false`) so the agent sees real tools instead of meta-search |
| Skills | `desktop-tidy` + `desktop-arrange` (SKILL.md, lookup-table format) | the agent's "vocabulary"; canonical JSON intents only |
| Intent broker | `ui/overlay.py::DesktopArrangeBroker` | sandbox proposes (writes JSON intent file inside container), host disposes (broker reads it via `docker exec`, runs `gio set` / `gio trash`); sandbox **never** touches host filesystem directly |
| Guardrails | NemoClaw `policies/*.yaml` + sandbox-internal marker (`/sandbox/.openclaw/trash-approved`) + OpenShell Landlock | dual-layer; details in [docs/GUARDRAILS.md](./docs/GUARDRAILS.md) |
| Overlay | Python 3.12 + [pyglet](https://pyglet.org) 2.1, native X11 desktop layer | transparent, click-through except the trash bin; runs against the actual host display |

## Hardware requirements

| | |
|---|---|
| OS | Ubuntu 24.04 (or any Linux with kernel ≥ 6.1 for Landlock) |
| GPU | **96 GB** for Super 120B BF16 quantised (RTX PRO 6000 Blackwell / H100 / equivalent). The 87 GB GGUF + KV cache + overlay headroom fits comfortably; tighter cards need the FP8 or NVFP4 variant. |
| RAM | 64 GB recommended (Ollama + Docker + browser + display server) |
| Disk | 100 GB free for the GGUF, sandbox image, and demo state |
| Display | X11 session (the overlay uses `_NET_WM_WINDOW_TYPE_DESKTOP` + SHAPE extension; Wayland support is not wired) |

## Setup

Prereqs: a Linux box with Docker (your user in the `docker` group, so the overlay broker can `docker exec` into the sandbox), an NVIDIA GPU + driver ≥ 575, [NemoClaw installed](https://www.nvidia.com/nemoclaw.sh) (the installer pulls Nemotron-3-Super into Ollama for you).

```bash
# 1. Clone.
git clone https://github.com/<your-fork>/grab_a_claw.git
cd grab_a_claw

# 2. Set up the overlay's Python env (one-time).
python3 -m venv ui/.venv
ui/.venv/bin/pip install -r ui/requirements.txt

# 3. Install the two agent skills into the sandbox.
nemoclaw hack-agent skill install ./skills/desktop-tidy
nemoclaw hack-agent skill install ./skills/desktop-arrange

# 4. Disable the openclaw native "compact tool catalog" so the agent
#    sees real tools instead of meta tool_search/describe/call. (Without
#    this, Nemotron thrashes on tool discovery 10+ rounds per request.)
SBX=$(docker ps --filter name=openshell-hack-agent --format '{{.Names}}' | head -1)
docker exec --user sandbox -e HOME=/home/sandbox \
  -e OPENCLAW_CONFIG_PATH=/sandbox/.openclaw/openclaw.json \
  "$SBX" openclaw config set tools.toolSearch false

# 5. (Optional) enable mild CoT for steadier schema-following.
docker exec --user sandbox -e HOME=/home/sandbox \
  -e OPENCLAW_CONFIG_PATH=/sandbox/.openclaw/openclaw.json \
  "$SBX" openclaw config set agents.defaults.thinkingDefault medium

# 6. Bounce openclaw so the config changes take effect.
docker exec --user 0 "$SBX" pkill -9 -f '^openclaw$'
sleep 5
docker exec --user 0 "$SBX" pgrep -af openclaw | head -2   # confirm respawn

# 7. Run the 60-second pre-flight (stashes your real desktop, plants the
#    7 demo files at known positions, revokes the trash gate, warms
#    Nemotron, prints the dashboard URL + cheat sheet).
./scripts/pre-demo.sh hack-agent

# 8. In a second terminal, launch the lobster overlay.
ui/.venv/bin/python ui/overlay.py
```

You should now see, on the real desktop:
- 7 demo files planted along a row (draft.pdf, empty_file.txt, old_disk.iso, random.log, screenshot_2026-05-20.png, tax_receipts_2024.zip, temp_notes.tmp)
- 5 sorted-target folders below them (Images, Documents, Archives, Code, Media)
- A 🦞 lobster sprite at the top-left, and a **red trash bin** at the top-right with a small "trash: LOCKED" label

The terminal where `overlay.py` runs prints `[broker] ...` lines whenever the agent queues an intent. Watch it during the demo.

## Live demo (3 paths × ~90 seconds)

`pre-demo.sh` prints the same cheat sheet, formatted with your live dashboard URL + token. Open the dashboard, start a fresh chat session, and type:

### A. Bulk tidy with a closed trash gate (`desktop-tidy` skill)



https://github.com/user-attachments/assets/ba184782-f180-46f8-81c2-4b843e729432



```
Use desktop-tidy to clean my desktop
```

Expected: agent calls `openclaw:core:exec` once to run the sandbox-internal `/sandbox/.openclaw/bin/tidy.sh`. Three files move into the sorted folders; four trash candidates are **denied by policy** (the lobster runs at each one and bounces off the locked bin, which flashes bright red).

### B1. Single-file move via natural language (`desktop-arrange` skill)


https://github.com/user-attachments/assets/3db4d671-e13d-4fa4-a705-517ed408636f



```
Use desktop-arrange to move draft.pdf to upper-right.
```

Expected:
- The agent picks Row 1 of the SKILL.md lookup table and emits `{"action":"set_position","file":"draft.pdf","x":1440,"y":310}` via `openclaw:core:exec` (one tool call total).
- The overlay terminal prints `[broker] arrange_request draft.pdf → (1440,310) [deferred to drop]`.
- The lobster walks from HOME to draft.pdf, picks it up (page icon attached above the sprite), walks to the upper-right zone, and **only at the drop frame** the broker runs `gio set metadata::nautilus-icon-position 1440,310 && touch draft.pdf` — the icon visually appears at the new position the same instant the lobster drops it.
- The lobster then walks home.

### B2. Trash with the gate locked → bin flash + lobster bounce


https://github.com/user-attachments/assets/94c11648-9bbc-4478-b8c4-9c5bbc39e08b



```
Use desktop-arrange to trash temp_notes.tmp.
```

Expected:
- Broker prints `[broker] trash temp_notes.tmp BLOCKED (gate closed) — denied event queued`.
- The trash bin flashes **bright red** with label "trash: DENIED — bin is LOCKED" for ~0.8 s.
- The lobster picks up `temp_notes.tmp`, walks toward the bin, parks just before its left edge, and bounces back (80 px recoil + rotation).
- The file is **not** trashed; it stays on the desktop.

Now **click the bin** on the screen. It turns yellow (`trash: UNLOCKING…`) while `policies/grant-trash.sh` flips the policy + sandbox marker, then green (`trash: UNLOCKED`).

```
Use desktop-arrange to trash temp_notes.tmp.
```

Expected this time: lobster reaches the bin, drops the file in, broker runs `gio trash`, the file disappears from the desktop into XDG trash.

### B3. Compositional layout — broker meta-arrange fan-out


https://github.com/user-attachments/assets/3fd2f7ec-3569-48bb-80c4-a178dffc17bb



```
Use desktop-arrange to arrange all files A-Z in upper-right.
```

Expected:
- Agent emits a single high-level intent `{"action":"arrange","sort":"A-Z","column":"upper-right","rowPitch":130,"startY":180}`.
- Broker reads the sandbox-mirrored desktop file list, sorts A-Z, fans out into 7 individual `arrange_request` events (`[broker] meta-arrange: 7 file(s) ...` then 7 `[broker]   → arrange_request ...` lines).
- The lobster makes 7 trips, one per file, leaving them stacked in a column at the upper-right.

### Recovery if the agent stalls > 60 s

The 120B model occasionally falls into a tool-discovery loop on the first request after a restart. If you see `tool_search_code` errors in the chat ≥ 5 in a row, fire:

```bash
./scripts/run-demo.sh hack-agent
```

This runs the exact same Bash logic the agent would have run through `desktop-tidy`, producing identical Markdown output. The Landlock + marker enforcement are unchanged; you just bypassed Nemotron for that one beat. The remaining beats (B1/B2/B3) usually recover after that one warm-up.

### Reset between takes

```bash
./scripts/post-demo.sh
./scripts/pre-demo.sh hack-agent
```

`post-demo.sh` removes the demo files from `~/Desktop` and any host destination folders, then restores your original desktop files from `~/.grab_a_claw-stash/<timestamp>/`. Safe to re-run.

## Repo layout

```
grab_a_claw/
├── policies/                  Guardrail policies + operator gate toggles
│   ├── openclaw-sandbox.yaml  The sandbox's base policy (creation-locked)
│   ├── trash-writable.yaml    Preset that opens the trash gate
│   ├── grant-trash.sh         Apply preset + touch sandbox marker + signal overlay
│   ├── revoke-trash.sh        Reverse of grant-trash.sh
│   └── README.md
├── skills/                    OpenClaw skills — SKILL.md format, Markdown only
│   ├── desktop-tidy/          Bulk auto-classify (Path A)
│   └── desktop-arrange/       Natural-language move/trash/grid (Paths B1/B2/B3)
├── sandbox-bin/
│   └── tidy.sh                Sandbox-internal script that desktop-tidy points at
├── scripts/
│   ├── pre-demo.sh            60s pre-flight before a live pitch
│   ├── post-demo.sh           Restore the operator's real desktop
│   └── run-demo.sh            Recovery — identical Markdown via direct bash if agent stalls
├── ui/
│   ├── overlay.py             pyglet overlay: walk, carry, bounce, gate watcher, intent broker
│   ├── assets/sprites/        Twemoji lobster (CC-BY 4.0)
│   └── requirements.txt
├── ops/
│   └── POLICY_STRATEGY.md     Why two layers, what we tried that didn't work
├── train/                     Bonus track — LoRA fine-tune evaluation (see SUBMISSION.md)
│   ├── generate_sft_data.py   Builds 5000-sample ChatML dataset
│   ├── nano-peft-singlegpu.yaml  NeMo Automodel single-GPU recipe
│   └── chat_template_no_thinking.jinja
└── docs/
    ├── ARCHITECTURE.md        Stack diagram + the broker pattern in detail
    └── GUARDRAILS.md          Live demo script (3+1 beats with narration)
```

## Known issues & lessons learned

These bit us during development. We mention them so judges reproducing the demo aren't surprised:

1. **`NemotronH` PTX kernels need driver ≥ 575.** vLLM 0.17.1's bundled FlashAttention 2 and Flashinfer cubins target sm_120 Blackwell PTX that older drivers reject with `cudaErrorUnsupportedPtxVersion`. Workaround: `--attention-backend TRITON_ATTN --enforce-eager` (Triton JIT-compiles; no precompiled cubin).
2. **OpenClaw's "compact tool catalog" feature (default ON) breaks Nemotron tool use.** It hides real tools behind 3 meta-tools (`tool_search` / `tool_describe` / `tool_call`), and Nemotron's chat template has a known training quirk that makes it thrash on these. Step 4 in the setup disables it.
3. **CUDA toolchain split.** System nvcc is CUDA 13.0 but the PyTorch wheels we use are cu129 — compilations of `mamba_ssm` / `causal_conv1d` / `transformer_engine` need `CUDA_HOME=/usr/local/cuda-12.8` + CPATH pointing at the venv's `nvidia/cudnn/include` and `nvidia/nccl/include`. The bonus `train/` track documents the exact env.
4. **Single-trash-bin widget vs separate gate + zone.** Earlier drafts had a thin vertical gate at one screen location and a trash zone at another. We collapsed them into a single bin rectangle at the upper-right because two visual elements for one logical concept confused both the audience and the lobster's pathfinding.

## License

Apache-2.0 — matches NemoClaw upstream. See [LICENSE](./LICENSE).

The Twemoji lobster sprite is CC-BY 4.0 (Twitter / Twemoji project).
