# Upstream patch — `openclaw-sandbox.yaml`

The trash gate requires `filesystem_policy.include_workdir: false` on the
running sandbox. OpenShell errors out (`filesystem include_workdir cannot
be changed on a live sandbox`) if we try to flip it via `openshell policy
set`, so we have to bake the flip in at sandbox creation. The flag is read
from NemoClaw's source tree at onboard time.

## What we patched

The file at `~/.nemoclaw/source/nemoclaw-blueprint/policies/openclaw-sandbox.yaml`.
Before-and-after diff is in [policies/sandbox-base.yaml](../policies/sandbox-base.yaml)
(the after) and `~/.nemoclaw/source/nemoclaw-blueprint/policies/openclaw-sandbox.yaml.meet_a_claw.bak`
(the before).

Summary of the changes:

- `include_workdir: true` → `false`
- Added `/sandbox` to `read_only` (so the agent can still `cd` and read root-owned dotfiles)
- Added these to `read_write`: `/sandbox/.cache`, `/sandbox/.config`, `/sandbox/.npm`,
  `/sandbox/.nv`, `/sandbox/demo/desktop`, `/sandbox/demo/sorted`
- Deliberately did NOT add `/sandbox/demo/trash` — that omission is the gate

## How to restore the original (after demo / before submitting a clean machine)

```bash
cp ~/.nemoclaw/source/nemoclaw-blueprint/policies/openclaw-sandbox.yaml.meet_a_claw.bak \
   ~/.nemoclaw/source/nemoclaw-blueprint/policies/openclaw-sandbox.yaml
nemoclaw hack-agent destroy --yes
nemoclaw onboard --name hack-agent --yes-i-accept-third-party-software
```

## Why not a cleaner mechanism

`nemoclaw onboard` has no `--policy <yaml>` flag. The user-facing override
surface for policy is `openshell policy set` / `policy update` / NemoClaw's
preset `--from-file`, but none of those can change `include_workdir` on a
live sandbox. Modifying the upstream source YAML before re-onboarding is
the documented escape hatch (the file's header comment says: "To add
endpoints: update this file and re-run `nemoclaw onboard`").
