# meet_a_claw custom sandbox image.
#
# Inherits the pinned OpenClaw sandbox image and pre-creates the directories
# the agent needs at runtime. We need this because the modified base policy
# (~/.nemoclaw/source/nemoclaw-blueprint/policies/openclaw-sandbox.yaml) flips
# include_workdir to false, so /sandbox itself is read-only inside the running
# sandbox. Without these dirs being pre-created (as the sandbox user) at image
# build time, the agent would have no writable place to put .npm, .cache, the
# demo scratch space, etc.
#
# Build flow: nemoclaw onboard --from ops/sandbox.Dockerfile uses this as the
# image source.
#
# Image pinning: digest matches blueprint.yaml's components.sandbox.image as of
# blueprint version 0.1.0 (NemoClaw v0.1.0 alpha, 2026-05).

FROM ghcr.io/nvidia/openshell-community/sandboxes/openclaw@sha256:b3d832b596ab6b7184a9dcb4ae93337ca32851a4f93b00765cc12de26baa3a9a

USER root
RUN mkdir -p \
        /sandbox/.cache \
        /sandbox/.config \
        /sandbox/.npm \
        /sandbox/.nv \
        /sandbox/demo/desktop \
        /sandbox/demo/sorted/images \
        /sandbox/demo/sorted/documents \
        /sandbox/demo/sorted/archives \
        /sandbox/demo/sorted/code \
        /sandbox/demo/sorted/media \
        /sandbox/demo/trash \
    && chown -R sandbox:sandbox \
        /sandbox/.cache \
        /sandbox/.config \
        /sandbox/.npm \
        /sandbox/.nv \
        /sandbox/demo

# Note: /sandbox/demo/trash IS created here (so mv has a valid destination)
# but the policy will NOT grant write access. Landlock denies the syscall
# before it ever reaches the filesystem; the dir just sits there empty.

USER sandbox
