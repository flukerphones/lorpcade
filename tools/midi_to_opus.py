#!/usr/bin/env python3
"""Render a MIDI file to Opus through an SF2 soundfont. Standard library only.

    python3 tools/midi_to_opus.py tools/music/main_menu.mid \\
        --soundfont path/to/GeneralUser_GS.sf2 \\
        -o tools/site/music/main_menu.opus

Defaults: mono, 32 kbps, 48 kHz, loudness-normalised to about -18 LUFS (menu-music level) with 4 dB of
true-peak headroom, because Opus can overshoot the pre-encode peak by a few dB. Normalisation is two-pass
with one constant gain, so quiet intros and fade-outs stay quiet.

Seamless looping: if the MIDI has a "loopEnd" marker (a meta marker event), the script trims the audio to
exactly that point and mixes the reverb/release tail that rings on past it back onto the start of the file,
which is what continuous playback would sound like. The result loops with no click, no cut-off tail and no
level step. The loop is taken to run from the start of the file. Use --no-loop to keep the plain render, or
--loop-seconds N to set the loop length yourself.

Needs two programs on your PATH:
    fluidsynth   (Ubuntu/Debian: apt install fluidsynth  |  macOS: brew install fluid-synth
                  Windows: https://github.com/FluidSynth/fluidsynth/releases)
    ffmpeg       built with libopus (nearly every build is)

If --soundfont is left out the script uses $SOUNDFONT, then the first *.sf2 in tools/soundfonts/, then the
usual system locations. Soundfonts are big, so *.sf2 is git-ignored: keep yours out of the repo, or in
tools/soundfonts/ where it stays untracked.
"""
import argparse
import glob
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import wave
from array import array
from pathlib import Path

HERE = Path(__file__).resolve().parent
SYSTEM_SF2 = [
    "/usr/share/sounds/sf2/*.sf2",
    "/usr/share/soundfonts/*.sf2",
    "/usr/local/share/soundfonts/*.sf2",
    "/opt/homebrew/share/soundfonts/*.sf2",
    "/usr/share/sounds/sf3/*.sf3",
]


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def need(tool, hint):
    path = shutil.which(tool)
    if not path:
        die(f"'{tool}' was not found on your PATH. {hint}")
    return path


def find_soundfont(explicit):
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_file():
            die(f"soundfont not found: {p}")
        return p
    if os.environ.get("SOUNDFONT"):
        return find_soundfont(os.environ["SOUNDFONT"])
    for pattern in [str(HERE / "soundfonts" / "*.sf[23]")] + SYSTEM_SF2:
        hits = sorted(glob.glob(pattern))
        if hits:
            return Path(hits[0])
    die("no soundfont given. Pass --soundfont file.sf2 (or set $SOUNDFONT, or drop one in tools/soundfonts/).")


def run(cmd):
    print("  $", " ".join(str(c) for c in cmd))
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if r.returncode != 0:
        print(r.stdout, file=sys.stderr)
        die(f"{Path(cmd[0]).name} failed (exit {r.returncode})")
    return r.stdout


def _vlq(d, i):
    v = 0
    while True:
        b = d[i]
        i += 1
        v = (v << 7) | (b & 0x7F)
        if not b & 0x80:
            return v, i


def midi_loop_seconds(path):
    """Seconds from the start to the 'loopEnd' marker, or None (no marker / loopStart isn't at 0)."""
    d = Path(path).read_bytes()
    if d[:4] != b"MThd":
        return None
    ntracks, division = struct.unpack(">HH", d[10:14])
    if division & 0x8000:
        return None  # SMPTE timing: not supported
    pos = 8 + struct.unpack(">I", d[4:8])[0]
    tempos, loop_end, loop_start = {0: 500000}, None, 0
    for _ in range(ntracks):
        if d[pos:pos + 4] != b"MTrk":
            break
        length = struct.unpack(">I", d[pos + 4:pos + 8])[0]
        i, end, tick, status = pos + 8, pos + 8 + length, 0, 0
        while i < end:
            delta, i = _vlq(d, i)
            tick += delta
            b = d[i]
            if b == 0xFF:
                kind = d[i + 1]
                n, j = _vlq(d, i + 2)
                data, i = d[j:j + n], j + n
                if kind == 0x51 and n == 3:
                    tempos[tick] = int.from_bytes(data, "big")
                elif kind == 0x06:
                    text = data.decode("latin-1").strip().lower()
                    if text == "loopend":
                        loop_end = tick
                    elif text == "loopstart":
                        loop_start = tick
            elif b in (0xF0, 0xF7):
                n, i = _vlq(d, i + 1)
                i += n
            else:
                if b & 0x80:
                    status = b
                    i += 1
                i += 1 if (status & 0xF0) in (0xC0, 0xD0) else 2
        pos = end
    if loop_end is None or loop_start != 0:
        return None
    seconds, last_tick, tempo = 0.0, 0, 500000
    for t in sorted(tempos):
        if t >= loop_end:
            break
        seconds += (t - last_tick) * tempo / division / 1e6
        last_tick, tempo = t, tempos[t]
    return seconds + (loop_end - last_tick) * tempo / division / 1e6


def wrap_tail(src, dst, loop_seconds):
    """Trim a 16-bit WAV to loop_seconds and mix whatever rings on after that point onto its start."""
    with wave.open(str(src), "rb") as r:
        ch, width, rate, frames = r.getnchannels(), r.getsampwidth(), r.getframerate(), r.getnframes()
        raw = r.readframes(frames)
    if width != 2:
        die("expected a 16-bit WAV from fluidsynth")
    a = array("h")
    a.frombytes(raw)
    if sys.byteorder == "big":
        a.byteswap()
    cut = round(loop_seconds * rate) * ch
    if cut <= 0 or cut > len(a):
        die(f"loop length {loop_seconds:.2f}s doesn't fit the {len(a) / ch / rate:.2f}s render")
    tail_len = min(len(a) - cut, cut)
    for k in range(tail_len):
        v = a[k] + a[cut + k]
        a[k] = 32767 if v > 32767 else -32768 if v < -32768 else v
    head = a[:cut]
    if sys.byteorder == "big":
        head.byteswap()
    with wave.open(str(dst), "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(head.tobytes())
    return tail_len / ch / rate


def loudnorm_filter(ffmpeg, wav, pre):
    """Two-pass loudnorm, so the whole file gets ONE gain: fades and quiet sections keep their shape."""
    target = "I=-18:TP=-4:LRA=20"
    r = subprocess.run([ffmpeg, "-hide_banner", "-nostats", "-i", str(wav), "-af", f"{pre}loudnorm={target}:print_format=json",
                        "-f", "null", "-"], stderr=subprocess.PIPE, text=True)
    blocks = re.findall(r"\{[^{}]*\}", r.stderr)
    try:
        m = json.loads(blocks[-1])
        measured = (f"measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
                    f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    except (IndexError, KeyError, ValueError):
        print("warning: couldn't measure loudness; falling back to single-pass normalisation", file=sys.stderr)
        return f"{pre}loudnorm={target}"
    return f"{pre}loudnorm={target}:{measured}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("midi", type=Path, help="input .mid file")
    ap.add_argument("-s", "--soundfont", help="SF2 (or SF3) soundfont to play the MIDI with")
    ap.add_argument("-o", "--out", type=Path, help="output file (default: next to the MIDI, .opus)")
    ap.add_argument("-b", "--bitrate", default="32k", help="Opus bitrate (default 32k)")
    ap.add_argument("--stereo", action="store_true", help="keep stereo instead of mixing down to mono")
    ap.add_argument("-r", "--rate", type=int, default=48000, help="render sample rate (default 48000)")
    ap.add_argument("-g", "--gain", type=float, default=1.0,
                    help="fluidsynth master gain (default 1.0; lower it if the raw render clips)")
    ap.add_argument("--no-normalize", action="store_true", help="skip loudness normalisation")
    ap.add_argument("--no-loop", action="store_true", help="don't trim/wrap the tail for a seamless loop")
    ap.add_argument("--loop-seconds", type=float, help="loop length in seconds (default: the MIDI's loopEnd marker)")
    args = ap.parse_args()

    if not args.midi.is_file():
        die(f"MIDI file not found: {args.midi}")
    sf2 = find_soundfont(args.soundfont)
    out = args.out or args.midi.with_suffix(".opus")
    fluid = need("fluidsynth", "Install it with 'apt install fluidsynth' or 'brew install fluid-synth'.")
    ffmpeg = need("ffmpeg", "Install it with 'apt install ffmpeg' or 'brew install ffmpeg'.")

    print(f"midi       {args.midi}\nsoundfont  {sf2}\noutput     {out}")
    out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "render.wav"
        # 1. MIDI -> WAV. -ni = no MIDI input / no shell, -F = render to file as fast as possible.
        print("\n[1/3] rendering MIDI with fluidsynth")
        run([fluid, "-ni", "-q", "-g", str(args.gain), "-r", str(args.rate),
             "-T", "wav", "-F", str(wav), str(sf2), str(args.midi)])
        if not wav.is_file() or wav.stat().st_size < 1024:
            die("fluidsynth produced no audio (is the MIDI file valid?)")

        # 2. Seamless loop: cut at the loop point and fold the ring-out tail back onto the start.
        loop = None if args.no_loop else (args.loop_seconds or midi_loop_seconds(args.midi))
        src = wav
        if loop:
            print(f"\n[2/3] looping: trimming to {loop:.3f}s and folding the tail onto the start")
            src = Path(tmp) / "loop.wav"
            tail = wrap_tail(wav, src, loop)
            print(f"      folded {tail:.2f}s of tail")
        else:
            print("\n[2/3] no loopEnd marker in the MIDI (or --no-loop): keeping the plain render")

        # 3. WAV -> Opus.
        print("\n[3/3] encoding Opus with ffmpeg")
        pre = "" if args.stereo else "pan=mono|c0=0.5*c0+0.5*c1,"
        af = None
        if not args.no_normalize:
            af = loudnorm_filter(ffmpeg, src, pre)
        elif pre:
            af = pre.rstrip(",")
        cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src), "-map_metadata", "-1"]
        if af:
            cmd += ["-af", af]
        cmd += ["-ac", "2" if args.stereo else "1", "-ar", "48000",
                "-c:a", "libopus", "-b:a", args.bitrate, "-vbr", "on", "-application", "audio", str(out)]
        run(cmd)

    print(f"\ndone: {out} ({out.stat().st_size / 1024 / 1024:.2f} MB, "
          f"{'stereo' if args.stereo else 'mono'}, {args.bitrate})")


if __name__ == "__main__":
    main()
