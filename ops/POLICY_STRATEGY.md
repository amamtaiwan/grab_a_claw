# Policy strategy — the trash gate

The trash gate has to be a path that's denied by default and grantable
by an opt-in preset. Two designs we considered:

## Why we rejected: "carve a hole inside `/sandbox`"

The first design put trash at `/sandbox/demo/trash` and tried to
restrict that subpath via a custom policy. It doesn't work for two
reasons:

1. OpenShell's `filesystem_policy.include_workdir: true` is **creation-locked**.
   Setting it to `false` on a live sandbox returns
   `filesystem include_workdir cannot be changed on a live sandbox`. We
   verified this empirically (policy v5/v6 attempts at 2026-05-24).
2. Landlock is **monotonic-additive**. Adding `/sandbox/demo/trash` to
   `read_only` while `/sandbox` is in `read_write` does NOT shadow the
   broader rule — the union grants `read_write`. Verified empirically
   (mv into trash returned exit 0 with the more-specific RO rule applied).

We then prepared a workaround that flipped `include_workdir: false` in
the upstream YAML and rebuilt the sandbox from a custom Dockerfile. The
`nemoclaw onboard --from` build hung repeatedly (issue #2101 territory:
Docker Desktop's container DNS probe is inconclusive on this host, and
NemoClaw's image-overlay phase appears to wedge BuildKit when the cache
is large). 124 GB of build cache was reclaimed when we pruned, which is
consistent with a wedged BuildKit state.

## What we shipped: "put trash OUTSIDE `/sandbox`"

`/opt` is not in any default policy rule. Landlock default-deny applies
to writes there. Therefore `/opt/agent-trash` is denied at the kernel
level the moment we move trash to live in there. No upstream YAML
patch, no custom image, no build hang.

- **Default state:** `/opt/agent-trash` is denied. Skill returns
  structured rejection. Animation renders the bounce.
- **Operator grants `trash-writable` preset:** adds `/opt/agent-trash`
  to `read_write`. Skill succeeds. Animation renders gate open.
- **Operator removes preset:** path falls back out of `read_write`. Gate
  closes again.

`/opt/agent-trash` is pre-created inside the sandbox after onboard via
`docker exec --user 0`. Landlock is per-process and applied to the
container's PID-1-and-descendants only; a fresh `docker exec` from the
host's docker daemon is outside that process tree, so DAC governs that
mkdir (root can write anywhere).

The narrative for judges: **"trash is a system resource the agent must
request access to, not something inside its workspace."** Matches how
real systems work (XDG Trash on Linux uses `~/.local/share/Trash` —
a path the agent's home doesn't include by default).

## Files involved

- [policies/sandbox-base.yaml](../policies/sandbox-base.yaml) — exact
  mirror of the **unmodified** upstream `openclaw-sandbox.yaml`. Kept in
  the repo for audit, not as a patch source.
- [policies/trash-writable.yaml](../policies/trash-writable.yaml) — the
  preset that opens the gate. Grants `/opt/agent-trash` in `read_write`.
- [skills/desktop-trash/SKILL.md](../skills/desktop-trash/SKILL.md) —
  the skill that targets `/opt/agent-trash` and reports the denial.
- [skills/desktop-plan/SKILL.md](../skills/desktop-plan/SKILL.md) —
  plans `trash` actions with target `/opt/agent-trash/<file>`.

## Setup commands

After `nemoclaw onboard` completes for a fresh `hack-agent` sandbox:

```bash
# Pre-create the trash dir and re-plant demo files (idempotent).
CONTAINER=$(docker ps --filter name=openshell-hack-agent --format '{{.Names}}' | head -1)

docker exec --user 0 "$CONTAINER" bash -c '
  mkdir -p /opt/agent-trash &&
  chown sandbox:sandbox /opt/agent-trash &&
  ls -ld /opt/agent-trash
'
```
