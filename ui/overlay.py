"""
meet_a_claw overlay — first version.

Renders the lobster mascot in a borderless window, positioned at top-left of
the primary screen. Press ESC to quit. Later versions will add transparency,
always-on-top, walking animation, and WebSocket / OCSF-log event consumers.

Run:
    cd /media/ufoai/DATAs3/fromtrx51/workspace/meet_a_claw/ui
    .venv/bin/python overlay.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pyglet
from pyglet.window import Window, key

HERE = Path(__file__).resolve().parent
SPRITE_PATH = HERE / "assets" / "sprites" / "lobster_72.png"
SPRITE_SCALE = 2.0  # 72px sprite × 2 = 144px on screen
WINDOW_SIZE = int(72 * SPRITE_SCALE) + 16  # small padding
MARGIN = 40  # distance from screen edge


def make_window() -> Window:
    # Try to get an alpha-capable GL config so future transparency works;
    # if the driver refuses, fall back to default.
    try:
        config = pyglet.gl.Config(alpha_size=8, double_buffer=True)
        window = Window(
            width=WINDOW_SIZE,
            height=WINDOW_SIZE,
            config=config,
            style=Window.WINDOW_STYLE_BORDERLESS,
            caption="meet_a_claw",
            resizable=False,
        )
    except pyglet.window.NoSuchConfigException:
        window = Window(
            width=WINDOW_SIZE,
            height=WINDOW_SIZE,
            style=Window.WINDOW_STYLE_BORDERLESS,
            caption="meet_a_claw",
            resizable=False,
        )

    # Place near the top-left of the primary screen, with a margin
    display = pyglet.display.get_display()
    screen = display.get_default_screen()
    window.set_location(MARGIN, MARGIN)
    return window


def main() -> int:
    if not SPRITE_PATH.exists():
        print(f"sprite missing: {SPRITE_PATH}", file=sys.stderr)
        return 1

    window = make_window()
    sprite_img = pyglet.image.load(str(SPRITE_PATH))
    sprite_img.anchor_x = sprite_img.width // 2
    sprite_img.anchor_y = sprite_img.height // 2
    lobster = pyglet.sprite.Sprite(
        img=sprite_img,
        x=WINDOW_SIZE / 2,
        y=WINDOW_SIZE / 2,
    )
    lobster.scale = SPRITE_SCALE

    # Visible-background fill (light cream) so we can see the window edges
    # while iterating. Will be replaced by transparent clear color once
    # always-on-top + compositor transparency is wired in B3.
    pyglet.gl.glClearColor(1.0, 0.97, 0.91, 1.0)

    @window.event
    def on_draw():
        window.clear()
        lobster.draw()

    @window.event
    def on_key_press(symbol, modifiers):
        if symbol == key.ESCAPE:
            pyglet.app.exit()

    print(f"meet_a_claw overlay running — sprite at {SPRITE_PATH.name}, ESC to quit")
    pyglet.app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
