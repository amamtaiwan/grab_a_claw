#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""
generate_sft_data.py — generate ~5000 SFT samples for Nemotron desktop-arrange.

Coverage:
  1. Simple single-intent moves    (file × zone × phrasings)
  2. Trash single                  (file × phrasings)
  3. Meta-arrange                  (sort/column/filter/pitch/start)
  4. Compositional MULTI-LINE:
     - "trash all files starting with t"
     - "delete every .log file"
     - "move .pdf to upper-right, .png to bottom-left"
     - "swap A.x and B.y"
     - "align all files in a circle"
     - "tile all files in a 3x3 grid in upper-left"
     - "move a.png next to b.png" (relative positioning)
     - "stack all logs vertically in bottom-right"

When the user asks for compositional behaviour the assistant emits N separate
JSON intent lines (newline-separated), one per file. Each line is a valid
canonical intent — the host broker reads each line independently.

Output:
  train/data/train.chatml.jsonl + eval.chatml.jsonl
"""

from __future__ import annotations
import argparse
import json
import math
import random
import string
from pathlib import Path

# ---------- demo desktop fixture (mirrors pre-demo.sh) -------------
DEMO_FILES = [
    "draft.pdf",
    "empty_file.txt",
    "old_disk.iso",
    "random.log",
    "screenshot_2026-05-20.png",
    "tax_receipts_2024.zip",
    "temp_notes.tmp",
]

# Extra synthetic filenames the generator can mix in for breadth.
EXTRA_FILES_POOL = [
    "alpha.png", "beta.png", "gamma.png", "delta.jpg",
    "report.pdf", "budget.pdf", "thesis.pdf",
    "session.log", "trace.log", "build.log",
    "archive.zip", "backup.tar", "data.csv",
    "notes.md", "todo.txt", "ideas.txt",
    "demo.mp4", "track.mp3",
    "tmp_file.tmp", "scratch.tmp", "test.tmp",
]

# Zone centers (must match overlay's DesktopArrangeBroker.ZONE_CENTERS).
ZONES = {
    "upper-left":   (520, 310),
    "upper-right":  (1440, 310),
    "bottom-left":  (520, 770),
    "bottom-right": (1440, 770),
    "center":       (960, 520),
}
ZONE_PHRASES = {
    "upper-left":   ["upper-left", "top-left", "upper left", "top left", "left top corner"],
    "upper-right":  ["upper-right", "top-right", "upper right", "top right", "right top corner"],
    "bottom-left":  ["bottom-left", "lower-left", "bottom left", "lower left", "left bottom"],
    "bottom-right": ["bottom-right", "lower-right", "bottom right", "lower right", "right bottom"],
    "center":       ["the center", "the middle", "centre", "the screen center", "middle of the desktop"],
}

MOVE_VERBS = ["move", "place", "put", "drag", "shift", "send", "arrange", "drop"]
TRASH_VERBS = ["trash", "delete", "remove", "throw out", "discard", "send to the bin", "get rid of"]

SKILL_SYSTEM = (
    "You are the desktop-arrange skill running inside an OpenClaw sandbox. "
    "Your job: read the user's request and emit a sequence of JSON intent lines (one JSON "
    "object per line) that the host-side overlay broker will execute. The canonical schema:\n"
    '  {"action":"set_position","file":"<name>","x":<int>,"y":<int>}\n'
    '  {"action":"trash","file":"<name>"}\n'
    '  {"action":"arrange","sort":"A-Z|Z-A","column":"<zone>","filter":"<optional ext>",'
    '"rowPitch":<int>,"startY":<int>}\n'
    "When the request needs touching multiple files, emit one canonical intent line PER file, "
    "newline-separated. DO NOT invent other keys (no 'intent'/'target'/'position' strings). "
    "DO NOT use awk/printf/shell templates inside JSON. Output JSON objects only — no prose."
)

# ---------- helpers --------------------------------------------------

def jsonl(obj: dict) -> str:
    return json.dumps(obj, separators=(",", ":"))


def render_move_pair(rng):
    file = rng.choice(DEMO_FILES + EXTRA_FILES_POOL)
    zone_name = rng.choice(list(ZONES.keys()))
    x, y = ZONES[zone_name]
    zphrase = rng.choice(ZONE_PHRASES[zone_name])
    verb = rng.choice(MOVE_VERBS)
    user_template = rng.choice([
        "{verb} {file} to {zone}",
        "{verb} {file} to the {zone}",
        "{verb} {file} into the {zone} area",
        "please {verb} {file} to {zone}",
        "Use desktop-arrange to {verb} {file} to {zone}",
        "{file} should go to {zone}",
        "I want {file} in the {zone}",
        "could you {verb} {file} to {zone}?",
        "drop {file} at {zone}",
        "{zone}, please put {file} there",
    ])
    user = user_template.format(verb=verb, file=file, zone=zphrase)
    assistant = jsonl({"action": "set_position", "file": file, "x": x, "y": y})
    return {"user": user, "assistant": assistant}


def render_trash_single(rng):
    file = rng.choice(DEMO_FILES + EXTRA_FILES_POOL)
    verb = rng.choice(TRASH_VERBS)
    user_template = rng.choice([
        "{verb} {file}",
        "{verb} the {file}",
        "please {verb} {file}",
        "I don't need {file}, {verb} it",
        "{file} can go",
        "Use desktop-arrange to {verb} {file}",
        "kill {file}",
        "{verb} {file} from the desktop",
    ])
    user = user_template.format(verb=verb, file=file)
    assistant = jsonl({"action": "trash", "file": file})
    return {"user": user, "assistant": assistant}


def render_meta_arrange(rng):
    zone_name = rng.choice(list(ZONES.keys()))
    zphrase = rng.choice(ZONE_PHRASES[zone_name])
    sort = rng.choice(["A-Z", "Z-A"])
    sort_phrase = {"A-Z": rng.choice(["A-Z", "alphabetically", "in alphabetical order"]),
                   "Z-A": rng.choice(["Z-A", "in reverse alphabetical order", "from Z to A"])}[sort]
    use_filter = rng.random() < 0.4
    intent = {
        "action": "arrange",
        "sort": sort,
        "column": zone_name,
        "rowPitch": 130,
        "startY": 180 if "upper" in zone_name else 540,
    }
    if use_filter:
        ext = rng.choice(["png", "pdf", "log", "zip", "txt", "tmp", "iso"])
        intent["filter"] = ext
        user_template = rng.choice([
            "arrange all {ext} files {sort_phrase} in {zone}",
            "sort the {ext}s {sort_phrase} in {zone}",
            "line up the {ext} files in {zone}, {sort_phrase}",
            "tidy {ext}s into a column at {zone}",
        ])
        user = user_template.format(ext=ext, sort_phrase=sort_phrase, zone=zphrase)
    else:
        user_template = rng.choice([
            "arrange all files {sort_phrase} in {zone}",
            "sort everything {sort_phrase} in {zone}",
            "stack all icons in {zone}, {sort_phrase}",
            "tidy the desktop into a column at {zone}",
        ])
        user = user_template.format(sort_phrase=sort_phrase, zone=zphrase)
    assistant = jsonl(intent)
    return {"user": user, "assistant": assistant}


# -------- compositional / hard examples ---------

def render_prefix_trash(rng):
    """trash all files starting with X -> N trash lines."""
    files_pool = DEMO_FILES + rng.sample(EXTRA_FILES_POOL, k=rng.randint(0, 8))
    prefixes = sorted({f[0].lower() for f in files_pool})
    prefix = rng.choice(prefixes)
    matching = [f for f in files_pool if f.lower().startswith(prefix)]
    if not matching:
        return None
    verb = rng.choice(TRASH_VERBS)
    user_template = rng.choice([
        "{verb} all files starting with {p}",
        "{verb} every file that begins with {p}",
        "{verb} anything whose name starts with {p}",
        "throw out all files starting with '{p}'",
        "I want every file starting with {p} gone",
    ])
    user = user_template.format(verb=verb, p=prefix)
    assistant = "\n".join(jsonl({"action": "trash", "file": f}) for f in matching)
    return {"user": user, "assistant": assistant}


def render_extension_trash(rng):
    """delete every .log file -> N trash lines."""
    files_pool = DEMO_FILES + rng.sample(EXTRA_FILES_POOL, k=rng.randint(0, 6))
    exts = sorted({f.rsplit(".", 1)[-1] for f in files_pool if "." in f})
    ext = rng.choice(exts)
    matching = [f for f in files_pool if f.endswith("." + ext)]
    if not matching:
        return None
    verb = rng.choice(TRASH_VERBS)
    user_template = rng.choice([
        "{verb} every .{ext} file",
        "{verb} all {ext} files",
        "{verb} the {ext}s",
        "drop all .{ext} into the trash",
        "{verb} every file with extension .{ext}",
    ])
    user = user_template.format(verb=verb, ext=ext)
    assistant = "\n".join(jsonl({"action": "trash", "file": f}) for f in matching)
    return {"user": user, "assistant": assistant}


def render_extension_routing(rng):
    """move .pdf to upper-right, .png to bottom-left -> multiple set_position lines."""
    routes = []  # list of (ext, zone_name)
    avail_zones = list(ZONES.keys())
    rng.shuffle(avail_zones)
    files_pool = DEMO_FILES + rng.sample(EXTRA_FILES_POOL, k=rng.randint(0, 6))
    exts_seen = sorted({f.rsplit(".", 1)[-1] for f in files_pool if "." in f})
    chosen_exts = rng.sample(exts_seen, k=min(rng.randint(2, 3), len(exts_seen)))
    for i, ext in enumerate(chosen_exts):
        routes.append((ext, avail_zones[i % len(avail_zones)]))
    parts = [f"{rng.choice(MOVE_VERBS)} all .{e} to {rng.choice(ZONE_PHRASES[z])}" for e, z in routes]
    user = ", and ".join(parts)
    lines = []
    for ext, zone in routes:
        matched = [f for f in files_pool if f.endswith("." + ext)]
        for f in matched:
            x, y = ZONES[zone]
            lines.append(jsonl({"action": "set_position", "file": f, "x": x, "y": y}))
    if not lines:
        return None
    return {"user": user, "assistant": "\n".join(lines)}


def render_circle_layout(rng):
    """align all files in a circle around the center."""
    files_pool = rng.sample(DEMO_FILES + EXTRA_FILES_POOL,
                            k=rng.randint(4, 8))
    cx, cy = 960, 520
    radius = rng.choice([240, 280, 320, 360, 400])
    n = len(files_pool)
    lines = []
    for i, f in enumerate(files_pool):
        theta = 2 * math.pi * i / n - math.pi / 2  # start at top
        x = int(cx + radius * math.cos(theta))
        y = int(cy + radius * math.sin(theta))
        lines.append(jsonl({"action": "set_position", "file": f, "x": x, "y": y}))
    user_template = rng.choice([
        "align all files in a circle",
        "arrange the files in a circle layout",
        "put everything on a circular ring",
        "give me a circle of icons",
        "lay them out in a circle around the center",
        "help me align all files to a circle",
        "make a clock face of files in the middle",
    ])
    return {"user": user_template, "assistant": "\n".join(lines)}


def render_grid_layout(rng):
    """tile all files in an NxN grid in a given zone."""
    files_pool = rng.sample(DEMO_FILES + EXTRA_FILES_POOL,
                            k=rng.randint(4, 9))
    zone_name = rng.choice(list(ZONES.keys()))
    zphrase = rng.choice(ZONE_PHRASES[zone_name])
    cx, cy = ZONES[zone_name]
    cols = int(math.ceil(math.sqrt(len(files_pool))))
    pitch_x, pitch_y = 200, 130
    lines = []
    for i, f in enumerate(files_pool):
        col = i % cols
        row = i // cols
        x = cx - (cols // 2) * pitch_x + col * pitch_x
        y = cy - (cols // 2) * pitch_y + row * pitch_y
        lines.append(jsonl({"action": "set_position", "file": f, "x": x, "y": y}))
    user_template = rng.choice([
        "tile all files in a grid in {zone}",
        "make a grid of icons at {zone}",
        "lay everything out as a grid in the {zone}",
        "arrange files in rows and columns at {zone}",
    ])
    return {"user": user_template.format(zone=zphrase), "assistant": "\n".join(lines)}


def render_relative_position(rng):
    """move A on top of B / next to B."""
    a, b = rng.sample(DEMO_FILES + EXTRA_FILES_POOL, 2)
    # Place B at a known coord, A relative to it. For training we just
    # pick a target zone and place A there as if it were "on top of" B.
    zone_name = rng.choice(list(ZONES.keys()))
    bx, by = ZONES[zone_name]
    rel = rng.choice(["on top of", "right next to", "above", "below", "beside"])
    if rel == "above":
        ax, ay = bx, by - 130
    elif rel == "below":
        ax, ay = bx, by + 130
    elif rel == "right next to":
        ax, ay = bx + 200, by
    elif rel == "beside":
        ax, ay = bx + 200, by
    else:  # "on top of"
        ax, ay = bx, by
    user_template = rng.choice([
        "move {a} {rel} {b}",
        "place {a} {rel} {b}",
        "put {a} {rel} {b}",
        "{a} should go {rel} {b}",
    ])
    # Both end up at the resolved coords (canonical schema only knows
    # absolute x,y — the LM must learn the spatial mapping).
    lines = [
        jsonl({"action": "set_position", "file": b, "x": bx, "y": by}),
        jsonl({"action": "set_position", "file": a, "x": ax, "y": ay}),
    ]
    return {"user": user_template.format(a=a, b=b, rel=rel),
            "assistant": "\n".join(lines)}


def render_multi_move(rng):
    """move A to upper-right, B to bottom-left."""
    n = rng.randint(2, 4)
    files = rng.sample(DEMO_FILES + EXTRA_FILES_POOL, n)
    zone_picks = [rng.choice(list(ZONES.keys())) for _ in range(n)]
    parts = []
    lines = []
    for f, z in zip(files, zone_picks):
        x, y = ZONES[z]
        parts.append(f"{rng.choice(MOVE_VERBS)} {f} to {rng.choice(ZONE_PHRASES[z])}")
        lines.append(jsonl({"action": "set_position", "file": f, "x": x, "y": y}))
    user = ", and ".join(parts)
    return {"user": user, "assistant": "\n".join(lines)}


def render_stack_vertical(rng):
    """stack all logs vertically in bottom-right."""
    files_pool = DEMO_FILES + rng.sample(EXTRA_FILES_POOL, k=rng.randint(0, 6))
    exts = sorted({f.rsplit(".", 1)[-1] for f in files_pool if "." in f})
    ext = rng.choice(exts)
    matching = sorted(f for f in files_pool if f.endswith("." + ext))
    if not matching:
        return None
    zone_name = rng.choice(list(ZONES.keys()))
    cx, cy = ZONES[zone_name]
    pitch = 130
    lines = []
    for i, f in enumerate(matching):
        y = cy - (len(matching) // 2) * pitch + i * pitch
        lines.append(jsonl({"action": "set_position", "file": f, "x": cx, "y": y}))
    verb = rng.choice(["stack", "line up", "arrange vertically", "pile"])
    user = f"{verb} all {ext}s in {rng.choice(ZONE_PHRASES[zone_name])}"
    return {"user": user, "assistant": "\n".join(lines)}


def render_swap(rng):
    """swap A and B positions (need to know both prior positions)."""
    a, b = rng.sample(DEMO_FILES + EXTRA_FILES_POOL, 2)
    # We don't know exact prior positions during inference, but training
    # data uses the planted (700, 180) starting row as default. For
    # generality, pick two zones and emit set_positions that swap.
    z1, z2 = rng.sample(list(ZONES.keys()), 2)
    ax, ay = ZONES[z2]  # A goes to B's zone
    bx, by = ZONES[z1]  # B goes to A's zone
    user = rng.choice([
        f"swap {a} and {b}",
        f"exchange positions of {a} and {b}",
        f"flip {a} with {b}",
    ])
    lines = [
        jsonl({"action": "set_position", "file": a, "x": ax, "y": ay}),
        jsonl({"action": "set_position", "file": b, "x": bx, "y": by}),
    ]
    return {"user": user, "assistant": "\n".join(lines)}


# ---------- build dataset --------------------------------------------

GENERATORS = [
    (render_move_pair,         2.0),   # simple, lots
    (render_trash_single,      1.0),
    (render_meta_arrange,      0.7),
    (render_prefix_trash,      0.7),
    (render_extension_trash,   0.7),
    (render_extension_routing, 0.6),
    (render_circle_layout,     0.6),
    (render_grid_layout,       0.5),
    (render_relative_position, 0.5),
    (render_multi_move,        0.8),
    (render_stack_vertical,    0.4),
    (render_swap,              0.4),
]


def build_dataset(target_n: int, seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    weights = [w for _, w in GENERATORS]
    fns = [f for f, _ in GENERATORS]
    samples = []
    seen = set()
    attempts = 0
    while len(samples) < target_n and attempts < target_n * 4:
        fn = rng.choices(fns, weights=weights, k=1)[0]
        out = fn(rng)
        if out is None:
            attempts += 1
            continue
        key = (out["user"], out["assistant"])
        if key in seen:
            attempts += 1
            continue
        seen.add(key)
        samples.append(out)
        attempts += 1
    rng.shuffle(samples)
    return samples


def as_chatml(sample: dict) -> dict:
    return {
        "messages": [
            {"role": "system", "content": SKILL_SYSTEM},
            {"role": "user", "content": sample["user"]},
            {"role": "assistant", "content": sample["assistant"]},
        ]
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="train/data")
    ap.add_argument("--target-n", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--eval-frac", type=float, default=0.1)
    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    samples = build_dataset(args.target_n, args.seed)
    split = int(len(samples) * (1 - args.eval_frac))
    train, evalset = samples[:split], samples[split:]
    train_path = out_dir / "train.chatml.jsonl"
    eval_path = out_dir / "eval.chatml.jsonl"
    with train_path.open("w") as f:
        for row in train:
            f.write(json.dumps(as_chatml(row), ensure_ascii=False) + "\n")
    with eval_path.open("w") as f:
        for row in evalset:
            f.write(json.dumps(as_chatml(row), ensure_ascii=False) + "\n")
    # Stats
    from collections import Counter
    counts = Counter()
    for s in train + evalset:
        n_lines = s["assistant"].count("\n") + 1
        counts[n_lines] += 1
    print(f"train: {len(train)}  eval: {len(evalset)}")
    print(f"assistant lines per sample (count): {dict(sorted(counts.items()))}")
    print()
    print("3 examples:")
    for s in train[:3]:
        print("---")
        print("USER:     ", s["user"])
        print("ASSISTANT:", s["assistant"][:300])


if __name__ == "__main__":
    main()
