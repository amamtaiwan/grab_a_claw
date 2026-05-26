# train/ — fine-tune evaluation track (bonus, not on the demo critical path)

This directory holds the LoRA fine-tune experiment we ran on
`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16`. The story is in
[SUBMISSION.md → "Fine-tune evaluation"](../SUBMISSION.md#fine-tune-evaluation-bonus-track-we-attempted-and-what-we-learned).
Short version: across 5 rounds we confirmed a stack-level incompatibility between
NeMo AutoModel's LoRA training and vLLM's Punica serving path for Nemotron-H
custom modeling. The base model without LoRA serves canonical JSON just fine,
so the demo doesn't depend on this directory.

What's tracked vs ignored (see [`../.gitignore`](../.gitignore)):

| Tracked | Why |
|---|---|
| `generate_sft_data.py` | Builds the 5K compositional SFT dataset |
| `nano-peft-singlegpu.yaml` | Single-GPU LoRA recipe (adapted from NVIDIA's 8×H100 cookbook) |
| `chat_template_no_thinking.jinja` | Train/serve template-alignment fix from round v3 |
| `data/{train,eval}.chatml.jsonl` | The 4500 train / 500 eval samples — byte-identical to what we trained on |
| `data/{train,eval}.nemo.jsonl` | Same data in NeMo Aligner format (kept for compat) |

| Ignored | Why |
|---|---|
| `Automodel/`, `nemotron-recipe/` | Vendored from `github.com/NVIDIA-NeMo/{Automodel,Nemotron}` — clone yourself |
| `vllm-venv/` | vLLM 0.17.1 install (~11 GB) — recreate via `uv pip install ...` (see SUBMISSION) |
| `checkpoints/` | 5 LoRA adapters × multiple steps each, ~4.4 GB total — the experiment outcome is the loss table in SUBMISSION; binary weights aren't needed |
| `logs/` | Training stdout per round; the numbers are in SUBMISSION |

## Reproducing a single round

If you want to retrain (e.g. v5 with `r=128 + alpha=256` on 5000 samples):

```bash
# 1. Get the dependencies
git clone https://github.com/NVIDIA-NeMo/Automodel.git
cd Automodel && uv venv && uv sync --extra cuda
#    CUDA toolchain notes in ../SUBMISSION.md (CUDA 12.8 toolkit alongside system 13.0)

# 2. Adjust nano-peft-singlegpu.yaml placeholders for your machine
sed -i 's|<repo-root>|'"$(realpath ..)"'|g; s|<nano-bf16-path>|/your/path/to/nemotron-3-nano-bf16|g' \
  ../nano-peft-singlegpu.yaml

# 3. Train
CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=0 \
  .venv/bin/automodel ../nano-peft-singlegpu.yaml --nproc-per-node=1
```

## Serving the trained adapter with vLLM

```bash
vllm serve <path-to-base-model> \
  --enable-lora \
  --lora-modules schema=<path-to-checkpoint>/LATEST/model \
  --max-lora-rank 128 \
  --trust-remote-code \
  --attention-backend TRITON_ATTN \
  --enforce-eager \
  --chat-template chat_template_no_thinking.jinja
```

The `TRITON_ATTN + --enforce-eager` combo is required on Blackwell (sm_120) with
driver 570 to avoid `cudaErrorUnsupportedPtxVersion` from the bundled FlashAttention
cubins. Details in SUBMISSION.

## What we'd try next

If you want to push this forward beyond what we did:

1. **Full fine-tune of Nemotron-Nano-9B** instead of LoRA. The 9B model fits a
   single 96 GB GPU for full FT (with bnb-8bit optimizer); avoids the Punica
   path entirely.
2. **DeepSpeed ZeRO-3 + CPU offload** to attempt full FT on Nano-30B. Slow but
   sidesteps the LoRA-server incompatibility.
3. **TensorRT-LLM** as the serving engine instead of vLLM. NVIDIA's own runtime
   for Nemotron-H — different LoRA merge path, may not hit the same bug.
4. **NeMo Skills** for end-to-end eval. Useful even without retraining — could
   quantify how often the base model emits canonical JSON vs drift, and validate
   the broker tolerance numbers.
