# Demo Architecture 1 — split inference (DEMO ONLY, probably unsafe)

> ⚠️ This branch is for the **GTC Taipei 2026-06-04 live demo only.** It
> deliberately weakens the security model `main` is built around. Do not
> merge to `main`; do not run on an untrusted network.

## What it is

```
[ HOME — your workstation ]                 [ BOOTH — DGX Spark ]
  Ollama + Nemotron 3 Super 120B    ←  OpenVPN  →   NemoClaw sandbox
  (96 GB Blackwell, ~1.79 TB/s)       (text only)    + OpenClaw agent
  proxy /v1 on LAN/VPN IP :11435                      + ui/overlay.py (lobster)
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

This branch **repoints the sandbox's inference provider at a remote IP reached
over an OpenVPN tunnel**. That means:

- The sandbox now has a live network path off-box (to the workstation). A
  compromised or jailbroken agent could, in principle, use that channel for
  exfiltration or C2 — the network-isolation guarantee no longer holds.
- The inference traffic rides an OpenVPN tunnel (encrypted; only the router's
  cert-authenticated VPN port faces the internet, never the `:11435` proxy) but
  the *policy* that used to forbid all non-`inference.local` egress is relaxed.
- We accept this **only** because the demo runs over a controlled OpenVPN tunnel
  with exactly two known nodes, for ~20 minutes, with an operator watching.

For any real deployment, inference must stay local (as on `main`) or be
fronted by a policy-enforced proxy that still satisfies `openshell policy prove`.

## Setup (rehearse this BEFORE the event)

### 0. Prereqs
- OpenVPN: the **home router** runs the built-in OpenVPN **server**; the Spark
  runs the OpenVPN **client** with a `.ovpn` profile exported from the router.
- Workstation: Ollama + Super already working (this is `main`'s normal state).
- Spark: NemoClaw + OpenShell + OpenClaw installed; overlay deps installed.

### 1. OpenVPN — router server, Spark client
On the **home router**: enable the built-in OpenVPN server, allow VPN clients to
reach the LAN subnet (`192.168.0.0/24`, not internet-only), and export the
client `.ovpn`. The router opens its own VPN port — you do **not** port-forward
`:11435`. On the **Spark**:
```bash
sudo apt install -y openvpn
sudo openvpn --config client.ovpn --daemon      # or import into NetworkManager
```
Because the router routes VPN clients into the LAN, the Spark reaches the
workstation at its **LAN IP** — so `WORKSTATION_IP = 192.168.0.2` both at home
and over the venue tunnel. Verify with the proxy token:
```bash
curl -s -H "Authorization: Bearer <token>" http://192.168.0.2:11435/v1/models   # → lists Super
```

### 2. Workstation — serve the model on the network
NemoClaw already runs an **auth-proxy** that exposes an OpenAI-compatible `/v1`
on `0.0.0.0:11435`, **token-gated** (it forwards to the system Ollama on
`127.0.0.1:11434`, which holds Super + Nano under `/usr/share/ollama`). That
proxy is already network-facing, so you usually only need to bring Ollama up:
```bash
# workstation
sudo systemctl start ollama                       # Super lives here
curl -s http://127.0.0.1:11434/api/generate \
  -d '{"model":"nemotron-3-super:latest","prompt":"PONG","stream":false}' >/dev/null  # warm
# note for the Spark: WORKSTATION_IP=192.168.0.2 (LAN, and the same over the
# venue OpenVPN tunnel), port 11435, and the bearer token:
cat ~/.nemoclaw/ollama-proxy-token                # treat as a secret
curl -s -H "Authorization: Bearer $(cat ~/.nemoclaw/ollama-proxy-token)" \
  http://$WORKSTATION_IP:11435/v1/models          # → lists nemotron-3-super:latest
```
> Tokenless alternative: bind Ollama itself to the network
> (`sudo systemctl edit ollama` → `OLLAMA_HOST=0.0.0.0:11434` → restart) and use
> bare `http://$WORKSTATION_IP:11434/v1`. Simpler config, but the raw model port
> is open on the LAN/VPN subnet — keep it off the public internet (the OpenVPN
> tunnel already does that), and ideally restrict it with `ufw` to just the VPN
> subnet / Spark.

### 3. Spark — point NemoClaw inference at the workstation
The sandbox's OpenClaw config routes inference via `inference.local`. Repoint
the provider base URL (and API key) at the workstation's token-gated proxy:
```bash
SBX=$(docker ps --filter label=openshell.ai/sandbox-name=hack-agent --format '{{.Names}}' | head -1)
docker exec --user sandbox -e HOME=/home/sandbox \
  -e OPENCLAW_CONFIG_PATH=/sandbox/.openclaw/openclaw.json "$SBX" \
  openclaw config set models.providers.inference.baseUrl "http://$WORKSTATION_IP:11435/v1"
docker exec --user sandbox -e HOME=/home/sandbox \
  -e OPENCLAW_CONFIG_PATH=/sandbox/.openclaw/openclaw.json "$SBX" \
  openclaw config set models.providers.inference.apiKey "<workstation proxy token>"
# bounce openclaw to apply
docker exec --user 0 "$SBX" pkill -9 -f '^openclaw$'
```
`$WORKSTATION_IP` = the workstation's LAN IP `192.168.0.2` — the same at home
and over the venue OpenVPN tunnel (the router routes VPN clients into the LAN),
so nothing in this step changes between rehearsal and the booth.
> NOTE — **required on a fresh sandbox.** A newly-onboarded sandbox enforces an
> egress allowlist (internal proxy): the agent can reach `inference.local` /
> `host.openshell.internal` + package registries, but **not** the workstation's
> IP — so it silently falls back to LOCAL inference and the workstation GPU never
> moves. Open egress to it (this is the step that "opens the box" — see threat
> model above):
> ```bash
> # policies/remote-inference.yaml allows host 192.168.0.2:11435 — edit if needed
> nemoclaw hack-agent policy-add --from-file ./policies/remote-inference.yaml --yes
> ```
> Verify the agent (not just the host) can now reach it — `docker exec` bypasses
> the proxy, so test from the agent's environment or just watch the workstation
> GPU load Super on the first dashboard turn.

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

1. Workstation at home: Ollama up, Super warm; router's OpenVPN server enabled.
2. Spark at booth: OpenVPN client connected; `curl -H "Authorization: Bearer <token>" http://192.168.0.2:11435/v1/models` lists Super.
3. Spark: `./scripts/pre-demo.sh hack-agent` (seeds demo desktop, revokes gate).
4. Spark: launch overlay in a shell **with docker group active** (`newgrp docker` first).
5. Dashboard: run A → B1 → B2(locked→unlock)→ B3.
6. If a turn hangs > 60 s: check the tunnel (`ping 192.168.0.2`, OpenVPN client
   status); if the workstation is unreachable, do step 4 of "Spark — local Nano
   fallback".
7. Ultimate fallback: play the recorded demo videos (embedded in `main`'s README).

## Teardown
- Revert Spark inference route to local; stop the OpenVPN client on the Spark and
  disable the router's OpenVPN server; optionally rotate the workstation proxy
  token. This branch never merges to `main`.
