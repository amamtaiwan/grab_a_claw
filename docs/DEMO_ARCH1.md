# Demo Architecture 1 — split inference (DEMO ONLY, probably unsafe)

> ⚠️ This branch is for the **GTC Taipei 2026-06-04 live demo only.** It
> deliberately weakens the security model `main` is built around. Do not
> merge to `main`; do not run on an untrusted network.

## What it is

```
[ HOME — your workstation ]                 [ BOOTH — DGX Spark ]
  Ollama + Nemotron 3 Super 120B    ← Tailscale →   NemoClaw sandbox
  (96 GB Blackwell, ~1.79 TB/s)       (text only)    + OpenClaw agent
  serves /v1 on tailnet IP                            + ui/overlay.py (lobster)
                                                      + drives the booth 4K display
                                                      + Nano 30B loaded LOCAL as fallback
```

Only **text** crosses the network — the inference request (system prompt +
user message, a few KB) and the response (a JSON intent, a few hundred bytes).
The lobster animation, the sandbox, and the policy gate all run **locally on
the Spark**, so a flaky conference network never touches the visuals.

## Why this is "probably unsafe"

`main`'s guardrail story has two layers:

1. **OpenShell Landlock** — filesystem isolation (unchanged here).
2. **Network policy** — the sandbox's egress is locked to `inference.local`
   (the gateway's internal virtual host). On `main`, the agent literally
   cannot reach the open internet.

This branch **repoints the sandbox's inference provider at a remote Tailscale
IP**. That means:

- The sandbox now has a live network path off-box (to the workstation). A
  compromised or jailbroken agent could, in principle, use that channel for
  exfiltration or C2 — the network-isolation guarantee no longer holds.
- The inference traffic rides Tailscale (WireGuard, encrypted) but the
  *policy* that used to forbid all non-`inference.local` egress is relaxed.
- We accept this **only** because the demo runs on a controlled tailnet with
  exactly two known nodes, for ~20 minutes, with an operator watching.

For any real deployment, inference must stay local (as on `main`) or be
fronted by a policy-enforced proxy that still satisfies `openshell policy prove`.

## Setup (rehearse this BEFORE the event)

### 0. Prereqs
- Tailscale account; both machines joined to the same tailnet.
- Workstation: Ollama + Super already working (this is `main`'s normal state).
- Spark: NemoClaw + OpenShell + OpenClaw installed; overlay deps installed.

### 1. Tailscale — join both nodes
```bash
# both machines
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
tailscale ip -4          # note each node's 100.x.y.z address
```
Record:
- `WORKSTATION_TS_IP` = `100.__.__.__`
- `SPARK_TS_IP`       = `100.__.__.__`

### 2. Workstation — expose Ollama on the tailnet
By default Ollama binds `127.0.0.1:11434`. Bind it to the tailnet so the Spark
can reach it (do NOT bind `0.0.0.0` on an untrusted LAN — tailnet only):
```bash
# workstation: systemd override
sudo systemctl edit ollama
# add:
#   [Service]
#   Environment="OLLAMA_HOST=0.0.0.0:11434"
sudo systemctl restart ollama
# verify from the Spark:
curl -s http://$WORKSTATION_TS_IP:11434/api/tags | head
```
(Tailscale ACLs should restrict :11434 to just the Spark node — set this in the
Tailscale admin console for least privilege.)

### 3. Spark — point NemoClaw inference at the workstation
The sandbox's OpenClaw config routes inference via `inference.local`. Repoint
the provider base URL at the workstation's tailnet Ollama:
```bash
SBX=$(docker ps --filter name=openshell-hack-agent --format '{{.Names}}' | head -1)
docker exec --user sandbox -e HOME=/home/sandbox \
  -e OPENCLAW_CONFIG_PATH=/sandbox/.openclaw/openclaw.json \
  "$SBX" openclaw config set \
  models.providers.inference.baseUrl "http://$WORKSTATION_TS_IP:11434/v1"
# bounce openclaw to apply
docker exec --user 0 "$SBX" pkill -9 -f '^openclaw$'
```
> NOTE: depending on the OpenShell network policy, the sandbox may block egress
> to the tailnet IP. If so, add the workstation tailnet IP:11434 to an allow
> rule in the sandbox network policy (this is the step that "opens the box" —
> see threat model above), then re-onboard / restart the sandbox.

### 4. Spark — local Nano fallback
Load Nano locally so a network drop has an instant switch-to-local path:
```bash
ollama pull nemotron-3-nano:latest     # or your local Nano build
ollama run nemotron-3-nano:latest "PONG"   # warm it
```
If the workstation becomes unreachable mid-demo, flip the provider back to the
Spark-local Ollama:
```bash
docker exec --user sandbox -e HOME=/home/sandbox \
  -e OPENCLAW_CONFIG_PATH=/sandbox/.openclaw/openclaw.json \
  "$SBX" openclaw config set \
  models.providers.inference.baseUrl "http://127.0.0.1:11434/v1"
docker exec --user sandbox ... openclaw config set \
  models.providers.inference.models[0].id "nemotron-3-nano:latest"
docker exec --user 0 "$SBX" pkill -9 -f '^openclaw$'
```

### 5. Speed — turn OFF thinking for the demo
Super at ~30 s/turn with `thinkingDefault=medium` is mostly reasoning tokens.
For the live demo, turn thinking off (the lookup-table SKILL is strong enough):
```bash
docker exec --user sandbox -e HOME=/home/sandbox \
  -e OPENCLAW_CONFIG_PATH=/sandbox/.openclaw/openclaw.json \
  "$SBX" openclaw config set agents.defaults.thinkingDefault off
```
Benchmark on the workstation first: a turn should drop well under 30 s.

### 6. 4K display
The Spark drives the booth 4K monitor. This branch supports it **natively** —
no config flag needed:
- `overlay.py` computes `SCALE = screen_w / 1920` at startup (logs it as
  `SCALE=2.000` on a 3840-wide panel) and scales every absolute constant —
  lobster sprite, trash-bin widget, sort-folder drop zones, the broker's
  zone/explicit coords (and the `gio set` metadata it writes), and the status
  fonts. Fraction-based geometry (home/trash/stage) already scaled on its own.
- `pre-demo.sh` plants the host file/folder icons with the **same**
  `SCREEN_W/1920` factor, so the real desktop icons and the lobster's drop
  zones stay aligned. At 1920×1080 `SCALE=1.0` → byte-for-byte identical to
  the tested `main` layout (zero regression); at 3840×2160 everything is ×2.
- **Verify on the day:** start the overlay and confirm the log line reads
  `screen 3840x2160 ... SCALE=2.000`. Run B1 (move draft.pdf upper-right) and
  watch the lobster actually reach the folder icon — that proves the host and
  overlay coords agree.
- **Zero-risk fallback** if 4K misbehaves under pressure: force 1080 and the
  whole stack runs at the well-tested `SCALE=1.0`:
  `xrandr --output <DP-OUT> --mode 1920x1080`

> ⚠️ The ×2 scaling assumes a 16:9 panel (3840×2160 is exactly 2× of
> 1920×1080), so one uniform SCALE works for both axes. An ultrawide or a
> non-16:9 projector would stretch — force 1080 in that case.

## Demo-day runbook

1. Workstation at home: Ollama up, Super warm, Tailscale up, `OLLAMA_HOST` on tailnet.
2. Spark at booth: Tailscale up, `curl $WORKSTATION_TS_IP:11434/api/tags` returns 200.
3. Spark: `./scripts/pre-demo.sh hack-agent` (seeds demo desktop, revokes gate).
4. Spark: launch overlay in a shell **with docker group active** (`newgrp docker` first).
5. Dashboard: run A → B1 → B2(locked→unlock)→ B3.
6. If a turn hangs > 60 s: check the tunnel (`tailscale status`); if the
   workstation is unreachable, do step 4 of "Spark — local Nano fallback".
7. Ultimate fallback: play the recorded demo videos (embedded in `main`'s README).

## Teardown
- Revert Spark inference route to local; `tailscale down` on both; restore
  workstation Ollama to `127.0.0.1` bind. This branch never merges to `main`.
