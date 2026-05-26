#!/usr/bin/env bash
#
# revoke-trash.sh — close the trash gate.
#
# Inverse of grant-trash.sh:
#   1. Removes /sandbox/.openclaw/trash-approved (the marker the skill reads).
#   2. Removes the trash-writable preset from NemoClaw — also an audit signal.
#
# Usage:
#   ./policies/revoke-trash.sh [<sandbox-name>]   # default: hack-agent

set -euo pipefail

SANDBOX="${1:-hack-agent}"
NEMOCLAW="${NEMOCLAW_BIN:-$HOME/.local/bin/nemoclaw}"

echo "[revoke-trash] sandbox=$SANDBOX"

echo "[revoke-trash] removing marker /sandbox/.openclaw/trash-approved"
"$NEMOCLAW" "$SANDBOX" exec --timeout 15 -- bash -c \
  'rm -f /sandbox/.openclaw/trash-approved && ls /sandbox/.openclaw/trash-approved 2>&1 || echo "(marker removed)"'

echo "[revoke-trash] removing NemoClaw preset (audit signal)"
"$NEMOCLAW" "$SANDBOX" policy-remove trash-writable --yes 2>&1 | tail -8 || true

echo "[revoke-trash] writing host-side gate state for the overlay"
echo "closed" > /tmp/grab_a_claw-gate-state

echo "[revoke-trash] gate is CLOSED. Grant with: ./policies/grant-trash.sh $SANDBOX"
