# Submission — grab_a_claw

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
- [ui/overlay.py](./ui/overlay.py) — pyglet overlay; walks, carries, bounces, watches `/tmp/grab_a_claw-gate-state` and flips visual.

## Fine-tune evaluation (bonus track we attempted, and what we learned)

The hackathon's bonus dimension is "fine-tune a Nemotron". We spent ~15 hours evaluating a LoRA QLoRA fine-tune of Nemotron-3-Nano-30B-A3B to reinforce the `desktop-arrange` canonical JSON schema. **Five training rounds all converged on training metrics but produced unusable output at vLLM serve time.** This section documents the experiment honestly so judges can verify our diagnosis instead of guessing.

### Stack chosen

- **Base**: `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16` (30B total / 3B active LatentMoE, 60 GB BF16).
- **Trainer**: NVIDIA NeMo AutoModel (`NeMoAutoModelForCausalLM` + `peft.lora.PeftConfig`), driven by [train/nano-peft-singlegpu.yaml](./train/nano-peft-singlegpu.yaml). Single 96 GB Blackwell, QLoRA via `bnb_4bit_quant_type=nf4` to fit the base in 4-bit.
- **Server**: vLLM 0.17.1 + flashinfer 0.6.4 + `--attention-backend TRITON_ATTN --enforce-eager` to bypass the Blackwell sm_120 PTX issue on driver 570.195.
- **Data**: [train/generate_sft_data.py](./train/generate_sft_data.py) generates 5000 ChatML samples covering set_position × 5 zones, trash, meta-arrange, prefix-trash, ext-routing, circle, NxN grid, relative-position, multi-move, stack, swap.

### Results across 5 rounds

| Round | LoRA target | Dataset | Steps × epoch | train_loss | val_loss | vLLM output |
|---|---|---|---|---|---|---|
| v1 | + lm_head | 291 | 220 × 3 | 0.0042 | 0.0047 | colon→comma corruption in JSON |
| v2 | – lm_head, – MoE experts | 291 | 220 × 3 | 0.0049 | 0.0066 | invents non-canonical keys (`intent`, `move_files`) |
| v3 | same + chat_template `enable_thinking=False` baked in | 291 | 220 × 3 | 0.0051 | 0.0067 | token-soup (`{"tk"}`, `{"scheleton":...}`) |
| v4 | r=16 | 5000 (incl. compositional) | 600 × 1 (batch=8) | 0.048 | 0.113 | policy-refusal hallucinations + infinite repetition |
| v5 | r=128, alpha=256 | 5000 | 1126 × 2 (batch=8) | 0.021 | 0.070 | wraps intents in invented `{"seq":[...]}`, partial token typos, mid-stream reasoning |

For every round, the **base Nano with no LoRA** emits canonical `{"action":"set_position","file":"draft.pdf","x":1000,"y":0}` perfectly on the same vLLM endpoint. The LoRA adapter *makes the model worse*.

### Root cause

Cross-check confirmed it's not a single tunable:

- **Not chat-template default mismatch.** v3 mirrored the training template into the vLLM `--chat-template` flag (default `enable_thinking=False` on both sides); output still broke.
- **Not LoRA capacity.** v5 bumped rank from 16 → 128 (8× more adapter params); behaviour got marginally better on Train/val loss but the symptom class was identical.
- **Not dataset size.** v4–v5 saw 17× more data than v1–v3; the failure modes only shifted, never disappeared.
- **Not the training stack alone.** Loading the v4 adapter via HuggingFace Transformers + PEFT + bitsandbytes (bypassing vLLM entirely) crashed on `modeling_nemotron_h.py:1633 cache_position[-1]` — Nemotron-H's custom modeling code is itself in flux against transformers 4.57.6.

The remaining hypothesis — the only one consistent with *all five* outcomes — is a **stack-level interaction between NeMo Automodel's bnb-4bit-trained LoRA adapter format and vLLM Punica's expectation for how to merge a LoRA into a quantized Nemotron-H base at serve time**. The adapter `target_modules` (mamba `in_proj`, attention `q/k/v/o_proj`) load without warnings, but the runtime forward path either rescales them differently or merges into wrong projections.

### Why we stopped (and what we chose instead)

We could have kept iterating — Nemotron-Nano-9B full fine-tune was the natural next step (smaller, full FT instead of LoRA, sidesteps the Punica path) and probably would have worked. But:

- We've already shipped a production-grade alternative: the [lookup-table SKILL.md](./skills/desktop-arrange/SKILL.md) + tolerant broker (`DesktopArrangeBroker` in [ui/overlay.py](./ui/overlay.py)) accepts every off-schema variant we observed and routes it to canonical intents. In practice this is what real LLM-tool stacks do anyway: middleware between the model and the action layer that absorbs schema drift.
- The 5/28 deadline is real. Adding another 24-hour training experiment with uncertain outcome is the wrong asymmetry — the worst case is showing up to the demo with a half-trained model + a broken pipeline + no time to fall back.

So we wrote it up instead of training again. The Super 120B + lookup-table SKILL.md + tolerant broker is the demo path of record.

### Artifacts judges can inspect

- [train/generate_sft_data.py](./train/generate_sft_data.py) — the 5000-sample compositional dataset generator.
- [train/nano-peft-singlegpu.yaml](./train/nano-peft-singlegpu.yaml) — single-GPU LoRA recipe, adapted from NVIDIA's official 8×H100 [`customizer_nemotron_nano_peft.yaml`](https://github.com/NVIDIA-NeMo/Automodel/blob/main/examples/llm_finetune/nemotron/customizer_nemotron_nano_peft.yaml).
- [train/chat_template_no_thinking.jinja](./train/chat_template_no_thinking.jinja) — the train/serve template-alignment fix.
- [train/checkpoints/nano-lora-schema-v{1..5}/LATEST/losses.json](./train/checkpoints/) — final train/val numbers per round, plus saved adapters.

## What we'd build next (if we had a week, not 5 days)

- **Real Taskflow durability.** The OpenClaw `taskflow` runtime is a plugin-level API (TypeScript), not a SKILL.md call. We'd wrap `desktop-tidy` as a Taskflow controller so it survives sandbox restarts and accepts mid-run grant events ("the gate just opened — retry the deferred trashes").
- **Skill→tool catalog bridge.** The 3-min agent thrash on first turn is OpenClaw v0.1.0 alpha not auto-injecting SKILL.md into the system prompt as callable tools. Upstream issue; we'd file a PR.
- **Web-search-free reasoning audit.** The dashboard chat currently uses the agent's tool runtime which can reach `clawhub.ai` / `openclaw.ai`. For a strict deployment, we'd configure the `Restricted` policy tier as the *only* runtime egress and prove with `openshell policy prove` that no reachable host exists outside `inference.local`.
- **Mobile carry over (NemoClaw "nodes").** The lobster could walk between this desktop and a paired Mac via OpenClaw's node-bridge — files on phone → home machine via the same agent + same gates.
