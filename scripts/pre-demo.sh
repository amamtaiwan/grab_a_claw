#!/usr/bin/env bash
#
# pre-demo.sh — 60-second pre-flight before a live meet_a_claw demo.
#
# Run this in the operator terminal immediately before pitching. It:
#   1. Replants the demo desktop into a known state (7 files, mixed types
#      and ages so the trash-candidate rule fires on 4 of them).
#   2. Cleans sorted/* and .openclaw/trash/ so the demo starts empty.
#   3. Revokes the trash-writable preset and removes the marker so the
#      gate visual starts CLOSED (red).
#   4. Warms up Ollama by running a single PONG against the configured
#      model — this guarantees the model is hot in VRAM so the first
#      dashboard chat doesn't pay a 30–60s cold load.
#   5. Prints the dashboard URL with a fresh gateway token, the model
#      currently routed, and a concise operator cheat-sheet.
#
# Usage:
#   ./scripts/pre-demo.sh [<sandbox-name>]    # default: hack-agent

set -uo pipefail

SANDBOX="${1:-hack-agent}"
NEMOCLAW="${NEMOCLAW_BIN:-$HOME/.local/bin/nemoclaw}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

hr() { printf "\n\033[36m── %s ──\033[0m\n" "$*"; }
warn() { printf "\033[33m! %s\033[0m\n" "$*"; }
ok() { printf "\033[32m✓ %s\033[0m\n" "$*"; }

hr "0. deploy sandbox-internal tidy.sh (read by desktop-tidy skill)"
"$NEMOCLAW" "$SANDBOX" exec --timeout 15 -- bash -c 'mkdir -p /sandbox/.openclaw/bin'
CONTAINER=$(docker ps --filter "name=openshell-$SANDBOX" --format '{{.Names}}' | head -1)
if [ -z "$CONTAINER" ]; then
  warn "docker access missing or sandbox container not found; tidy.sh deploy skipped"
else
  docker cp "$REPO_DIR/sandbox-bin/tidy.sh" "$CONTAINER":/sandbox/.openclaw/bin/tidy.sh
  # docker cp preserves source perms (we chmod +x on the host file in repo),
  # and chown to sandbox so subsequent runs by the sandbox user have nothing
  # to argue about.
  docker exec --user 0 "$CONTAINER" chown sandbox:sandbox /sandbox/.openclaw/bin/tidy.sh
  "$NEMOCLAW" "$SANDBOX" exec --timeout 10 -- ls -la /sandbox/.openclaw/bin/tidy.sh
fi

hr "1. replant /sandbox/demo/desktop (7 files, known mtimes)"
# nemoclaw exec rejects newlines in its command arg, so we one-line this.
"$NEMOCLAW" "$SANDBOX" exec --timeout 30 -- bash -c 'mkdir -p /sandbox/demo/desktop /sandbox/demo/sorted/{images,documents,archives,code,media} /sandbox/.openclaw/trash; rm -rf /sandbox/demo/sorted/*/* /sandbox/.openclaw/trash/* 2>/dev/null; cd /sandbox/demo/desktop && rm -f * 2>/dev/null; for f in screenshot_2026-05-20.png old_disk.iso draft.pdf temp_notes.tmp tax_receipts_2024.zip random.log empty_file.txt; do touch "$f"; done; head -c 1024 /dev/urandom > screenshot_2026-05-20.png; head -c 524288 /dev/urandom > old_disk.iso; head -c 4096 /dev/urandom > draft.pdf; head -c 200 /dev/urandom > temp_notes.tmp; head -c 8192 /dev/urandom > tax_receipts_2024.zip; touch -d "2024-01-15" old_disk.iso; touch -d "2023-12-01" random.log; echo "desktop files: $(ls /sandbox/demo/desktop | wc -l)"'

hr "2. revoke trash gate (start CLOSED)"
"$REPO_DIR/policies/revoke-trash.sh" "$SANDBOX" 2>&1 | grep -vE 'Unknown preset|preset cleared' | tail -4
ok "gate is CLOSED — marker removed, preset cleared, overlay file = closed"

hr "3. warm up the inference model"
MODEL=$("$NEMOCLAW" inference get 2>/dev/null | awk '/^Model:/ {print $2; exit}')
if [ -z "$MODEL" ]; then
  warn "could not read inference model; skipping warmup"
else
  echo "model: $MODEL"
  T0=$(date +%s)
  timeout 90 ollama run "$MODEL" "Reply exactly: PONG" >/dev/null 2>&1 || warn "warmup ollama run timed out"
  T1=$(date +%s)
  ok "warmed in $((T1 - T0))s"
fi

hr "4. dashboard URL + cheat sheet"
TOKEN=$("$NEMOCLAW" "$SANDBOX" gateway-token --quiet 2>/dev/null)
cat <<EOF

  Dashboard:  http://127.0.0.1:18789/#token=$TOKEN
              (treat the URL like a password — do not share or screen-record uncensored)

  Live demo cheat-sheet (3 beats):
    A. In dashboard chat, type:
         Use desktop-tidy to clean my desktop
       → agent returns markdown with 3 moves + 4 trash DENIED + remediation.

    B. In this terminal, type:
         ./policies/grant-trash.sh $SANDBOX
       → overlay gate flips RED → GREEN; OCSF policy event lands.

    C. In dashboard chat, type:
         Tidy again
       → agent re-runs, this time the 4 trash succeed.

  Recovery (if the agent stalls > 60s):
       ./scripts/run-demo.sh $SANDBOX
     produces identical markdown via direct bash — same Landlock, same
     marker check, same audit log.

  Reset for another take:
       ./scripts/pre-demo.sh $SANDBOX

EOF
