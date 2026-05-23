# policies/

NemoClaw guardrail policies, kept in version control so judges (and future-us) can audit exactly what the agent is allowed to do.

## Two files

- **`filesystem.yaml`** — which paths the sandbox can read vs write. Enforced by OpenShell Landlock at the kernel level. Bypassing this requires escaping the sandbox.
- **`network.yaml`** — which hosts/ports the agent can reach. Enforced by NemoClaw network policy (`enforcement: enforce`, not just `monitor`). Bypassing requires escaping the sandbox network namespace.

## How they're applied

```bash
# from this dir
nemoclaw hack-agent policy-add --from-file ./filesystem.yaml
nemoclaw hack-agent policy-add --from-file ./network.yaml

# verify
nemoclaw hack-agent policy-list
nemoclaw hack-agent status   # shows the resolved, live policy
```

## The Trash gate

`filesystem.yaml` deliberately **omits** `~/.local/share/Trash` from `read_write`. The agent's `request_trash` skill will get an EACCES when it tries to move files there. That's the gate. To open the gate for a session:

```bash
# TODO: define this preset
nemoclaw hack-agent policy-add filesystem-trash
```

The animation layer reads the OCSF audit log (`~/.nemoclaw/audit/<sandbox>.ocsf.log`) and renders a "bounce" when it sees `FS:DENY` events tagged with our skill, and a "gate slides open" when policy reload events show the trash preset becoming active.

## What's *not* in here

- The default presets NemoClaw installed during onboarding (`local-inference`, `clawhub`, `nvidia`, etc.) — those live in NemoClaw's own config. We layer on top; we don't replace them.
- Per-skill IPC permissions inside the sandbox — those are configured at the skill level, not via these YAMLs.
