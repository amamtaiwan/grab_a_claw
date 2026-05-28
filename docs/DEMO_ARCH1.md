# Demo Architecture 1 — split inference (DEMO ONLY, probably unsafe)

> ⚠️ This branch is for the **GTC Taipei 2026-06-04 live demo only.** It
> deliberately weakens the security model `main` is built around. Do not
> merge to `main`; do not run on an untrusted network.

## What it is

```
[ HOME — your workstation ]                 [ BOOTH — DGX Spark ]
  Ollama + Nemotron 3 Super 120B    ←   SSH    →    NemoClaw sandbox
  (96 GB Blackwell, ~1.79 TB/s)       (text only)    + OpenClaw agent
  /v1 on 127.0.0.1:11434 (SSH only)                  + ui/overlay.py (lobster)
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

This branch **repoints the sandbox's inference at the workstation, reached over
an SSH tunnel** (the sandbox dials a local port that `ssh -L` forwards to the
workstation's Ollama). That means:

- The sandbox now has a live network path off-box (to the workstation). A
  compromised or jailbroken agent could, in principle, use that channel for
  exfiltration or C2 — the network-isolation guarantee no longer holds.
- The traffic rides an SSH tunnel (encrypted; only the workstation's SSH port
  faces the internet, never the `:11434` model port, and the key handed out is
  forward-only — `permitopen` to that one port, no shell) but the *policy* that
  used to forbid all non-`inference.local` egress is relaxed.
- We accept this **only** because the demo runs over a controlled SSH tunnel
  with exactly two known nodes, for ~20 minutes, with an operator watching.

For any real deployment, inference must stay local (as on `main`) or be
fronted by a policy-enforced proxy that still satisfies `openshell policy prove`.

## Setup (rehearse this BEFORE the event)

### 0. Prereqs
- SSH: the **Spark** opens an `ssh -L` tunnel to the workstation; the workstation
  trusts a **forward-only public key** the Spark's operator generated.
- Workstation: Ollama + Super already working (this is `main`'s normal state);
  sshd running, key-only auth.
- Spark: NemoClaw + OpenShell + OpenClaw installed; overlay deps installed.

### 1. Workstation — serve the model + trust a forward-only key
```bash
# workstation
sudo systemctl start ollama                       # Super lives here (127.0.0.1:11434)
curl -s http://127.0.0.1:11434/api/generate \
  -d '{"model":"nemotron-3-super:latest","prompt":"PONG","stream":false}' >/dev/null  # warm

# Trust the Spark operator's PUBLIC key, locked to a single port, no shell:
cat >> ~/.ssh/authorized_keys <<'KEY'
no-pty,no-agent-forwarding,no-X11-forwarding,permitopen="127.0.0.1:11434",command="echo forward-only; sleep infinity" ssh-ed25519 AAAA...SPARK-OPERATOR-PUBKEY... demo-forward
KEY
chmod 600 ~/.ssh/authorized_keys
sudo sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config && sudo systemctl reload ssh
```
`WORKSTATION_IP = 192.168.0.2` for the home rehearsal. At the venue, port-forward
**one** external port on the home router → workstation:22; the Spark uses your
public IP / DDNS + that port. Only SSH is ever exposed; `:11434` stays local.

### 2. Spark — open the SSH tunnel
```bash
# generate ONCE; send only the .pub to the workstation operator (step 1)
[ -f ~/.ssh/grabclaw_demo ] || ssh-keygen -t ed25519 -N '' -f ~/.ssh/grabclaw_demo -C demo-forward
A_HOST=192.168.0.2     # workstation LAN IP at home; public IP / DDNS at the venue
A_SSH_PORT=22          # the router-forwarded SSH port at the venue
# bind 0.0.0.0:8000 so the sandbox can reach it via host.openshell.internal
ssh -i ~/.ssh/grabclaw_demo -fN -L 0.0.0.0:8000:127.0.0.1:11434 demo@"$A_HOST" -p "$A_SSH_PORT"
curl -s http://127.0.0.1:8000/v1/models          # → lists nemotron-3-super:latest
```
(`autossh` instead of `ssh` auto-reconnects if the link drops mid-demo.)

### 3. Spark — point NemoClaw inference at the tunnel
The sandbox talks to the **local host** (`host.openshell.internal:8000`, which is
already on the `local-inference` egress allowlist); the tunnel carries it to the
workstation's Super. **No custom egress policy is needed** (vs a direct-IP setup),
because the agent never dials a non-local address.
```bash
SBX=$(docker ps --filter label=openshell.ai/sandbox-name=hack-agent --format '{{.Names}}' | head -1)
cfg(){ docker exec --user sandbox -e HOME=/home/sandbox \
  -e OPENCLAW_CONFIG_PATH=/sandbox/.openclaw/openclaw.json "$SBX" openclaw config set "$@"; }
cfg models.providers.inference.baseUrl          "http://host.openshell.internal:8000/v1"
cfg models.providers.inference.apiKey           "unused"
cfg 'models.providers.inference.models[0].id'   "nemotron-3-super:latest"
cfg 'models.providers.inference.models[0].name' "inference/nemotron-3-super:latest"
cfg agents.defaults.model.primary               "inference/nemotron-3-super:latest"
docker exec --user 0 "$SBX" pkill -9 -f '^openclaw$'   # reload agent config
```
> Retarget `id` **and** `name` **and** `agents.defaults.model.primary` — the
> agent selects its model by `primary` (a model *name*); changing only `id`
> leaves it requesting the small onboarding model. Confirm it's really Super by
> watching the **workstation** GPU load ~90 GB on the first dashboard turn
> (`docker exec` from the host bypasses the egress proxy, so a host-side curl is
> not proof the *agent* reached it).
>
> The older `policies/remote-inference.yaml` preset is only for a direct-IP
> (no-SSH) variant — with the SSH tunnel you do not apply it.

### 4. Spark — local Nano fallback
The Spark onboarded with local Nano (`nemotron-3-nano:30b`), so a network drop
has an instant switch-to-local path. If the workstation (or the tunnel) becomes
unreachable mid-demo, flip the sandbox back to the Spark's own Ollama (`cfg` is
the helper from step 3):
```bash
cfg models.providers.inference.baseUrl          "https://inference.local/v1"
cfg 'models.providers.inference.models[0].id'   "nemotron-3-nano:30b"
cfg 'models.providers.inference.models[0].name' "inference/nemotron-3-nano:30b"
cfg agents.defaults.model.primary               "inference/nemotron-3-nano:30b"
docker exec --user 0 "$SBX" pkill -9 -f '^openclaw$'
# warm it first if needed:  ollama run nemotron-3-nano:30b "PONG"
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

1. Workstation at home: Ollama up, Super warm; sshd up, forward-only key trusted.
2. Spark at booth: `ssh -L` tunnel up; `curl http://127.0.0.1:8000/v1/models` lists Super.
3. Spark: `./scripts/pre-demo.sh hack-agent` (seeds demo desktop, revokes gate).
4. Spark: launch overlay in a shell **with docker group active** (`newgrp docker` first).
5. Dashboard: run A → B1 → B2(locked→unlock)→ B3.
6. If a turn hangs > 60 s: check the tunnel (`curl http://127.0.0.1:8000/v1/models`;
   is the `ssh -L` still up?); if the workstation is unreachable, do step 4
   "Spark — local Nano fallback".
7. Ultimate fallback: play the recorded demo videos (embedded in `main`'s README).

## Teardown
- Revert the Spark inference route to local; kill the `ssh -L` tunnel on the
  Spark, remove the router's SSH port-forward, and delete the forward-only key
  line from the workstation's `~/.ssh/authorized_keys`. This branch never merges
  to `main`.
