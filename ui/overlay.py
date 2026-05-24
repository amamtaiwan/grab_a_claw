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
import queue
import re
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
    import Xlib.Xatom
    import Xlib.protocol.event
    from Xlib.ext import shape as xshape
    HAVE_XLIB = True
except ImportError:
    HAVE_XLIB = False

import json


def load_icon_positions() -> dict[str, tuple[int, int]]:
    """Read screen-coordinate icon positions written by pre-demo.sh.
    Returns {filename: (screen_x, screen_y)} where screen coords are
    top-left-origin (the format gio / ding use)."""
    if not POSITIONS_FILE.exists():
        return {}
    try:
        items = json.loads(POSITIONS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return {
        item["name"]: (int(item["screen_x"]), int(item["screen_y"]))
        for item in items
        if "name" in item and "screen_x" in item and "screen_y" in item
    }


def screen_to_pyglet(sx: int, sy: int, window_origin_x: int, window_origin_y: int,
                     window_h: int, screen_h: int) -> tuple[float, float]:
    """Convert a screen (top-left-origin) coord to a pyglet
    (bottom-left-origin) coord inside our overlay window."""
    px = sx - window_origin_x
    # screen_y is measured from top; pyglet y is measured from bottom
    # of the window. Window bottom in screen coords = window_origin_y + window_h.
    py = (window_origin_y + window_h) - sy
    return px, py

SANDBOX_NAME = "hack-agent"
SANDBOX_DESKTOP_PATH = "/sandbox/demo/desktop"
SANDBOX_DENIED_FILE = "/sandbox/.openclaw/state/last-tidy-denied.txt"
SANDBOX_INTENT_FILE = "/sandbox/.openclaw/state/desktop-intents.jsonl"

# Where on the host the demo files live. pre-demo.sh plants the same 7
# files DIRECTLY on the user's ~/Desktop (top level) so they appear as
# real desktop icons with positions set via gio metadata. When the agent
# moves a file inside the sandbox, the corresponding host-side file is
# mirrored from ~/Desktop into the matching dest directory below — the
# audience sees real desktop icons drain in real time.
HOST_HOME = Path.home()
HOST_DEMO_DIR = HOST_HOME / "Desktop"

# JSON file written by scripts/pre-demo.sh with the screen-coord
# position of each planted demo icon. Lobster walks to those positions.
POSITIONS_FILE = Path("/tmp/meet_a_claw-positions.json")

# Where mirrored files end up on the host. To keep the demo's payoff
# *visible on the desktop*, we drop into sibling folders directly on
# ~/Desktop instead of sending them off to ~/Pictures / ~/Documents
# where the audience can't see them. pre-demo.sh creates these folders
# and sets their icon positions via gio so the lobster has a known
# screen-coord drop zone for each bucket.
HOST_DEST = {
    "images":    HOST_HOME / "Desktop" / "Images",
    "documents": HOST_HOME / "Desktop" / "Documents",
    "archives":  HOST_HOME / "Desktop" / "Archives",
    "code":      HOST_HOME / "Desktop" / "Code",
    "media":     HOST_HOME / "Desktop" / "Media",
}
# Screen positions where the bucket-folder icons live on the desktop.
# Matches the layout pre-demo.sh sets via gio. Used to convert into
# pyglet drop zones once the overlay knows the window origin.
HOST_FOLDER_SCREEN_POS = {
    "images":    (200,  420),
    "documents": (550,  420),
    "archives":  (900,  420),
    "code":      (1250, 420),
    "media":     (1600, 420),
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
class PickupTask:
    """A queued real-file move: walk to icon, perform host mv, walk to
    drop zone, drop. Phases are 'to_source' then 'to_dest'.
    do_host_op=False is for events that fired AFTER the host filesystem
    already changed (e.g. agent did gio set directly) — then the lobster
    only needs to animate, not re-do the host operation."""
    filename: str
    bucket: str
    source_pos: tuple[float, float]
    dest_pos: tuple[float, float]
    phase: str = "to_source"
    do_host_op: bool = True


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

    # Current pickup task — set when the mirror queue dispatches a job
    # to the lobster. Fields encode the two-phase walk:
    #   phase=='to_source' → walking to the icon's screen position; do
    #       the host mv on arrival, then transition.
    #   phase=='to_dest'   → walking to the bucket drop zone; clear
    #       carried_file on arrival and finish the task.
    pickup_task: "PickupTask | None" = None

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


class DesktopArrangeBroker(threading.Thread):
    """Polls the sandbox-internal intent file
    (/sandbox/.openclaw/state/desktop-intents.jsonl). Each new JSON line
    is one intent the agent queued via the desktop-arrange skill — we
    execute the host-side equivalent here. Trash intents are gated on
    /tmp/meet_a_claw-gate-state; closed → bounce event, no host op.

    Architecture: sandbox proposes, host (this thread) disposes. No
    host filesystem is ever touched from inside the sandbox. The
    DesktopWatcher below catches the resulting position changes /
    removals and pushes them into the lobster animation queue.
    """

    POLL_INTERVAL_S = 1.0
    GATE_FILE = Path("/tmp/meet_a_claw-gate-state")

    def __init__(self, container_resolver, event_queue: "queue.Queue"):
        super().__init__(name="DesktopArrangeBroker", daemon=True)
        self._stop = threading.Event()
        self._resolver = container_resolver
        self._queue = event_queue
        self._processed_lines = 0

    def run(self) -> None:
        while not self._stop.is_set():
            container = self._resolver()
            if container:
                lines = self._read_intents(container)
                if len(lines) > self._processed_lines:
                    for line in lines[self._processed_lines:]:
                        self._handle_line(line)
                    self._processed_lines = len(lines)
            self._stop.wait(self.POLL_INTERVAL_S)

    @staticmethod
    def _read_intents(container: str) -> list[str]:
        try:
            out = subprocess.check_output(
                ["docker", "exec", "--user", "sandbox", container,
                 "cat", SANDBOX_INTENT_FILE],
                text=True, timeout=3, stderr=subprocess.DEVNULL,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
                FileNotFoundError, OSError):
            return []
        return [line for line in out.splitlines() if line.strip()]

    def reset_cursor(self) -> None:
        """Call after pre-demo.sh wipes the intent file so the broker
        starts re-reading from line 0."""
        self._processed_lines = 0

    def _handle_line(self, line: str) -> None:
        try:
            intent = json.loads(line)
        except json.JSONDecodeError:
            print(f"[broker] bad JSON line ignored: {line!r}", file=sys.stderr)
            return
        action = intent.get("action")
        filename = intent.get("file")
        if not action or not filename:
            print(f"[broker] missing action/file: {intent}", file=sys.stderr)
            return
        path = HOST_HOME / "Desktop" / filename
        if action == "set_position":
            x = intent.get("x")
            y = intent.get("y")
            if x is None or y is None:
                return
            try:
                subprocess.run(
                    ["gio", "set", str(path), "metadata::nautilus-icon-position", f"{x},{y}"],
                    timeout=3, check=False,
                )
                print(f"[broker] set_position {filename} → ({x},{y})")
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                print(f"[broker] set_position failed: {e}", file=sys.stderr)
        elif action == "trash":
            state = ""
            try:
                state = self.GATE_FILE.read_text().strip()
            except (OSError, FileNotFoundError):
                state = "closed"
            if state != "open":
                # Closed gate → emit denied animation; don't touch host.
                self._queue.put(("denied", filename))
                print(f"[broker] trash {filename} BLOCKED (gate closed) — denied event queued")
                return
            try:
                subprocess.run(["gio", "trash", str(path)], timeout=3, check=False)
                print(f"[broker] trash {filename} → host trash (gate was open)")
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                print(f"[broker] trash failed: {e}", file=sys.stderr)
        else:
            print(f"[broker] unknown action {action!r}: {intent}", file=sys.stderr)

    def stop(self) -> None:
        self._stop.set()


class DesktopWatcher(threading.Thread):
    """Polls ~/Desktop for icon position changes and file removals that
    the agent (or anyone else) did via gio set / gio trash directly.
    Emits ('rearrange', filename, old_screen_pos, new_screen_pos) when an
    icon moves, and ('vanished', filename, old_screen_pos) when a file
    disappears from the top of ~/Desktop. The main loop turns each event
    into a lobster walk.
    """

    POLL_INTERVAL_S = 1.5
    CLAIM_WINDOW_S = 30.0  # SandboxMirror claims its filenames; we skip them

    def __init__(self, event_queue: "queue.Queue", claims: dict):
        super().__init__(name="DesktopWatcher", daemon=True)
        self._stop = threading.Event()
        self._queue = event_queue
        self._claims = claims
        self._last_positions: dict[str, tuple[int, int]] = {}
        self._primed = False

    def run(self) -> None:
        while not self._stop.is_set():
            current = self._snapshot()
            now = time.time()
            if self._primed:
                for name, pos in current.items():
                    last = self._last_positions.get(name)
                    if last is not None and last != pos and not self._claimed(name, now):
                        self._queue.put(("rearrange", name, last, pos))
                for name, last in self._last_positions.items():
                    if name not in current and not self._claimed(name, now):
                        self._queue.put(("vanished", name, last))
            self._last_positions = current
            self._primed = True
            self._stop.wait(self.POLL_INTERVAL_S)

    def _claimed(self, name: str, now: float) -> bool:
        ts = self._claims.get(name)
        return ts is not None and (now - ts) < self.CLAIM_WINDOW_S

    def _snapshot(self) -> dict[str, tuple[int, int]]:
        positions: dict[str, tuple[int, int]] = {}
        desktop = HOST_HOME / "Desktop"
        try:
            entries = list(desktop.iterdir())
        except OSError:
            return positions
        for entry in entries:
            if entry.name.startswith("."):
                continue
            pos = self._read_position(entry)
            if pos is not None:
                positions[entry.name] = pos
        return positions

    @staticmethod
    def _read_position(path: Path) -> tuple[int, int] | None:
        try:
            out = subprocess.check_output(
                ["gio", "info", str(path), "-a", "metadata::nautilus-icon-position"],
                text=True, timeout=2, stderr=subprocess.DEVNULL,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
                FileNotFoundError, OSError):
            return None
        m = re.search(r"nautilus-icon-position:\s*(-?\d+),(-?\d+)", out)
        if not m:
            return None
        return int(m.group(1)), int(m.group(2))

    def stop(self) -> None:
        self._stop.set()


class SandboxMirror(threading.Thread):
    """Polls the sandbox for newly-sorted / newly-trashed files. Instead
    of mirroring to the host immediately, pushes (bucket, filename)
    events to a thread-safe queue. The main loop pairs each event with a
    lobster walk: walk to the file's real icon position, then perform
    the host mv when the lobster arrives, then walk to the bucket's drop
    zone. That way the audience sees the lobster reach the icon BEFORE
    the file disappears from the desktop.
    """

    POLL_INTERVAL_S = 1.5

    def __init__(self, container_resolver, event_queue: "queue.Queue", claims: dict):
        super().__init__(name="SandboxMirror", daemon=True)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._processed: set[tuple[str, str]] = set()
        self.last_action: tuple[float, str] | None = None  # (timestamp, msg)
        self._resolver = container_resolver
        self._queue = event_queue
        # Shared with DesktopWatcher so it knows which filenames sandbox
        # already handled and won't double-animate the disappearance.
        self._claims = claims

    def run(self) -> None:
        while not self._stop.is_set():
            container = self._resolver()
            if container:
                for path in SANDBOX_SORTED_BUCKETS:
                    bucket = Path(path).name
                    for filename in _docker_ls(container, path):
                        key_ = (bucket, filename)
                        with self._lock:
                            if key_ in self._processed:
                                continue
                            self._processed.add(key_)
                        self._claims[filename] = time.time()
                        self._queue.put(("move", bucket, filename))
                for filename in _docker_ls(container, SANDBOX_TRASH_PATH):
                    key_ = ("trash", filename)
                    with self._lock:
                        if key_ in self._processed:
                            continue
                        self._processed.add(key_)
                    self._claims[filename] = time.time()
                    self._queue.put(("trash", "trash", filename))
                # Files the sandbox decided to trash but the marker was
                # absent — they stayed on the host desktop, but the
                # overlay should still animate "lobster walked the file,
                # bounced off the gate, brought it back."
                for filename in self._read_denied_list(container):
                    key_ = ("denied", filename)
                    with self._lock:
                        if key_ in self._processed:
                            continue
                        self._processed.add(key_)
                    self._claims[filename] = time.time()
                    self._queue.put(("denied", filename))
            self._stop.wait(self.POLL_INTERVAL_S)

    def reset(self) -> None:
        with self._lock:
            self._processed.clear()
            self.last_action = None

    @staticmethod
    def _read_denied_list(container: str) -> list[str]:
        try:
            out = subprocess.check_output(
                ["docker", "exec", "--user", "sandbox", container,
                 "cat", SANDBOX_DENIED_FILE],
                text=True, timeout=3, stderr=subprocess.DEVNULL,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
                FileNotFoundError, OSError):
            return []
        return [line.strip() for line in out.splitlines() if line.strip()]

    def report(self, msg: str) -> None:
        with self._lock:
            self.last_action = (time.time(), msg)

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


def make_window(origin_x: int, origin_y: int, width: int, height: int) -> Window:
    """Transparent, borderless overlay anchored at (origin_x, origin_y).
    X11 atoms + SHAPE input region are applied in main() once the
    window has a real X11 ID."""
    # WINDOW_STYLE_OVERLAY tells pyglet to pick an ARGB visual on X11 so
    # glClearColor(0,0,0,0) actually shows through to the compositor.
    # WINDOW_STYLE_BORDERLESS gives an opaque 24-bit visual even when we
    # ask for alpha_size=8. WINDOW_STYLE_TRANSPARENT is similar but with
    # taskbar entry; OVERLAY suppresses the taskbar too.
    config = pyglet.gl.Config(alpha_size=8, double_buffer=True, depth_size=0)
    for style in (
        Window.WINDOW_STYLE_OVERLAY,
        Window.WINDOW_STYLE_TRANSPARENT,
        Window.WINDOW_STYLE_BORDERLESS,  # last resort, will be opaque
    ):
        try:
            window = Window(
                width=width,
                height=height,
                config=config,
                style=style,
                caption="meet_a_claw",
                resizable=False,
            )
            print(f"[overlay] window style: {style}")
            break
        except pyglet.window.NoSuchConfigException:
            continue
    else:
        # absolute fallback with no special config
        window = Window(
            width=width, height=height,
            style=Window.WINDOW_STYLE_BORDERLESS,
            caption="meet_a_claw", resizable=False,
        )
        print("[overlay] window style: default (no transparency available)")
    window.set_location(origin_x, origin_y)
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

    NET_WM_WINDOW_TYPE = xdisplay.intern_atom("_NET_WM_WINDOW_TYPE")
    TYPE_DESKTOP = xdisplay.intern_atom("_NET_WM_WINDOW_TYPE_DESKTOP")
    NET_WM_STATE = xdisplay.intern_atom("_NET_WM_STATE")
    SKIP_TASKBAR = xdisplay.intern_atom("_NET_WM_STATE_SKIP_TASKBAR")
    SKIP_PAGER = xdisplay.intern_atom("_NET_WM_STATE_SKIP_PAGER")
    BELOW = xdisplay.intern_atom("_NET_WM_STATE_BELOW")

    # Tag the window as desktop-class. WMs that honor _NET_WM_WINDOW_TYPE
    # (mutter, kwin, openbox, ...) will park it on the desktop layer
    # above the wallpaper but below every regular app window. This also
    # sidesteps Ubuntu Dock's intelli-hide because desktop-class windows
    # don't count as "a window touching the dock."
    xwin.change_property(
        NET_WM_WINDOW_TYPE,
        Xlib.Xatom.ATOM,
        32,
        [TYPE_DESKTOP],
        mode=Xlib.X.PropModeReplace,
    )

    # Suppress taskbar / alt-tab, and explicitly mark as BELOW so any
    # late-arriving WM that doesn't read the type atom still gets the
    # z-order right.
    for atom_a, atom_b in [(SKIP_TASKBAR, SKIP_PAGER), (BELOW, 0)]:
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
    screen_w, screen_h = STAGE_W, STAGE_H
    try:
        _disp = pyglet.display.get_display()
        _scr = _disp.get_default_screen()
        screen_w, screen_h = _scr.width, _scr.height
    except Exception:
        pass  # keep defaults

    # GNOME Ubuntu Dock auto-hides whenever ANY window touches its rect,
    # regardless of opacity. Reserving a margin so our overlay doesn't
    # overlap the dock keeps it visible. Tweak via env vars to suit
    # different desktop environments (e.g. KDE panel at bottom).
    margin_left = int(os.environ.get("MEETACLAW_MARGIN_LEFT", "80"))
    margin_top = int(os.environ.get("MEETACLAW_MARGIN_TOP", "32"))
    margin_right = int(os.environ.get("MEETACLAW_MARGIN_RIGHT", "0"))
    margin_bottom = int(os.environ.get("MEETACLAW_MARGIN_BOTTOM", "48"))

    STAGE_W = max(400, screen_w - margin_left - margin_right)
    STAGE_H = max(300, screen_h - margin_top - margin_bottom)

    HOME_POS = (max(80, int(STAGE_W * 0.06)), max(120, int(STAGE_H * 0.18)))
    TRASH_ZONE_POS = (int(STAGE_W * 0.86), HOME_POS[1])
    GATE_X = int(STAGE_W * 0.74)
    GATE_HEIGHT = max(220, int(STAGE_H * 0.30))
    GATE_Y = HOME_POS[1] - int(GATE_HEIGHT * 0.3)
    print(f"[overlay] screen {screen_w}x{screen_h}; reserved L{margin_left}/T{margin_top}/R{margin_right}/B{margin_bottom}")
    print(f"[overlay] stage    {STAGE_W}x{STAGE_H} at ({margin_left},{margin_top}); HOME={HOME_POS} TRASH={TRASH_ZONE_POS} GATE_X={GATE_X}")

    window = make_window(origin_x=margin_left, origin_y=margin_top, width=STAGE_W, height=STAGE_H)

    # Convert per-icon screen positions (from pre-demo.sh) into
    # pyglet-window coordinates so the lobster can walk straight to them.
    icon_positions_screen = load_icon_positions()
    icon_positions_pyglet: dict[str, tuple[float, float]] = {}
    for name, (sx, sy) in icon_positions_screen.items():
        icon_positions_pyglet[name] = screen_to_pyglet(
            sx, sy, margin_left, margin_top, STAGE_H, screen_h,
        )
    if icon_positions_pyglet:
        print(f"[overlay] loaded {len(icon_positions_pyglet)} icon positions; e.g. "
              f"{next(iter(icon_positions_pyglet.items()))}")
    else:
        print("[overlay] no icon positions JSON (run scripts/pre-demo.sh)")
    sprite_img = pyglet.image.load(str(SPRITE_PATH))
    sprite_img.anchor_x = sprite_img.width // 2
    sprite_img.anchor_y = sprite_img.height // 2
    sprite = pyglet.sprite.Sprite(img=sprite_img, x=HOME_POS[0], y=HOME_POS[1])
    sprite.scale = SPRITE_SCALE

    lobster = Lobster(sprite=sprite, base_y=HOME_POS[1])

    gate_state = GateState()
    gate_observer = start_gate_watcher(gate_state)

    # Three threads push into one event queue:
    #   - SandboxMirror: sandbox tidy.sh moves files inside the sandbox;
    #     we mirror to host buckets via shutil.move and emit move/trash
    #     events tied to known icon positions.
    #   - DesktopArrangeBroker: agent's desktop-arrange skill queues
    #     intents inside the sandbox; broker reads them and runs gio set
    #     / gio trash on the host (gate-checked).
    #   - DesktopWatcher: catches resulting ~/Desktop position changes
    #     and removals (from broker actions OR anything else) and emits
    #     rearrange / vanished events for the lobster to animate.
    # claims is shared between the mirror and the desktop watcher so the
    # watcher doesn't fire a second animation when sandbox mirror
    # already accounted for a filename.
    mirror_queue: queue.Queue = queue.Queue()
    claims: dict[str, float] = {}
    mirror_thread = SandboxMirror(_find_sandbox_container, mirror_queue, claims)
    mirror_thread.start()
    arrange_broker = DesktopArrangeBroker(_find_sandbox_container, mirror_queue)
    arrange_broker.start()
    desktop_watcher = DesktopWatcher(mirror_queue, claims)
    desktop_watcher.start()

    # Drop zones in pyglet window-local coords. For sorted buckets, these
    # are the screen-coord positions of the actual folder icons that
    # pre-demo.sh planted on the desktop, converted into pyglet space.
    # For trash, the existing trash zone (with the gate in front).
    DROP_ZONES = {}
    for bucket, (sx, sy) in HOST_FOLDER_SCREEN_POS.items():
        DROP_ZONES[bucket] = screen_to_pyglet(
            sx, sy, margin_left, margin_top, STAGE_H, screen_h,
        )
    DROP_ZONES["trash"] = TRASH_ZONE_POS

    def _screen_to_pg(pos):
        return screen_to_pyglet(pos[0], pos[1], margin_left, margin_top, STAGE_H, screen_h)

    def begin_task_for_event(event: tuple) -> None:
        """Translate a queued event into a lobster pickup task. Handles
        four kinds:
          ('move', bucket, filename)         — sandbox mirror, sort bucket
          ('trash', 'trash', filename)       — sandbox mirror, trashed
          ('rearrange', name, old_xy, new_xy)— agent did gio set; we just animate
          ('vanished', name, old_xy)         — agent removed file; animate to trash zone
        """
        kind = event[0]
        if kind in ("move", "trash"):
            _, bucket, filename = event
            source = icon_positions_pyglet.get(filename)
            if source is None:
                _ = _mirror_file_on_host(filename, bucket)
                mirror_thread.report(f"{filename} → (no icon position; quiet mirror)")
                return
            dest = DROP_ZONES.get(bucket, HOME_POS)
            lobster.pickup_task = PickupTask(
                filename=filename, bucket=bucket,
                source_pos=source, dest_pos=dest, phase="to_source",
                do_host_op=True,
            )
            lobster.walk_to(source)
            mirror_thread.report(f"{filename} → walking to {bucket}")
        elif kind == "rearrange":
            _, filename, old_xy, new_xy = event
            source = _screen_to_pg(old_xy)
            dest = _screen_to_pg(new_xy)
            lobster.pickup_task = PickupTask(
                filename=filename, bucket="rearrange",
                source_pos=source, dest_pos=dest, phase="to_source",
                do_host_op=False,  # agent already moved the icon
            )
            lobster.walk_to(source)
            mirror_thread.report(f"{filename} → rearranged on desktop")
        elif kind == "vanished":
            _, filename, old_xy = event
            source = _screen_to_pg(old_xy)
            lobster.pickup_task = PickupTask(
                filename=filename, bucket="trash",
                source_pos=source, dest_pos=DROP_ZONES["trash"], phase="to_source",
                do_host_op=False,  # already deleted on host
            )
            lobster.walk_to(source)
            mirror_thread.report(f"{filename} → vanished (lobster animates after the fact)")
        elif kind == "denied":
            _, filename = event
            source = icon_positions_pyglet.get(filename)
            if source is None:
                mirror_thread.report(f"{filename} → denied (no icon position; skipping)")
                return
            # Walk to the file → walk toward the trash zone → the
            # closed-gate auto-bounce handler fires when the lobster
            # crosses the gate position with carried_file set. Then the
            # phase=="to_dest" arrival in tick clears the carry and the
            # task — visually: 'tried to trash, gate bounced me back.'
            lobster.pickup_task = PickupTask(
                filename=filename, bucket="trash",
                source_pos=source, dest_pos=DROP_ZONES["trash"], phase="to_source",
                do_host_op=False,  # the file is staying on the desktop
            )
            lobster.walk_to(source)
            mirror_thread.report(f"{filename} → denied (will bounce off gate)")

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

        # Advance any in-flight pickup task. Two cases:
        #   1) lobster just arrived at the source icon → do the real
        #      host mv, switch carry visual on, walk to drop zone.
        #   2) lobster just arrived at the drop zone → clear carry,
        #      task done, lobster is idle and ready for the next event.
        if lobster.state == LobsterState.IDLE and lobster.pickup_task is not None:
            task = lobster.pickup_task
            if task.phase == "to_source":
                if task.do_host_op:
                    status = _mirror_file_on_host(task.filename, task.bucket)
                    mirror_thread.report(f"{task.filename} → {status}")
                lobster.pickup(task.filename)
                task.phase = "to_dest"
                lobster.walk_to(task.dest_pos)
            elif task.phase == "to_dest":
                lobster.drop()
                lobster.pickup_task = None

        # Pull next event from the mirror queue when the lobster is free.
        if lobster.state == LobsterState.IDLE and lobster.pickup_task is None:
            try:
                event = mirror_queue.get_nowait()
                begin_task_for_event(event)
            except queue.Empty:
                pass

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
    # input region is in WINDOW coordinates (not screen). pyglet draws
    # bottom-left-origin, but SHAPE wants top-left-origin, so flip y.
    gate_top_local = STAGE_H - GATE_Y - GATE_HEIGHT
    # Generous padding so the operator can click the bar without missing.
    pad = 30
    make_overlay_native_on_desktop(
        window,
        gate_rect_screen=(
            int(GATE_X) - pad,
            int(gate_top_local) - pad,
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
        arrange_broker.stop()
        arrange_broker.join(timeout=2.0)
        desktop_watcher.stop()
        desktop_watcher.join(timeout=2.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
