#!/usr/bin/env python3
"""Music-box renditions of traditional (public domain) children's tunes, as MP3 files.

Usage: python3 music_box.py OUTPUT_FOLDER     (needs numpy and ffmpeg)

Melodies are written as "NOTE:BEATS" tokens (NOTE like C4, F#4, Bb3; BEATS defaults to 1).
"""

import re
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

SR = 44100

# title -> (beats per minute, melody, round_entries)
# round_entries: number of extra voices entering every 8 beats after the solo (0 = no round)
SONGS = {
    "Frère Jacques": (104, """
        C4 D4 E4 C4 C4 D4 E4 C4 E4 F4 G4:2 E4 F4 G4:2
        G4:.5 A4:.5 G4:.5 F4:.5 E4 C4 G4:.5 A4:.5 G4:.5 F4:.5 E4 C4
        C4 G3 C4:2 C4 G3 C4:2""", 3),
    "Ah ! vous dirai-je maman": (100, """
        C4 C4 G4 G4 A4 A4 G4:2 F4 F4 E4 E4 D4 D4 C4:2
        G4 G4 F4 F4 E4 E4 D4:2 G4 G4 F4 F4 E4 E4 D4:2
        C4 C4 G4 G4 A4 A4 G4:2 F4 F4 E4 E4 D4 D4 C4:2""", 0),
    "Au clair de la lune": (96, """
        C4 C4 C4 D4 E4:2 D4:2 C4 E4 D4 D4 C4:4
        C4 C4 C4 D4 E4:2 D4:2 C4 E4 D4 D4 C4:4
        D4 D4 D4 D4 A3:2 A3:2 D4 C4 B3 A3 G3:4
        C4 C4 C4 D4 E4:2 D4:2 C4 E4 D4 D4 C4:4""", 0),
    "Berceuse de Brahms": (84, """
        E4:.5 E4:.5 G4:2 E4:.5 E4:.5 G4:2 E4:.5 G4:.5 C5 B4:1.5 A4:.5 A4 G4
        D4:.5 E4:.5 F4 D4 D4:.5 E4:.5 F4:2 D4:.5 F4:.5 B4:.5 A4:.5 G4 B4 C5:2
        C4:.5 C4:.5 C5:2 A4:.5 F4:.5 G4:2 E4:.5 C4:.5 F4 G4 A4 G4:2
        C4:.5 C4:.5 C5:2 A4:.5 F4:.5 G4:2 E4:.5 C4:.5 F4 E4 D4 C4:3""", 0),
    "Douce nuit": (150, """
        G4:1.5 A4:.5 G4 E4:3 G4:1.5 A4:.5 G4 E4:3
        D5:2 D5 B4:3 C5:2 C5 G4:3
        A4:2 A4 C5:1.5 B4:.5 A4 G4:1.5 A4:.5 G4 E4:3
        A4:2 A4 C5:1.5 B4:.5 A4 G4:1.5 A4:.5 G4 E4:3
        D5:2 D5 F5:1.5 D5:.5 B4 C5:3 E5:3
        C5 G4 E4 G4:1.5 F4:.5 D4 C4:6""", 0),
    "Vive le vent": (120, """
        E4 E4 E4:2 E4 E4 E4:2 E4 G4 C4:1.5 D4:.5 E4:4
        F4 F4 F4:1.5 F4:.5 F4 E4 E4 E4:.5 E4:.5 E4 D4 D4 E4 D4:2 G4:2
        E4 E4 E4:2 E4 E4 E4:2 E4 G4 C4:1.5 D4:.5 E4:4
        F4 F4 F4:1.5 F4:.5 F4 E4 E4 E4:.5 E4:.5 G4 G4 F4 D4 C4:4""", 0),
    "Joyeux anniversaire": (100, """
        G4:.75 G4:.25 A4 G4 C5 B4:2 G4:.75 G4:.25 A4 G4 D5 C5:2
        G4:.75 G4:.25 G5 E5 C5 B4 A4:2 F5:.75 F5:.25 E5 C5 D5 C5:3""", 0),
}

SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def parse(melody):
    notes = []
    for token in melody.split():
        name, _, beats = token.partition(":")
        m = re.fullmatch(r"([A-G])([#b]?)(\d)", name)
        midi = 12 * (int(m.group(3)) + 1) + SEMITONES[m.group(1)] + {"#": 1, "b": -1, "": 0}[m.group(2)]
        notes.append((midi, float(beats or 1)))
    return notes


def tone(midi, seconds, velocity):
    freq = 440 * 2 ** ((midi - 69) / 12) * 2  # one octave up: music-box register
    t = np.arange(int(SR * max(seconds, 1.6))) / SR
    sig = (np.sin(2 * np.pi * freq * t)
           + .35 * np.sin(2 * np.pi * 2 * freq * t) * np.exp(-t * 6)
           + .15 * np.sin(2 * np.pi * 3.01 * freq * t) * np.exp(-t * 9))
    return velocity * sig * np.exp(-t * 3.2) * np.minimum(1, t * 400)


def render(bpm, melody, round_entries):
    beat = 60 / bpm
    notes = parse(melody)
    if not round_entries:
        notes = notes * 2  # short tunes are played twice
    length = sum(b for _, b in notes)
    voices = [(0, .5, notes)]
    for i in range(round_entries):
        voices.append((length + 4 + 8 * i, .45 - .06 * i, notes * 2))
    total = max(start + sum(b for _, b in n) for start, _, n in voices)
    out = np.zeros(int(SR * (total * beat + 3)))
    for start, velocity, voice in voices:
        b = start
        for midi, beats in voice:
            s = int(SR * b * beat)
            x = tone(midi, beats * beat, velocity)[: len(out) - s]
            out[s:s + len(x)] += x
            b += beats
    return out / np.max(np.abs(out)) * .85


def write_mp3(audio, path):
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "out.wav"
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes((audio * 32767).astype(np.int16).tobytes())
        fade_start = len(audio) / SR - 3
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-af", f"afade=t=out:st={fade_start}:d=3",
                        "-b:a", "128k", str(path)], check=True)


def main():
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out_dir.mkdir(parents=True, exist_ok=True)
    for title, (bpm, melody, round_entries) in SONGS.items():
        write_mp3(render(bpm, melody, round_entries), out_dir / f"{title}.mp3")
        print(f"{title}.mp3")


if __name__ == "__main__":
    main()
