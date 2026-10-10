#!/usr/bin/env python3
"""Build a STUdio story pack (.zip) from a folder of songs or stories.

The resulting archive can be dragged into Lunii.QT (https://github.com/o-daneel/Lunii.QT)
to install it on a Lunii.

Pack layout on the device:
    cover ("Mes comptines")  --OK-->  menu: turn the wheel to pick a track  --OK-->  track plays
    At the end of a track (or on HOME) the child is brought back to the menu, on that same track.

Usage:
    python3 build_studio_pack.py MY_FOLDER --title "Mes comptines"

Optional files in MY_FOLDER:
    _titre.mp3           audio announcing the pack name (played on the cover)
    _cover.png           image for the cover (otherwise one is generated with the title)
    <track>.titre.mp3    audio announcing a track in the menu (e.g. "Le petit bonhomme.titre.mp3")
    <track>.png          image for a track in the menu (otherwise one is generated with its name)

Without a title audio, the first seconds of the track are used as its menu preview
(this needs ffmpeg; otherwise the menu entry is silent).

Requirements: Python 3.8+, Pillow (pip install pillow), ffmpeg recommended.
"""

import argparse
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

AUDIO_EXTS = {".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".wav", ".flac", ".wma"}
SCREEN_SIZE = (320, 240)
PREVIEW_SECONDS = 6
# Fixed namespace so that rebuilding a pack with the same title keeps the same UUID
# (Lunii.QT then reports it as already loaded instead of installing a duplicate).
PACK_NAMESPACE = uuid.UUID("6f1c3a52-7d1e-4c55-9a3e-5b1a2f0c8d11")


def natural_key(path):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", path.stem)]


def display_name(path):
    # "01 - Le petit bonhomme" -> "Le petit bonhomme"
    return re.sub(r"^\d+\s*[-_.]?\s*", "", path.stem).strip() or path.stem


def asset_name(data, ext):
    # Lunii.QT keeps only the last 8 characters of each asset name, so they must be unique there.
    return hashlib.sha1(data).hexdigest()[:8] + ext


def load_font(size):
    for name in ("DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf", "Arial.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def wrap(draw, text, font, max_width):
    lines, line = [], ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width or not line:
            line = candidate
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def text_image(text):
    img = Image.new("RGB", SCREEN_SIZE, "black")
    draw = ImageDraw.Draw(img)
    for size in (40, 34, 28, 22, 18):
        font = load_font(size)
        lines = wrap(draw, text, font, SCREEN_SIZE[0] - 24)
        line_h = size + 6
        if len(lines) * line_h <= SCREEN_SIZE[1] - 24:
            break
    y = (SCREEN_SIZE[1] - len(lines) * line_h) // 2
    for line in lines:
        x = (SCREEN_SIZE[0] - draw.textlength(line, font=font)) // 2
        draw.text((x, y), line, font=font, fill="white")
        y += line_h
    return img


def png_bytes(img):
    img = img.convert("RGB")
    if img.size != SCREEN_SIZE:
        img.thumbnail(SCREEN_SIZE)
        canvas = Image.new("RGB", SCREEN_SIZE, "black")
        canvas.paste(img, ((SCREEN_SIZE[0] - img.width) // 2, (SCREEN_SIZE[1] - img.height) // 2))
        img = canvas
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def audio_preview(path):
    """First seconds of a track, faded out, as MP3 bytes (None if ffmpeg is unavailable)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "preview.mp3"
        cmd = [ffmpeg, "-v", "error", "-y", "-i", str(path), "-t", str(PREVIEW_SECONDS),
               "-af", f"afade=t=out:st={PREVIEW_SECONDS - 1.5}:d=1.5",
               "-map_metadata", "-1", "-vn", "-ac", "1", "-ar", "44100", "-b:a", "64k", str(out)]
        if subprocess.run(cmd).returncode != 0 or not out.exists():
            return None
        return out.read_bytes()


def control(wheel, ok, home, pause, autoplay):
    return {"wheel": wheel, "ok": ok, "home": home, "pause": pause, "autoplay": autoplay}


def build(folder, title, output):
    tracks = sorted(
        (p for p in folder.iterdir()
         if p.is_file() and p.suffix.lower() in AUDIO_EXTS
         and not p.name.startswith("_") and not p.stem.lower().endswith(".titre")),
        key=natural_key)
    if not tracks:
        sys.exit(f"No audio files found in {folder}")

    assets = {}  # asset name -> bytes

    def add_asset(data, ext):
        name = asset_name(data, ext)
        assets[name] = data
        return name

    def optional(path):
        return path.read_bytes() if path.is_file() else None

    if not shutil.which("ffmpeg"):
        print("ffmpeg not found: menu entries without a '.titre.mp3' file will be silent.")

    pack_uuid = uuid.uuid5(PACK_NAMESPACE, title)
    menu_id = str(uuid.uuid5(pack_uuid, "menu"))

    cover_img = optional(folder / "_cover.png")
    cover_img = png_bytes(Image.open(io.BytesIO(cover_img))) if cover_img else png_bytes(text_image(title))
    cover_audio = optional(folder / "_titre.mp3") or audio_preview(tracks[0])

    stage_nodes = [{
        "uuid": str(pack_uuid),
        "type": "cover",
        "name": title,
        "squareOne": True,
        "position": {"x": 0, "y": 0},
        "image": add_asset(cover_img, ".png"),
        "audio": add_asset(cover_audio, ".mp3") if cover_audio else None,
        "okTransition": {"actionNode": menu_id, "optionIndex": 0},
        "homeTransition": None,
        "controlSettings": control(True, True, False, False, False),
    }]
    action_nodes = [{"id": menu_id, "name": "Menu", "position": {"x": 300, "y": 0}, "options": []}]

    for index, track in enumerate(tracks):
        name = display_name(track)
        menu_node_id = str(uuid.uuid5(pack_uuid, f"menu-{index}-{track.name}"))
        play_node_id = str(uuid.uuid5(pack_uuid, f"play-{index}-{track.name}"))
        play_action_id = str(uuid.uuid5(pack_uuid, f"action-{index}-{track.name}"))

        img = optional(track.with_suffix(".png"))
        img = png_bytes(Image.open(io.BytesIO(img))) if img else png_bytes(text_image(name))
        title_audio = optional(track.with_name(track.stem + ".titre.mp3")) or audio_preview(track)
        back_to_menu = {"actionNode": menu_id, "optionIndex": index}

        stage_nodes.append({
            "uuid": menu_node_id,
            "type": "stage",
            "name": name,
            "position": {"x": 600, "y": index * 150},
            "image": add_asset(img, ".png"),
            "audio": add_asset(title_audio, ".mp3") if title_audio else None,
            "okTransition": {"actionNode": play_action_id, "optionIndex": 0},
            "homeTransition": None,
            "controlSettings": control(True, True, True, False, False),
        })
        stage_nodes.append({
            "uuid": play_node_id,
            "type": "stage",
            "name": f"{name} (lecture)",
            "position": {"x": 1200, "y": index * 150},
            "image": None,
            "audio": add_asset(track.read_bytes(), track.suffix.lower()),
            "okTransition": back_to_menu,
            "homeTransition": back_to_menu,
            "controlSettings": control(False, False, True, True, True),
        })
        action_nodes[0]["options"].append(menu_node_id)
        action_nodes.append({"id": play_action_id, "name": name, "position": {"x": 900, "y": index * 150},
                             "options": [play_node_id]})

    story = {
        "format": "v1",
        "title": title,
        "version": 1,
        "description": f"{len(tracks)} pistes : " + ", ".join(display_name(t) for t in tracks),
        "nightModeAvailable": False,
        "stageNodes": stage_nodes,
        "actionNodes": action_nodes,
    }

    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("story.json", json.dumps(story, ensure_ascii=False, indent=2))
        zf.writestr("thumbnail.png", cover_img)
        for name, data in assets.items():
            zf.writestr(f"assets/{name}", data)

    print(f"Created {output} ({len(tracks)} tracks). Drag it into Lunii.QT to install it.")


def main():
    parser = argparse.ArgumentParser(description="Build a STUdio pack for Lunii.QT from a folder of audio files.")
    parser.add_argument("folder", type=Path, help="folder containing the songs/stories (MP3 recommended)")
    parser.add_argument("--title", default=None, help="pack name shown on the Lunii (default: folder name)")
    parser.add_argument("-o", "--output", type=Path, default=None, help="output .zip (default: '<title>.zip')")
    args = parser.parse_args()

    folder = args.folder.expanduser().resolve()
    if not folder.is_dir():
        sys.exit(f"{folder} is not a folder")
    title = args.title or folder.name
    output = args.output or Path(f"{title}.zip")
    build(folder, title, output)


if __name__ == "__main__":
    main()
