"""
meet_a_claw overlay — B3 walk animation.

State machine:
    IDLE       — sprite static at current position
    WALKING    — interpolating from (x0,y0) → target over `walk_duration`
                 seconds, with a small vertical "bob" so it looks like
                 footsteps. Snaps back to IDLE when arrived.

Controls (for solo testing before B5 WebSocket wiring lands):
    SPACE      — walk to the demo trash zone (right of screen)
    R          — walk back to home (top-left)
    ESC        — quit

Run:
    cd /media/ufoai/DATAs3/fromtrx51/workspace/meet_a_claw/ui
    .venv/bin/python overlay.py
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import pyglet
from pyglet.window import Window, key

HERE = Path(__file__).resolve().parent
SPRITE_PATH = HERE / "assets" / "sprites" / "lobster_72.png"
SPRITE_SCALE = 2.0
SPRITE_PX = int(72 * SPRITE_SCALE)

# The overlay window has to be big enough to cover the lobster's entire
# trajectory because we draw inside a single window (pyglet doesn't have a
# native "draw on the actual desktop" surface). We size it to most of the
# screen and let the empty cream area double as a stage. B7 will replace
# the cream fill with transparency so the desktop wallpaper shows through.
STAGE_W = 1400
STAGE_H = 240
WALK_DURATION_S = 1.8    # seconds end-to-end
WALK_BOB_HEIGHT = 8      # vertical pixels of bobbing during walk
WALK_BOB_FREQ_HZ = 6     # steps per second visual rate

HOME_POS = (60, 80)      # top-left start
TRASH_ZONE_X = STAGE_W * 0.78  # roughly where a "trash can" would sit
TRASH_ZONE_POS = (TRASH_ZONE_X, 80)


class LobsterState(Enum):
    IDLE = "idle"
    WALKING = "walking"


@dataclass
class Lobster:
    sprite: pyglet.sprite.Sprite
    state: LobsterState = LobsterState.IDLE
    walk_origin: tuple[float, float] = (0.0, 0.0)
    walk_target: tuple[float, float] = (0.0, 0.0)
    walk_elapsed: float = 0.0
    walk_duration: float = WALK_DURATION_S
    base_y: float = 0.0  # y while idle (no bob)

    def walk_to(self, target: tuple[float, float]) -> None:
        if self.state == LobsterState.WALKING:
            # Re-target from current position so a mid-walk keypress
            # produces a smooth course-correct rather than a teleport.
            self.walk_origin = (self.sprite.x, self.base_y)
        else:
            self.walk_origin = (self.sprite.x, self.sprite.y)
        self.walk_target = target
        self.walk_elapsed = 0.0
        self.state = LobsterState.WALKING
        self.base_y = self.walk_origin[1]

    def update(self, dt: float) -> None:
        if self.state != LobsterState.WALKING:
            return
        self.walk_elapsed += dt
        t = min(1.0, self.walk_elapsed / self.walk_duration)
        # Ease-in-out so the lobster starts and stops gently.
        eased = 0.5 - 0.5 * math.cos(math.pi * t)
        x = self.walk_origin[0] + (self.walk_target[0] - self.walk_origin[0]) * eased
        y = self.walk_origin[1] + (self.walk_target[1] - self.walk_origin[1]) * eased
        # Footstep bob: a sinusoid that only kicks in mid-walk so the
        # arrival is steady (no jitter on the last frame).
        in_motion = 1.0 if 0.05 < t < 0.95 else 0.0
        bob = math.sin(self.walk_elapsed * WALK_BOB_FREQ_HZ * 2 * math.pi) * WALK_BOB_HEIGHT * in_motion
        self.sprite.x = x
        self.sprite.y = y + bob
        self.base_y = y
        # Face the direction of travel.
        dx = self.walk_target[0] - self.walk_origin[0]
        if dx > 0:
            self.sprite.scale_x = abs(self.sprite.scale_x)
        elif dx < 0:
            self.sprite.scale_x = -abs(self.sprite.scale_x)
        if t >= 1.0:
            self.state = LobsterState.IDLE
            self.sprite.y = self.walk_target[1]


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
    # Anchor top-left of screen with a tiny gap.
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

    pyglet.gl.glClearColor(1.0, 0.97, 0.91, 1.0)
    instr = pyglet.text.Label(
        "SPACE: walk to trash zone   R: walk home   ESC: quit",
        font_name="Sans",
        font_size=11,
        color=(80, 60, 40, 200),
        x=12,
        y=STAGE_H - 18,
    )

    @window.event
    def on_draw():
        window.clear()
        lobster.sprite.draw()
        instr.draw()

    @window.event
    def on_key_press(symbol, modifiers):
        if symbol == key.ESCAPE:
            pyglet.app.exit()
        elif symbol == key.SPACE:
            lobster.walk_to(TRASH_ZONE_POS)
        elif symbol == key.R:
            lobster.walk_to(HOME_POS)

    def tick(dt: float):
        lobster.update(dt)

    pyglet.clock.schedule_interval(tick, 1 / 60)
    print("meet_a_claw overlay — B3 walk animation. SPACE/R/ESC.")
    pyglet.app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
