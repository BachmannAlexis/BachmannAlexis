# Usage: python3 frere_jacques_music_box.py out.wav  (then convert to MP3 with ffmpeg)
# Music-box rendition of "Frère Jacques" (traditional, public domain): melody, then a 3-voice round.
import sys, wave, numpy as np
SR, BPM = 44100, 104
Q = 60 / BPM
NOTES = {"C4":60,"D4":62,"E4":64,"F4":65,"G4":67,"A4":69,"G3":55,"C5":72}
# (note, beats) — 8 bars of 4 beats, in C major
phrase = [("C4",1),("D4",1),("E4",1),("C4",1)]*2 + [("E4",1),("F4",1),("G4",2)]*2 \
       + [("G4",.5),("A4",.5),("G4",.5),("F4",.5),("E4",1),("C4",1)]*2 + [("C4",1),("G3",1),("C4",2)]*2
def tone(midi, dur, vel):
    f = 440 * 2 ** ((midi - 69) / 12) * 2  # one octave up: music-box register
    n = int(SR * max(dur, 1.6)); t = np.arange(n) / SR
    sig = (np.sin(2*np.pi*f*t) + .35*np.sin(2*np.pi*2*f*t)*np.exp(-t*6) + .15*np.sin(2*np.pi*3.01*f*t)*np.exp(-t*9))
    env = np.exp(-t * 3.2) * np.minimum(1, t * 400)
    return vel * sig * env
def render(voices, total_beats):
    out = np.zeros(int(SR * (total_beats * Q + 3)))
    for start_beat, vel, notes in voices:
        b = start_beat
        for name, beats in notes:
            s = int(SR * b * Q); x = tone(NOTES[name], beats * Q, vel)
            out[s:s+len(x)] += x[:len(out)-s]; b += beats
    return out
voices = [(0, .5, phrase)]                      # solo, 32 beats
for i, v in enumerate((.45, .38, .32)):         # round: entries every 2 bars
    voices.append((32 + 4 + 8*i, v, phrase*2))
audio = render(voices, 32 + 4 + 16 + 64)
audio = audio / np.max(np.abs(audio)) * .85
with wave.open(sys.argv[1], "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((audio * 32767).astype(np.int16).tobytes())
