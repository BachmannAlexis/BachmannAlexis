# Lunii song pack builder

Turns a folder of songs or stories into a STUdio pack (`.zip`) that
[Lunii.QT](https://github.com/o-daneel/Lunii.QT) can install on a Lunii.

## Setup (once)

1. Install [Python 3](https://www.python.org/downloads/), then `pip install pillow`.
2. Install ffmpeg (recommended; it plays the start of each song as a menu preview).
   On Windows/macOS, Lunii.QT's *Tools → FFMPEG* menu downloads it to `~/.lunii-qt`. Add that folder to your PATH or install ffmpeg separately.

## Usage

```
Comptines/
  01 - Le petit bonhomme.mp3
  02 - Frère Jacques.mp3
  02 - Frère Jacques.titre.mp3   (optional: a recording saying "Frère Jacques")
  _titre.mp3                     (optional: a recording saying "Mes comptines")
```

```
python3 build_studio_pack.py Comptines --title "Mes comptines"
```

Then drag `Mes comptines.zip` into Lunii.QT with the Lunii plugged in.

On the Lunii: select the pack, press OK, turn the wheel to choose a song, press OK to play.
At the end of a song (or with HOME) it returns to the song list.

To add songs later, delete the pack in Lunii.QT, add the files to the folder, rebuild and re-import.
