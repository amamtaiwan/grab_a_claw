#!/usr/bin/env bash
#
# grant-trash.sh — open the trash gate for a meet_a_claw sandbox.
#
# Application-layer consent for the desktop-trash skill. Atomically does:
#   1. Touches /sandbox/.openclaw/trash-approved inside the sandbox
#      (the marker the skill reads before attempting mv).
#   2. Applies the trash-writable preset to NemoClaw — this is purely a
#      signal: the network endpoint it whitelists is non-functional, but
#      its apply event is recorded in the OCSF audit log so the animation
#      layer can detect "gate state changed" without polling the marker.
#
# Usage:
#   ./policies/grant-trash.sh [<sandbox-name>]   # default: hack-agent

set -euo pipefail

SANDBOX="${1:-hack-agent}"
NEMOCLAW="${NEMOCLAW_BIN:-$HOME/.local/bin/nemoclaw}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[grant-trash] sandbox=$SANDBOX"

echo "[grant-trash] touching marker /sandbox/.openclaw/trash-approved"
"$NEMOCLAW" "$SANDBOX" exec --timeout 15 -- bash -c \
  'mkdir -p /sandbox/.openclaw/trash && touch /sandbox/.openclaw/trash-approved && ls -la /sandbox/.openclaw/trash-approved'

echo "[grant-trash] applying NemoClaw preset (audit signal only — filesystem grants are baked at sandbox create time)"
"$NEMOCLAW" "$SANDBOX" policy-add --from-file "$REPO_DIR/policies/trash-writable.yaml" --yes 2>&1 | tail -8 || true

echo "[grant-trash] gate is OPEN. Revoke with: ./policies/revoke-trash.sh $SANDBOX"
