"""
meet_a_claw overlay — B3 walk + B6 gate state + bounce.

Visuals:
    - Lobster sprite walks between HOME and TRASH_ZONE.
    - A vertical "gate" bar sits between the lobster and the trash zone.
      Color tracks /tmp/meet_a_claw-gate-state:
        contains "open"   → green   (policies/grant-trash.sh just ran)
        contains "closed" → red     (policies/revoke-trash.sh just ran)
        missing           → red     (default; gate is closed)
    - Bounce animation: lobster lerps backward 80 px and snaps back, with
      a small angular wobble. Use this when the agent's trash attempt was
      refused by the policy / marker check.

Controls (operator-driven during demo):
    SPACE  walk to trash zone
    R      walk back home
    B      trigger bounce animation
    ESC    quit

Wiring:
    - The host-side gate state file is the bridge between
      ./policies/{grant,revoke}-trash.sh and this overlay. Filesystem
      event watcher refreshes the visual immediately on change.
    - In a later iteration (Phase 4 B5), agent-driven walk commands will
      come via a WebSocket; for now keypresses are the script.

Run:
    cd /media/ufoai/DATAs3/fromtrx51/workspace/meet_a_claw/ui
    .venv/bin/python overlay.py
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import pyglet
from pyglet import shapes
from pyglet.window import Window, key, mouse
from watchdog.events import FileSystemEventHandler
# PollingObserver avoids inotify so we keep working on machines where
# fs.inotify.max_user_watches is already saturated by IDEs / dev tools.
from watchdog.observers.polling import PollingObserver as Observer

# X11 / Xlib bits used to make the overlay sit on the real desktop:
#   - _NET_WM_STATE_ABOVE       always on top of regular windows
#   - _NET_WM_STATE_SKIP_TASKBAR & _NET_WM_STATE_SKIP_PAGER
#                              hide from alt-tab and taskbar
#   - SHAPE extension (input)  empty input region except the gate, so
#                              clicks pass through to the actual desktop
#                              icons, browser, file manager, etc.
try:
    import Xlib.display
    import Xlib.X
    import Xlib.protocol.event
    from Xlib.ext import shape as xshape
    HAVE_XLIB = True
except ImportError:
    HAVE_XLIB = False

SANDBOX_NAME = "hack-agent"
SANDBOX_DESKTOP_PATH = "/sandbox/demo/desktop"

# Where on the host the demo files live. pre-demo.sh plants the same 7
# files here that it plants inside the sandbox; when the agent moves a
# file inside the sandbox the corresponding host-side file is mirrored
# into the matching dest directory below (so the audience sees their
# real Desktop empty out in real time).
HOST_HOME = Path.home()
HOST_DEMO_DIR = HOST_HOME / "Desktop" / "meet_a_claw-demo"

# Where mirrored files end up on the host. Categories match the
# sandbox-internal sorted/ layout that tidy.sh writes into.
HOST_DEST = {
    "images": HOST_HOME / "Pictures",
    "documents": HOST_HOME / "Documents",
    "archives": HOST_HOME / "Downloads",
    "code": HOST_HOME / "Documents" / "code",
    "media": HOST_HOME / "Videos",
}
# Sandbox paths we poll for new arrivals.
SANDBOX_SORTED_BUCKETS = [
    f"/sandbox/demo/sorted/{name}" for name in HOST_DEST.keys()
]
SANDBOX_TRASH_PATH = "/sandbox/.openclaw/trash"

HERE = Path(__file__).resolve().parent
SPRITE_PATH = HERE / "assets" / "sprites" / "lobster_72.png"
GATE_STATE_FILE = Path("/tmp/meet_a_claw-gate-state")

SPRITE_SCALE = 2.0
SPRITE_PX = int(72 * SPRITE_SCALE)

# Window is sized to the full screen at startup so the lobster can walk
# across the user's real desktop, not just inside a 1400-wide rectangle.
# Falls back to a generous size if the screen probe fails.
STAGE_W = 1920
STAGE_H = 1080

WALK_DURATION_S = 1.8
WALK_BOB_HEIGHT = 8
WALK_BOB_FREQ_HZ = 6

BOUNCE_DURATION_S = 0.55
BOUNCE_RECOIL_PX = 80
BOUNCE_WOBBLE_DEG = 18

# These get re-computed at runtime once we know the real screen size.
# Home is along the left edge, trash zone toward the right, gate just
# in front of the trash so the lobster has to pass through it.
HOME_POS = (200, 200)
TRASH_ZONE_POS = (1600, 200)
GATE_X = 1400
GATE_WIDTH = 14
GATE_HEIGHT = 280
GATE_Y = 70

GATE_COLOR_CLOSED = (220, 60, 60)
GATE_COLOR_OPEN = (80, 200, 120)
GATE_COLOR_PENDING = (235, 190, 50)  # amber/yellow for "in transition"
PENDING_TIMEOUT_S = 10.0  # if the file watcher hasn't settled within this, give up


class LobsterState(Enum):
    IDLE = "idle"
    WALKING = "walking"
    BOUNCING = "bouncing"


@dataclass
class Lobster:
    sprite: pyglet.sprite.Sprite

    state: LobsterState = LobsterState.IDLE

    walk_origin: tuple[float, float] = (0.0, 0.0)
    walk_target: tuple[float, float] = (0.0, 0.0)
    walk_elapsed: float = 0.0
    walk_duration: float = WALK_DURATION_S
    base_y: float = 0.0

    bounce_origin_x: float = 0.0
    bounce_elapsed: float = 0.0

    # Carried file (Phase 4 B4). None when empty-handed. The label is what
    # gets rendered on screen — the actual filesystem op happens in the
    # sandbox via the agent's desktop-trash skill; this is just the visual.
    carried_file: str | None = None

    def pickup(self, filename: str) -> None:
        self.carried_file = filename

    def drop(self) -> None:
        self.carried_file = None

    def walk_to(self, target: tuple[float, float]) -> None:
        if self.state == LobsterState.WALKING:
            self.walk_origin = (self.sprite.x, self.base_y)
        else:
            self.walk_origin = (self.sprite.x, self.sprite.y)
        self.walk_target = target
        self.walk_elapsed = 0.0
        self.base_y = self.walk_origin[1]
        self.sprite.rotation = 0
        self.state = LobsterState.WALKING

    def bounce(self) -> None:
        if self.state == LobsterState.BOUNCING:
            return
        self.bounce_origin_x = self.sprite.x
        self.bounce_elapsed = 0.0
        self.state = LobsterState.BOUNCING

    def update(self, dt: float, gate_open: bool) -> None:
        if self.state == LobsterState.WALKING:
            self._step_walk(dt, gate_open)
        elif self.state == LobsterState.BOUNCING:
            self._step_bounce(dt)

    def _step_walk(self, dt: float, gate_open: bool) -> None:
        self.walk_elapsed += dt
        t = min(1.0, self.walk_elapsed / self.walk_duration)
        eased = 0.5 - 0.5 * math.cos(math.pi * t)
        x = self.walk_origin[0] + (self.walk_target[0] - self.walk_origin[0]) * eased
        y = self.walk_origin[1] + (self.walk_target[1] - self.walk_origin[1]) * eased
        in_motion = 1.0 if 0.05 < t < 0.95 else 0.0
        bob = math.sin(self.walk_elapsed * WALK_BOB_FREQ_HZ * 2 * math.pi) * WALK_BOB_HEIGHT * in_motion
        self.sprite.x = x
        self.sprite.y = y + bob
        self.base_y = y
        dx = self.walk_target[0] - self.walk_origin[0]
        if dx > 0:
            self.sprite.scale_x = abs(self.sprite.scale_x)
        elif dx < 0:
            self.sprite.scale_x = -abs(self.sprite.scale_x)

        # Collision with closed gate. Lobster's right edge reaches the
        # gate's left edge while walking rightward and the gate is shut →
        # cancel the walk and start a bounce. Walking leftward (return
        # home) or with the gate open passes through normally.
        going_right = dx > 0
        right_edge = self.sprite.x + (SPRITE_PX / 2)
        if (
            going_right
            and not gate_open
            and right_edge >= GATE_X
            and self.walk_target[0] > GATE_X  # only intercept if target is past the gate
        ):
            self.sprite.x = GATE_X - (SPRITE_PX / 2) - 4  # park just before the gate
            self.sprite.y = self.base_y
            self.bounce()
            return

        if t >= 1.0:
            self.state = LobsterState.IDLE
            self.sprite.y = self.walk_target[1]
            # Arrived at the destination. If we're carrying a file AND the
            # destination is the trash zone, the file is dropped into the
            # trash (clear carry). Walking back to home keeps the file —
            # operator can decide what happens next.
            if (
                self.carried_file is not None
                and abs(self.walk_target[0] - TRASH_ZONE_POS[0]) < 5
            ):
                self.drop()

    def _step_bounce(self, dt: float) -> None:
        self.bounce_elapsed += dt
        t = min(1.0, self.bounce_elapsed / BOUNCE_DURATION_S)
        # Recoil out and back: a half-sine.
        recoil = math.sin(t * math.pi) * BOUNCE_RECOIL_PX
        # Direction depends on which way the lobster is facing.
        facing_right = self.sprite.scale_x >= 0
        self.sprite.x = self.bounce_origin_x + (-recoil if facing_right else recoil)
        # Angular wobble: starts at 0, peaks mid-bounce, returns.
        self.sprite.rotation = math.sin(t * math.pi) * BOUNCE_WOBBLE_DEG * (1 if facing_right else -1)
        if t >= 1.0:
            self.state = LobsterState.IDLE
            self.sprite.x = self.bounce_origin_x
            self.sprite.rotation = 0


# ── gate state subscriber ──────────────────────────────────────────────


class GateState:
    """Thread-safe holder for the trash gate's state.

    Tracks both the settled state (open/closed, from /tmp/meet_a_claw-
    gate-state) and a 'pending' state (set when the operator clicks to
    toggle; cleared when the watcher sees the file change OR when the
    pending action times out). The 'pending' state lets the overlay
    paint the gate yellow immediately so the operator knows their click
    registered, instead of waiting 2-5 s for the script chain
    (subprocess → nemoclaw exec → policy reload → state file write →
    polling watcher) to settle.
    """

    PENDING_OPENING = "opening"
    PENDING_CLOSING = "closing"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._open = self._read_initial()
        self._pending: str | None = None
        self._pending_started_at: float = 0.0
        self._dirty = True  # force first render

    @staticmethod
    def _read_initial() -> bool:
        try:
            return GATE_STATE_FILE.read_text().strip() == "open"
        except FileNotFoundError:
            return False

    def set_from_file(self) -> None:
        try:
            new = GATE_STATE_FILE.read_text().strip() == "open"
        except FileNotFoundError:
            new = False
        with self._lock:
            changed = new != self._open
            had_pending = self._pending is not None
            self._open = new
            self._pending = None  # settle
            self._pending_started_at = 0.0
            if changed or had_pending:
                self._dirty = True

    def mark_pending(self, direction: str) -> bool:
        """Mark a transition as in-progress. Returns True if accepted
        (caller should kick off the script), False if already pending or
        already in the target state."""
        with self._lock:
            if self._pending is not None:
                return False  # mid-transition; ignore extra clicks
            if direction == self.PENDING_OPENING and self._open:
                return False
            if direction == self.PENDING_CLOSING and not self._open:
                return False
            self._pending = direction
            self._pending_started_at = time.time()
            self._dirty = True
            return True

    def maybe_timeout_pending(self) -> None:
        """Clear a stuck pending state after PENDING_TIMEOUT_S.
        Called from the main loop tick so the UI can recover if the
        script chain dies silently."""
        with self._lock:
            if self._pending is None:
                return
            if time.time() - self._pending_started_at > PENDING_TIMEOUT_S:
                self._pending = None
                self._pending_started_at = 0.0
                self._dirty = True

    def consume_change(self) -> bool:
        """Returns True if anything visual changed since last consume."""
        with self._lock:
            if self._dirty:
                self._dirty = False
                return True
            return False

    @property
    def is_open(self) -> bool:
        with self._lock:
            return self._open

    @property
    def pending(self) -> str | None:
        with self._lock:
            return self._pending


# ── desktop file list from sandbox ─────────────────────────────────────


def _find_sandbox_container() -> str | None:
    """Locate the openshell-hack-agent container by name pattern."""
    try:
        out = subprocess.check_output(
            ["docker", "ps", "--filter", f"name=openshell-{SANDBOX_NAME}",
             "--format", "{{.Names}}"],
            text=True, timeout=5,
        ).strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if not out:
        return None
    return out.splitlines()[0]


def list_sandbox_desktop() -> list[str]:
    """Snapshot the agent's demo desktop directory. Empty on failure."""
    container = _find_sandbox_container()
    if not container:
        return []
    try:
        out = subprocess.check_output(
            ["docker", "exec", "--user", "sandbox", container,
             "ls", "-1", SANDBOX_DESKTOP_PATH],
            text=True, timeout=5, stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def _docker_ls(container: str, path: str) -> list[str]:
    try:
        out = subprocess.check_output(
            ["docker", "exec", "--user", "sandbox", container, "ls", "-1", path],
            text=True, timeout=3, stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def _mirror_file_on_host(filename: str, bucket: str) -> str:
    """Apply a sandbox-detected move to the host's demo desktop. Returns a
    short status string for logging. Idempotent: if the source file is
    already missing, returns 'gone'."""
    src = HOST_DEMO_DIR / filename
    if not src.exists():
        return "gone"
    if bucket == "trash":
        # Prefer XDG trash via gio when available, fall back to outright
        # rm if the host doesn't ship gio (rare on Linux desktops).
        if shutil.which("gio"):
            try:
                subprocess.run(["gio", "trash", str(src)], check=False, timeout=5)
                return "trashed (gio)"
            except subprocess.TimeoutExpired:
                pass
        try:
            src.unlink()
            return "trashed (unlink)"
        except OSError as e:
            return f"trash-fail:{e}"
    dest_dir = HOST_DEST.get(bucket)
    if dest_dir is None:
        return f"unknown-bucket:{bucket}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    try:
        shutil.move(str(src), str(dest))
        return f"moved → {dest_dir.name}/"
    except OSError as e:
        return f"move-fail:{e}"


class SandboxMirror(threading.Thread):
    """Polls the sandbox for newly-sorted / newly-trashed files and
    mirrors the equivalent action on the host's demo desktop. Runs as a
    daemon thread; main loop reads its log queue for UI status.
    """

    POLL_INTERVAL_S = 1.5

    def __init__(self, container_resolver):
        super().__init__(name="SandboxMirror", daemon=True)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._processed: set[tuple[str, str]] = set()
        self.last_action: tuple[float, str] | None = None  # (timestamp, msg)
        self._resolver = container_resolver  # callable returning current container

    def run(self) -> None:
        while not self._stop.is_set():
            container = self._resolver()
            if container:
                # Sorted buckets.
                for path in SANDBOX_SORTED_BUCKETS:
                    bucket = Path(path).name
                    for filename in _docker_ls(container, path):
                        key_ = (bucket, filename)
                        if key_ in self._processed:
                            continue
                        status = _mirror_file_on_host(filename, bucket)
                        with self._lock:
                            self._processed.add(key_)
                            self.last_action = (time.time(), f"{filename} → {status}")
                # Trash.
                for filename in _docker_ls(container, SANDBOX_TRASH_PATH):
                    key_ = ("trash", filename)
                    if key_ in self._processed:
                        continue
                    status = _mirror_file_on_host(filename, "trash")
                    with self._lock:
                        self._processed.add(key_)
                        self.last_action = (time.time(), f"{filename} → {status}")
            self._stop.wait(self.POLL_INTERVAL_S)

    def reset(self) -> None:
        """Clear processed-file cache. Call from pre-demo / on operator
        manual reset so a fresh round of files isn't filtered out."""
        with self._lock:
            self._processed.clear()
            self.last_action = None

    def consume_last_action(self) -> tuple[float, str] | None:
        with self._lock:
            return self.last_action

    def stop(self) -> None:
        self._stop.set()


class _GateFileHandler(FileSystemEventHandler):
    def __init__(self, state: GateState) -> None:
        self.state = state

    def on_any_event(self, event):  # noqa: D401
        if event.is_directory:
            return
        if Path(event.src_path) == GATE_STATE_FILE:
            self.state.set_from_file()


def start_gate_watcher(state: GateState) -> Observer:
    handler = _GateFileHandler(state)
    # Poll every 500 ms — plenty for a human-driven operator action and
    # cheap (the file is 4-8 bytes on tmpfs).
    observer = Observer(timeout=0.5)
    # Watch the parent dir so we catch creation events too.
    observer.schedule(handler, str(GATE_STATE_FILE.parent), recursive=False)
    observer.daemon = True
    observer.start()
    return observer


# ── pyglet plumbing ────────────────────────────────────────────────────


def make_window() -> Window:
    """Borderless, transparent, full-screen overlay anchored at (0,0).
    X11 atoms + SHAPE input region are applied in main() once the
    window has a real X11 ID."""
    config = pyglet.gl.Config(alpha_size=8, double_buffer=True)
    window = Window(
        width=STAGE_W,
        height=STAGE_H,
        config=config,
        style=Window.WINDOW_STYLE_BORDERLESS,
        caption="meet_a_claw",
        resizable=False,
    )
    window.set_location(0, 0)
    return window


def _pyglet_window_xid(window) -> int | None:
    """Best-effort lookup of the underlying X11 window id from a pyglet
    window. pyglet 2.x exposes it as either window._window or via
    canvas.id depending on the platform plugin."""
    for path in (
        lambda w: w._window,
        lambda w: w.canvas._window,
        lambda w: w.context.canvas.window,
        lambda w: w._native_handle,
    ):
        try:
            xid = path(window)
            if isinstance(xid, int) and xid > 0:
                return xid
        except (AttributeError, TypeError):
            continue
    return None


def make_overlay_native_on_desktop(window, gate_rect_screen: tuple[int, int, int, int]) -> None:
    """Promote the pyglet window to a click-through, always-on-top
    desktop overlay using X11 atoms + SHAPE.

    gate_rect_screen is (x, y, w, h) in screen coordinates (y from top),
    the only region that catches clicks. Everything else passes through
    to the desktop icons / app windows underneath.
    """
    if not HAVE_XLIB:
        print("[overlay] python-xlib missing; running as a regular window", file=sys.stderr)
        return

    xid = _pyglet_window_xid(window)
    if xid is None:
        print("[overlay] could not locate pyglet's X11 window id; SHAPE skipped", file=sys.stderr)
        return

    xdisplay = Xlib.display.Display()
    xwin = xdisplay.create_resource_object("window", xid)

    NET_WM_STATE = xdisplay.intern_atom("_NET_WM_STATE")
    ABOVE = xdisplay.intern_atom("_NET_WM_STATE_ABOVE")
    SKIP_TASKBAR = xdisplay.intern_atom("_NET_WM_STATE_SKIP_TASKBAR")
    SKIP_PAGER = xdisplay.intern_atom("_NET_WM_STATE_SKIP_PAGER")

    # Single ClientMessage can carry up to 2 atoms via data[2] and data[3].
    # Apply (ABOVE, SKIP_TASKBAR) and (SKIP_PAGER, 0) in two passes.
    for atom_a, atom_b in [(ABOVE, SKIP_TASKBAR), (SKIP_PAGER, 0)]:
        data = (32, [1, atom_a, atom_b, 0, 0])
        ev = Xlib.protocol.event.ClientMessage(
            window=xwin, client_type=NET_WM_STATE, data=data
        )
        xdisplay.send_event(
            xdisplay.screen().root,
            ev,
            event_mask=Xlib.X.SubstructureRedirectMask | Xlib.X.SubstructureNotifyMask,
        )
    xdisplay.sync()

    # SHAPE input: keep ONLY the gate region clickable; clicks anywhere
    # else fall through to whatever is behind the overlay (desktop, file
    # manager, browser, terminal). The gate rectangle is in pyglet's
    # bottom-left-origin pixel space; SHAPE input wants top-left, which
    # matches pyglet's set_location and the way Xlib reports things, so
    # we pass it through unchanged.
    #
    # python-xlib exposes the request as a method on the Window object
    # (shape_rectangles), not as a module-level SetRectangles call.
    gx, gy, gw, gh = gate_rect_screen
    xwin.shape_rectangles(
        operation=xshape.SO.Set,
        destination_kind=xshape.SK.Input,
        ordering=0,  # Unsorted
        x_offset=0,
        y_offset=0,
        rectangles=[(int(gx), int(gy), int(gw), int(gh))],
    )
    xdisplay.sync()
    print(f"[overlay] X11 SHAPE input set to gate rect {gate_rect_screen}; rest click-through")


def main() -> int:
    if not SPRITE_PATH.exists():
        print(f"sprite missing: {SPRITE_PATH}", file=sys.stderr)
        return 1

    # Probe real screen size and re-anchor the lobster's geography so
    # the demo scales to whatever the operator's monitor is.
    global STAGE_W, STAGE_H, HOME_POS, TRASH_ZONE_POS, GATE_X, GATE_Y, GATE_HEIGHT
    try:
        _disp = pyglet.display.get_display()
        _scr = _disp.get_default_screen()
        STAGE_W = _scr.width
        STAGE_H = _scr.height
    except Exception:
        pass  # keep defaults
    HOME_POS = (max(160, int(STAGE_W * 0.10)), max(180, int(STAGE_H * 0.20)))
    TRASH_ZONE_POS = (int(STAGE_W * 0.84), HOME_POS[1])
    GATE_X = int(STAGE_W * 0.72)
    GATE_HEIGHT = max(220, int(STAGE_H * 0.32))
    GATE_Y = HOME_POS[1] - int(GATE_HEIGHT * 0.3)
    print(f"[overlay] screen {STAGE_W}x{STAGE_H}; HOME={HOME_POS} TRASH={TRASH_ZONE_POS} GATE_X={GATE_X}")

    window = make_window()
    sprite_img = pyglet.image.load(str(SPRITE_PATH))
    sprite_img.anchor_x = sprite_img.width // 2
    sprite_img.anchor_y = sprite_img.height // 2
    sprite = pyglet.sprite.Sprite(img=sprite_img, x=HOME_POS[0], y=HOME_POS[1])
    sprite.scale = SPRITE_SCALE

    lobster = Lobster(sprite=sprite, base_y=HOME_POS[1])

    gate_state = GateState()
    gate_observer = start_gate_watcher(gate_state)

    # Container resolver — re-checked on each poll so a sandbox restart
    # while the overlay is running doesn't break mirroring.
    mirror_thread = SandboxMirror(_find_sandbox_container)
    mirror_thread.start()

    # Path to the grant/revoke scripts so a click on the gate runs them.
    REPO_DIR = HERE.parent
    GRANT_SCRIPT = REPO_DIR / "policies" / "grant-trash.sh"
    REVOKE_SCRIPT = REPO_DIR / "policies" / "revoke-trash.sh"

    def toggle_gate_from_click():
        # Reserve the pending slot first so the gate paints yellow on the
        # very next frame. If a transition is already in flight, ignore
        # the click — visual is already showing it.
        is_open = gate_state.is_open
        direction = GateState.PENDING_CLOSING if is_open else GateState.PENDING_OPENING
        if not gate_state.mark_pending(direction):
            print(f"[click-gate] ignored — already {gate_state.pending or 'in target state'}")
            return
        target = REVOKE_SCRIPT if is_open else GRANT_SCRIPT
        if not target.exists():
            print(f"[click-gate] script missing: {target}", file=sys.stderr)
            return
        # Spawn detached — don't block the UI thread on the subprocess.
        try:
            subprocess.Popen(
                [str(target), SANDBOX_NAME],
                cwd=str(REPO_DIR),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"[click-gate] triggered {target.name} (pending {direction})")
        except OSError as e:
            print(f"[click-gate] {target.name} spawn failed: {e}", file=sys.stderr)

    # Carried-file visual: a single page rectangle + text label above.
    # System fonts on this box don't ship color emoji, so we draw the
    # icon ourselves instead of relying on 📄.
    carry_label = pyglet.text.Label(
        "",
        font_name="Sans", font_size=11, color=(40, 30, 20, 230),
        x=0, y=0, anchor_x="center", anchor_y="bottom",
    )
    carry_bg = shapes.Rectangle(
        x=0, y=0, width=10, height=10,
        color=(255, 255, 255),
    )
    carry_bg.opacity = 230
    carry_page = shapes.Rectangle(
        x=0, y=0, width=20, height=24,
        color=(245, 240, 220),
    )

    # Real file list from the sandbox. Each pickup pops one off; D drops
    # back to the front; reaching the trash zone with a file = permanent
    # removal (the actual sandbox-side mv is the agent's job, not ours).
    available_files: list[str] = list_sandbox_desktop()
    print(f"  desktop snapshot: {len(available_files)} file(s) — {available_files!r}")

    initial_color = GATE_COLOR_OPEN if gate_state.is_open else GATE_COLOR_CLOSED
    gate_shape = shapes.Rectangle(
        x=GATE_X, y=GATE_Y, width=GATE_WIDTH, height=GATE_HEIGHT,
        color=initial_color,
    )

    # Transparent background — the overlay literally sits on top of the
    # user's real desktop now.
    pyglet.gl.glClearColor(0.0, 0.0, 0.0, 0.0)
    # On-screen instructions live in the operator terminal now; the
    # desktop overlay only shows the lobster, the gate, and a tiny
    # mirror-status hint near the gate.
    mirror_label = pyglet.text.Label(
        "mirror: idle",
        font_name="Sans", font_size=11, color=(40, 40, 40, 230),
        x=GATE_X + 30, y=GATE_Y + GATE_HEIGHT + 30, anchor_x="left",
    )
    desktop_label = pyglet.text.Label(
        text=f"desktop: {len(available_files)} file(s)",
        font_name="Sans", font_size=11, color=(80, 60, 40, 200),
        x=12, y=STAGE_H - 38,
    )

    def refresh_desktop_label() -> None:
        desktop_label.text = f"desktop: {len(available_files)} file(s)"
    gate_label = pyglet.text.Label(
        "gate: CLOSED (click to open)", font_name="Sans", font_size=11, color=(80, 60, 40, 200),
        x=GATE_X - 110, y=GATE_Y + GATE_HEIGHT + 8,
    )

    def refresh_gate_label_and_color() -> None:
        pending = gate_state.pending
        if pending == GateState.PENDING_OPENING:
            gate_shape.color = GATE_COLOR_PENDING
            gate_label.text = "gate: OPENING…"
        elif pending == GateState.PENDING_CLOSING:
            gate_shape.color = GATE_COLOR_PENDING
            gate_label.text = "gate: CLOSING…"
        elif gate_state.is_open:
            gate_shape.color = GATE_COLOR_OPEN
            gate_label.text = "gate: OPEN (click to close)"
        else:
            gate_shape.color = GATE_COLOR_CLOSED
            gate_label.text = "gate: CLOSED (click to open)"

    refresh_gate_label_and_color()

    def position_carry():
        # The page icon + label hug the upper-right of the sprite's hitbox
        # so they bob and bounce with the lobster naturally.
        sx, sy = lobster.sprite.x, lobster.sprite.y
        offset_x = 26
        offset_y = SPRITE_PX / 2 + 4
        # Page icon sits just above the sprite.
        carry_page.x = sx + offset_x - 10  # center 20-wide page on offset_x
        carry_page.y = sy + offset_y
        # Text label above the page.
        carry_label.x = sx + offset_x
        carry_label.y = sy + offset_y + 28
        # Background pill behind label.
        text_w = carry_label.content_width + 14
        text_h = carry_label.content_height + 4
        carry_bg.x = carry_label.x - text_w / 2
        carry_bg.y = carry_label.y - 2
        carry_bg.width = text_w
        carry_bg.height = text_h

    @window.event
    def on_draw():
        window.clear()
        gate_shape.draw()
        gate_label.draw()
        lobster.sprite.draw()
        if lobster.carried_file is not None:
            position_carry()
            carry_page.draw()
            carry_bg.draw()
            carry_label.draw()
        mirror_label.draw()

    # Generous hitbox so the operator doesn't have to be pixel-perfect
    # during a live demo. 20-pixel padding on each side of the gate bar.
    GATE_CLICK_PAD = 20

    @window.event
    def on_mouse_press(x, y, button, modifiers):
        if button != mouse.LEFT:
            return
        if not (GATE_X - GATE_CLICK_PAD <= x <= GATE_X + GATE_WIDTH + GATE_CLICK_PAD):
            return
        if not (GATE_Y - GATE_CLICK_PAD <= y <= GATE_Y + GATE_HEIGHT + GATE_CLICK_PAD):
            return
        toggle_gate_from_click()

    @window.event
    def on_key_press(symbol, modifiers):
        if symbol == key.ESCAPE:
            pyglet.app.exit()
        elif symbol == key.SPACE:
            lobster.walk_to(TRASH_ZONE_POS)
        elif symbol == key.R:
            lobster.walk_to(HOME_POS)
        elif symbol == key.B:
            lobster.bounce()
        elif symbol == key.P:
            if lobster.carried_file is None and available_files:
                picked = available_files.pop(0)
                lobster.pickup(picked)
                carry_label.text = picked
                refresh_desktop_label()
        elif symbol == key.D:
            if lobster.carried_file is not None:
                # Put back at the front of the list (will be picked up
                # again on next P).
                available_files.insert(0, lobster.carried_file)
                lobster.drop()
                refresh_desktop_label()
        elif symbol == key.F:
            # Refresh the desktop snapshot from sandbox.
            new_list = list_sandbox_desktop()
            available_files.clear()
            available_files.extend(new_list)
            refresh_desktop_label()
            print(f"  refreshed: {len(available_files)} file(s) — {available_files!r}")

    def tick(dt: float):
        gate_state.maybe_timeout_pending()
        if gate_state.consume_change():
            refresh_gate_label_and_color()
        # Lobster only walks through when the gate has actually settled
        # to OPEN — a pending transition does not yet grant passage.
        lobster.update(dt, gate_open=gate_state.is_open and gate_state.pending is None)
        # Refresh the mirror status label so the audience can see what
        # just happened on their host desktop.
        last = mirror_thread.consume_last_action()
        if last:
            age = time.time() - last[0]
            if age < 4.0:
                mirror_label.text = f"mirror: {last[1]}"
            elif mirror_label.text != "mirror: idle":
                mirror_label.text = "mirror: idle"

    pyglet.clock.schedule_interval(tick, 1 / 60)

    # Promote to a click-through, always-on-top desktop overlay. SHAPE
    # converts X11 coordinates (top-left origin), so we mirror y here:
    # pyglet's gate is at (GATE_X, GATE_Y) in bottom-left-origin pixels.
    gate_top = STAGE_H - GATE_Y - GATE_HEIGHT
    # Generous padding so the operator can click the bar without missing.
    pad = 30
    make_overlay_native_on_desktop(
        window,
        gate_rect_screen=(
            int(GATE_X) - pad,
            int(gate_top) - pad,
            int(GATE_WIDTH) + 2 * pad,
            int(GATE_HEIGHT) + 2 * pad,
        ),
    )

    print("meet_a_claw overlay — desktop-native (transparent, click-through except gate).")
    print(f"  gate state file:   {GATE_STATE_FILE}")
    print(f"  host demo desktop: {HOST_DEMO_DIR}")
    print(f"  click the gate to toggle.  Keys (when overlay has focus): SPACE/R/B/P/D/F/ESC.")
    try:
        pyglet.app.run()
    finally:
        gate_observer.stop()
        gate_observer.join(timeout=2.0)
        mirror_thread.stop()
        mirror_thread.join(timeout=2.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
