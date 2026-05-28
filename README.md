> # ⚠️ DEMO-ONLY BRANCH — PROBABLY UNSAFE ⚠️
> **`demo-arch1-remote-inference`** splits the stack so the model runs on a
> remote workstation (over a Tailscale tunnel) while the sandbox + agent +
> overlay run on the booth DGX Spark. **This intentionally breaks the network
> isolation guarantee** that `main` relies on: the sandbox's inference egress
> is pointed at a remote endpoint instead of being locked to `inference.local`.
> Do NOT merge into `main`. Do NOT run outside the controlled GTC Taipei demo.
> See [docs/DEMO_ARCH1.md](./docs/DEMO_ARCH1.md) for the threat-model caveats.

---

# 🏆🦞 NVIDIA Agent Hackathon WINNER 🦞🏆

## 🎉 We won!! 🎉 Catch the live demo at **GTC Taipei — Thursday, June 4, 16:00** 🚀🇹🇼

---

# grab_a_claw

> A local AI agent that tidies your real Ubuntu desktop — embodied as a Q-version lobster mascot 🦞 walking across the screen — with a NemoClaw policy-enforced trash bin the agent literally cannot punch through.

🥇 **NVIDIA Agent Hackathon Winner** · 🎤 Live demo @ GTC Taipei, Thu Jun 4 @ 16:00 · Apache-2.0.

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

## Split architecture — what each machine runs

On this branch the stack runs across **two machines**, and only text crosses the
network (the inference request + the JSON intent — a few KB). Everything visual
and every guardrail runs locally on Machine B.

```
[ MACHINE A — home workstation, the 96 GB GPU ]        [ MACHINE B — booth box (NVIDIA GPU, Ubuntu 24.04) ]
  Ollama serving Nemotron 3 Super (+ Nano)      ← LAN / VPN →   NemoClaw sandbox + OpenClaw agent
  NemoClaw auth-proxy: token-gated /v1                          ui/overlay.py (the lobster) + 4K display
  on 0.0.0.0:11435  (already LAN-facing)          (text only)   sandbox inference → Machine A
```

| | Machine A (LLM server) | Machine B (desktop + agent + overlay) |
|---|---|---|
| Holds the model | ✅ Super in Ollama (`/usr/share/ollama`) | ❌ remote-only (pull Nano locally just as a fallback) |
| Runs the sandbox / agent | ❌ | ✅ NemoClaw + OpenShell + OpenClaw |
| Runs the lobster overlay + display | ❌ | ✅ drives the booth 4K monitor |
| Exposes on the network | token-gated `/v1` on `:11435` | nothing |

> ⚠️ Pointing Machine B's sandbox at a remote inference endpoint is exactly the
> network-isolation relaxation this branch is about — see
> [docs/DEMO_ARCH1.md](./docs/DEMO_ARCH1.md) for the threat model.

### Machine A — serve the model (run in your terminal)

```bash
# A1. Bring Ollama up (it holds Super + Nano). Needs sudo.
sudo systemctl start ollama && systemctl is-active ollama

# A2. Warm Super so the first remote turn isn't a cold ~90 GB load.
curl -s http://127.0.0.1:11434/api/generate \
  -d '{"model":"nemotron-3-super:latest","prompt":"PONG","stream":false}' >/dev/null

# A3. NemoClaw's auth-proxy already serves an OpenAI-compatible /v1 on
#     0.0.0.0:11435 (token-gated). Note these three for Machine B:
hostname -I | awk '{print $1}'        # MACHINE_A_IP  (LAN now; tailnet IP at the venue)
echo 11435                            # proxy port
cat ~/.nemoclaw/ollama-proxy-token    # bearer token  (treat as a secret — do not commit/share)

# A4. Confirm the LAN endpoint actually serves Super:
curl -s -H "Authorization: Bearer $(cat ~/.nemoclaw/ollama-proxy-token)" \
  "http://$(hostname -I | awk '{print $1}'):11435/v1/models"   # → should list nemotron-3-super:latest
```

(If you'd rather not deal with a token, bind Ollama to the LAN instead —
`sudo systemctl edit ollama` → `OLLAMA_HOST=0.0.0.0:11434` → restart — and have
Machine B use `http://MACHINE_A_IP:11434/v1` with any `apiKey`. Simpler, but the
raw model port is then open on the LAN.)

### Machine B — sandbox + agent + lobster (from a blank Ubuntu 24.04 box)

**Open one terminal on Machine B and run B0 → B2 in it yourself.** These are
hands-on steps — a `sudo` password prompt, the `newgrp docker` shell, and the
NemoClaw onboarding wizard — so type/paste them in your own terminal, not through
any automation that can't answer prompts. **Stay in that same terminal the whole
way:** `newgrp docker` (end of B0) activates the docker group for *that shell
only*, so opening a second terminal would lose it (you'd just `newgrp docker`
again there). Work under `$HOME` on an **ext4** disk — NOT an NTFS / exFAT /
network mount, or `git` and `venv` die on `chmod` ("Operation not permitted").

**B0 — base packages + docker group (in your terminal; `sudo` will prompt):**
```bash
sudo apt update
sudo apt install -y docker.io git curl python3-venv python3-pip
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"                  # activated by `newgrp docker` below (no relogin)
# NVIDIA: make sure the driver is installed first (`nvidia-smi` must work),
# then the container toolkit so the sandbox can claim the GPU:
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt update && sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker
```
**↳ Activate the group without logging out:** run `newgrp docker` and **stay in
this terminal for B1 + B2** — it execs a fresh shell that has the group, and the
lines you paste after it run inside that shell. (A *separate* terminal needs its
own `newgrp docker`; or log out/in once and forget it.)
```bash
newgrp docker
docker ps        # must run with NO permission error before continuing
```
> `newgrp` starts a new shell, so set variables (like B2's `MACHINE_A_IP`)
> **after** it — B2 already does.

**B1 — install NemoClaw + onboard (interactive):**
```bash
cd ~
curl -fsSL https://www.nvidia.com/nemoclaw.sh -o nemoclaw-install.sh
NEMOCLAW_INSTALL_REF=0f48781072b61041b0a53d57ad1845e85e7c634a \
NEMOCLAW_SANDBOX_NAME=hack-agent NEMOCLAW_PROVIDER=ollama \
NEMOCLAW_POLICY_MODE=suggested bash nemoclaw-install.sh
```
The wizard asks you to accept third-party terms and **pick a model — choose the
SMALLEST** (Machine B does not serve Super; it only needs a sandbox. Nano
doubles as the network-drop fallback — see docs/DEMO_ARCH1.md). The installer
appends `~/.local/bin` to PATH; reload it **in this same shell** with
`source ~/.bashrc` (do NOT open a new terminal — that would drop the `newgrp`
docker group), then confirm the sandbox is up:
```bash
nemoclaw list
docker ps --filter label=openshell.ai/sandbox-name=hack-agent --format '{{.Names}}'
```

**B2 — point inference at Machine A, get the repo, run (single paste):**
```bash
# >>> EDIT THESE TWO LINES <<<
MACHINE_A_IP=192.168.0.2                      # A's LAN IP now; A's 100.x tailnet IP at the venue
A_TOKEN='paste-machine-A-proxy-token-here'    # = `cat ~/.nemoclaw/ollama-proxy-token` on Machine A

cd ~ && git clone https://github.com/amamtaiwan/grab_a_claw.git
cd grab_a_claw && git checkout demo-arch1-remote-inference
python3 -m venv ui/.venv && ui/.venv/bin/pip install -r ui/requirements.txt
nemoclaw hack-agent skill install ./skills/desktop-tidy
nemoclaw hack-agent skill install ./skills/desktop-arrange

# Repoint the sandbox's inference at Machine A (the one real change vs main):
SBX=$(docker ps --filter label=openshell.ai/sandbox-name=hack-agent --format '{{.Names}}' | head -1)
cfg(){ docker exec --user sandbox -e HOME=/home/sandbox \
  -e OPENCLAW_CONFIG_PATH=/sandbox/.openclaw/openclaw.json "$SBX" openclaw config set "$@"; }
cfg models.providers.inference.baseUrl "http://$MACHINE_A_IP:11435/v1"
cfg models.providers.inference.apiKey  "$A_TOKEN"
cfg tools.toolSearch false
docker exec --user 0 "$SBX" pkill -9 -f '^openclaw$'   # apply config

# sanity: does Machine A serve Super over the network? (should list nemotron-3-super)
curl -s -H "Authorization: Bearer $A_TOKEN" "http://$MACHINE_A_IP:11435/v1/models"

./scripts/pre-demo.sh hack-agent           # seeds desktop, closes the gate, prints dashboard URL
ui/.venv/bin/python -u ui/overlay.py       # lobster overlay; 4K auto-detects SCALE=2.0
```

**Network:** for the home rehearsal set `MACHINE_A_IP` to Machine A's LAN address
(e.g. `192.168.0.2`). At the venue, `tailscale up` on both boxes and set
`MACHINE_A_IP` to Machine A's `100.x` tailnet IP — nothing else changes.

**Verify the link from Machine B:** the A4 `curl` (run from B against
`MACHINE_A_IP:11435`) lists Super; then a dashboard B1 prompt moves the lobster —
proving B's agent reached A's Super over the network.

## Setup (single-machine reference)

> The block below is the original **one-box** flow (model + sandbox + overlay on
> the same machine, as on `main`). On this branch use the two-machine split
> above; this is kept for reference / local testing.

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


https://github.com/user-attachments/assets/d2282092-33bd-4f04-ac8b-180a25e1038b


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

### Clearing GPU VRAM before / between demos

The demo path uses **only Ollama** (Nemotron 3 Super, ~90 GB resident). You normally never touch VRAM — `OLLAMA_KEEP_ALIVE` keeps the model hot. But if you've been experimenting (e.g. the fine-tune track's vLLM server) or the GPU looks full when it shouldn't, clear it like this:

```bash
# 1. See exactly what's holding VRAM.
nvidia-smi --query-compute-apps=pid,process_name,used_gpu_memory --format=csv

# 2. Unload just the Ollama model (keeps the daemon; fastest path).
ollama stop nemotron-3-super:latest

# 3. Or fully restart Ollama (drops everything it holds).
sudo systemctl restart ollama

# 4. Kill an orphaned engine that survived a Ctrl+C (the classic culprit
#    is a vLLM "EngineCore" process from the fine-tune track — it can hold
#    ~90 GB and won't die with the parent). Find its pid in step 1, then:
kill -9 <pid>

# 5. Confirm the card is clear (should drop to a few hundred MiB).
nvidia-smi --query-gpu=index,memory.used --format=csv

# 6. Re-warm Super before the demo so the first dashboard turn is instant.
curl -s http://localhost:11434/api/generate \
  -d '{"model":"nemotron-3-super:latest","prompt":"PONG","stream":false}' >/dev/null
nvidia-smi --query-gpu=memory.used --format=csv   # ~90 GB once loaded
```

`pre-demo.sh` already re-warms the model in its last step, so for a normal reset you only need this if a stale process is squatting on the card.

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
