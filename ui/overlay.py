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
import sys
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import pyglet
from pyglet import shapes
from pyglet.window import Window, key
from watchdog.events import FileSystemEventHandler
# PollingObserver avoids inotify so we keep working on machines where
# fs.inotify.max_user_watches is already saturated by IDEs / dev tools.
from watchdog.observers.polling import PollingObserver as Observer

HERE = Path(__file__).resolve().parent
SPRITE_PATH = HERE / "assets" / "sprites" / "lobster_72.png"
GATE_STATE_FILE = Path("/tmp/meet_a_claw-gate-state")

SPRITE_SCALE = 2.0
SPRITE_PX = int(72 * SPRITE_SCALE)

STAGE_W = 1400
STAGE_H = 240

WALK_DURATION_S = 1.8
WALK_BOB_HEIGHT = 8
WALK_BOB_FREQ_HZ = 6

BOUNCE_DURATION_S = 0.55
BOUNCE_RECOIL_PX = 80
BOUNCE_WOBBLE_DEG = 18

HOME_POS = (60, 100)
TRASH_ZONE_X = STAGE_W * 0.82
TRASH_ZONE_POS = (TRASH_ZONE_X, 100)
GATE_X = STAGE_W * 0.72  # gate stands between lobster path and trash
GATE_WIDTH = 14
GATE_HEIGHT = 160
GATE_Y = (STAGE_H - GATE_HEIGHT) / 2

GATE_COLOR_CLOSED = (220, 60, 60)
GATE_COLOR_OPEN = (80, 200, 120)


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
    """Thread-safe holder for whether the trash gate is currently open."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._open = self._read_initial()
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
            if new != self._open:
                self._open = new
                self._dirty = True

    def consume_change(self) -> bool | None:
        """Returns the new state if it changed since last consume, else None."""
        with self._lock:
            if self._dirty:
                self._dirty = False
                return self._open
            return None

    @property
    def is_open(self) -> bool:
        with self._lock:
            return self._open


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
    try:
        config = pyglet.gl.Config(alpha_size=8, double_buffer=True)
        window = Window(
            width=STAGE_W,
            height=STAGE_H,
            config=config,
            style=Window.WINDOW_STYLE_BORDERLESS,
            caption="meet_a_claw",
            resizable=False,
        )
    except pyglet.window.NoSuchConfigException:
        window = Window(
            width=STAGE_W,
            height=STAGE_H,
            style=Window.WINDOW_STYLE_BORDERLESS,
            caption="meet_a_claw",
            resizable=False,
        )
    window.set_location(40, 40)
    return window


def main() -> int:
    if not SPRITE_PATH.exists():
        print(f"sprite missing: {SPRITE_PATH}", file=sys.stderr)
        return 1

    window = make_window()
    sprite_img = pyglet.image.load(str(SPRITE_PATH))
    sprite_img.anchor_x = sprite_img.width // 2
    sprite_img.anchor_y = sprite_img.height // 2
    sprite = pyglet.sprite.Sprite(img=sprite_img, x=HOME_POS[0], y=HOME_POS[1])
    sprite.scale = SPRITE_SCALE

    lobster = Lobster(sprite=sprite, base_y=HOME_POS[1])

    gate_state = GateState()
    gate_observer = start_gate_watcher(gate_state)

    # Carried-file visual: a small white "page" icon (rectangle + folded
    # corner accent) sitting above-right of the lobster, plus a text
    # label with the filename. System fonts on this box don't ship color
    # emoji, so we draw the icon ourselves instead of relying on 📄.
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
    # The "page" — a small rectangle. We draw a darker accent triangle
    # in the top-right to suggest a folded corner.
    carry_page = shapes.Rectangle(
        x=0, y=0, width=18, height=22,
        color=(245, 240, 220),
    )
    carry_page_corner = shapes.Triangle(
        0, 0, 0, 0, 0, 0,
        color=(200, 195, 175),
    )
    carry_page_border = shapes.Rectangle(
        x=0, y=0, width=18, height=22,
        color=(120, 100, 60),
    )
    carry_page_border.opacity = 80

    # Default file to pick up on P. In B5 this will come from a real
    # desktop-scan call into the sandbox.
    DEFAULT_PICKUP = "old_disk.iso"

    initial_color = GATE_COLOR_OPEN if gate_state.is_open else GATE_COLOR_CLOSED
    gate_shape = shapes.Rectangle(
        x=GATE_X, y=GATE_Y, width=GATE_WIDTH, height=GATE_HEIGHT,
        color=initial_color,
    )

    pyglet.gl.glClearColor(1.0, 0.97, 0.91, 1.0)
    instr = pyglet.text.Label(
        "SPACE: walk to trash   R: walk home   B: bounce   P: pick up   D: drop   ESC: quit",
        font_name="Sans", font_size=11, color=(80, 60, 40, 200),
        x=12, y=STAGE_H - 18,
    )
    gate_label = pyglet.text.Label(
        "gate: CLOSED", font_name="Sans", font_size=11, color=(80, 60, 40, 200),
        x=GATE_X - 110, y=GATE_Y + GATE_HEIGHT + 8,
    )

    def refresh_gate_label_and_color() -> None:
        if gate_state.is_open:
            gate_shape.color = GATE_COLOR_OPEN
            gate_label.text = "gate: OPEN"
        else:
            gate_shape.color = GATE_COLOR_CLOSED
            gate_label.text = "gate: CLOSED"

    refresh_gate_label_and_color()

    def position_carry():
        # The page icon + label hug the upper-right of the sprite's hitbox
        # so they bob and bounce with the lobster naturally.
        sx, sy = lobster.sprite.x, lobster.sprite.y
        offset_x = 26
        offset_y = SPRITE_PX / 2 + 4
        carry_label.x = sx + offset_x
        carry_label.y = sy + offset_y + 26  # text sits above the page icon
        # Background pill behind label.
        text_w = carry_label.content_width + 14
        text_h = carry_label.content_height + 4
        carry_bg.x = carry_label.x - text_w / 2
        carry_bg.y = carry_label.y - 2
        carry_bg.width = text_w
        carry_bg.height = text_h
        # Page icon sits between the lobster and the label.
        page_x = sx + offset_x - 9   # center the 18-wide page on offset_x
        page_y = sy + offset_y + 2
        carry_page_border.x = page_x - 1
        carry_page_border.y = page_y - 1
        carry_page_border.width = 20
        carry_page_border.height = 24
        carry_page.x = page_x
        carry_page.y = page_y
        # Folded corner: a small triangle in the top-right of the page.
        corner = 6
        carry_page_corner.x1 = page_x + 18 - corner
        carry_page_corner.y1 = page_y + 22
        carry_page_corner.x2 = page_x + 18
        carry_page_corner.y2 = page_y + 22
        carry_page_corner.x3 = page_x + 18
        carry_page_corner.y3 = page_y + 22 - corner

    @window.event
    def on_draw():
        window.clear()
        gate_shape.draw()
        gate_label.draw()
        lobster.sprite.draw()
        if lobster.carried_file is not None:
            position_carry()
            carry_page_border.draw()
            carry_page.draw()
            carry_page_corner.draw()
            carry_bg.draw()
            carry_label.draw()
        instr.draw()

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
            if lobster.carried_file is None:
                lobster.pickup(DEFAULT_PICKUP)
                carry_label.text = DEFAULT_PICKUP
        elif symbol == key.D:
            lobster.drop()

    def tick(dt: float):
        new_state = gate_state.consume_change()
        if new_state is not None:
            refresh_gate_label_and_color()
        lobster.update(dt, gate_open=gate_state.is_open)

    pyglet.clock.schedule_interval(tick, 1 / 60)
    print("meet_a_claw overlay — B3 walk + B6 gate watcher.")
    print(f"  watching: {GATE_STATE_FILE}")
    print("  SPACE/R/B/ESC, or grant-trash.sh / revoke-trash.sh to toggle gate.")
    try:
        pyglet.app.run()
    finally:
        gate_observer.stop()
        gate_observer.join(timeout=2.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
