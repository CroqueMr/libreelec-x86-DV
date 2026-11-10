#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Generate synthetic DVD-style MPEG-2 program streams with known cadences.

Every sample is made from a deterministic lavfi source, so the original progressive
frames can be regenerated for quality comparisons (see measure.py).

With --containers, the soft-telecine sample is also written as Matroska, as a DVD-Video
VIDEO_TS folder and as an ISO image (requires mkvpropedit, dvdauthor and xorriso).

usage: corpus.py OUTPUT_DIR [--seconds N] [--containers]
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys

NTSC = (720, 480)
PAL = (720, 576)
FILM = "24000/1001"


def source(size, rate, seconds):
    """Deterministic moving test pattern. Every frame differs (counter, motion).

    The pattern is rendered at twice the size and filtered down, like camera or film
    content. Unfiltered one-pixel edges look like combing to field detectors.
    """
    w, h = size
    return (f"testsrc2=size={2 * w}x{2 * h}:rate={rate}:duration={seconds},"
            f"scale={w}:{h}:flags=lanczos,format=yuv420p")


def run(args):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


MPEG2 = ["-c:v", "mpeg2video", "-q:v", "2", "-g", "12", "-maxrate", "9000k",
         "-bufsize", "1835k", "-an"]
INTERLACED = ["-flags", "+ildct+ilme", "-top", "1"]


def encode(filtergraph, out, extra=()):
    run(["-f", "lavfi", "-i", filtergraph, *MPEG2, *extra, "-f", "dvd", str(out)])


def soft_telecine(es: bytes) -> bytes:
    """Turn a progressive 23.976 MPEG-2 elementary stream into 3:2 soft telecine.

    Like DGPulldown: the sequence header announces 29.97, progressive_sequence is
    cleared and the picture coding extensions carry the repeat_first_field and
    top_field_first pattern. The stream must be encoded without B-frames so that
    coding order equals display order.
    """
    data = bytearray(es)
    pattern = [(1, 1), (0, 0), (0, 1), (1, 0)]  # (top_field_first, repeat_first_field)
    picture = 0
    i = data.find(b"\x00\x00\x01")
    while i >= 0 and i + 8 < len(data):
        code = data[i + 3]
        p = i + 4
        if code == 0xB3:  # sequence header: frame_rate_code -> 30000/1001
            data[p + 3] = (data[p + 3] & 0xF0) | 0x04
        elif code == 0xB5:
            ext = data[p] >> 4
            if ext == 1:  # sequence extension: progressive_sequence = 0
                data[p + 1] &= ~0x08
            elif ext == 8:  # picture coding extension
                tff, rff = pattern[picture % 4]
                if (data[p + 2] & 0x03) != 0x03:
                    raise ValueError("field pictures are not supported")
                data[p + 3] = (data[p + 3] & ~0x82) | (0x80 if tff else 0) | (0x02 if rff else 0)
                data[p + 4] |= 0x80  # progressive_frame
                picture += 1
        i = data.find(b"\x00\x00\x01", i + 3)
    if not picture:
        raise ValueError("no picture coding extension found")
    return bytes(data)


# Film frame N of the 3:2 pattern starts at field 2N + (N + 1) // 2 (59.94 fields/s),
# the presentation time a DVD encoder writes.
SOFT_TIMESTAMPS = "(2*N+floor((N+1)/2))*1001/(60000*TB)"


def make_soft(out_dir, seconds):
    m2v = out_dir / "ntsc_soft32.m2v"
    run(["-f", "lavfi", "-i", source(NTSC, FILM, seconds), *MPEG2, "-bf", "0",
         "-f", "mpeg2video", str(m2v)])
    m2v.write_bytes(soft_telecine(m2v.read_bytes()))
    run(["-f", "mpegvideo", "-i", str(m2v), "-c:v", "copy", "-bsf:v",
         f"setts=pts={SOFT_TIMESTAMPS}:dts={SOFT_TIMESTAMPS}", "-f", "dvd",
         str(out_dir / "ntsc_soft32.mpg")])
    m2v.unlink()


def make_containers(out_dir):
    """The soft-telecine sample as Matroska, VIDEO_TS folder and ISO image."""
    # Matroska remux with the 3:2 timestamps that states the film rate, the average
    # frame rate of those timestamps. The MPEG-2 stream still codes 29.97.
    mkv = out_dir / "ntsc_soft32.mkv"
    run(["-fflags", "+genpts", "-i", str(out_dir / "ntsc_soft32.mpg"), "-c", "copy",
         str(mkv)])
    subprocess.run(["mkvpropedit", "-q", str(mkv), "--edit", "track:v1", "--set",
                    "default-duration=41708333"], check=True, capture_output=True)
    # DVD-Video folder and ISO image, the sample as title 1
    disc = out_dir / "ntsc_soft32_dvd"
    env = {**os.environ, "VIDEO_FORMAT": "NTSC"}
    for args in (["-t", str(out_dir / "ntsc_soft32.mpg")], ["-T"]):
        subprocess.run(["dvdauthor", "-o", str(disc), *args], check=True, env=env,
                       capture_output=True)
    subprocess.run(["xorriso", "-as", "mkisofs", "-quiet", "-V", "CADENCE", "-o",
                    str(out_dir / "ntsc_soft32.iso"), str(disc)], check=True,
                   capture_output=True)


SAMPLES = {
    # NTSC film, 3:2 pulldown recorded in the fields (hard telecine), 29.97i.
    "ntsc_hard32": lambda s: (source(NTSC, FILM, s) + ",telecine=first_field=top:pattern=23", INTERLACED),
    # True interlaced NTSC video: every field is a different instant (59.94 fields/s).
    "ntsc_video": lambda s: (source(NTSC, "60000/1001", s) + ",interlace=scan=tff", INTERLACED),
    # PAL film: 25p frames stored in interlace-flagged 576i (2:2).
    "pal_22": lambda s: (source(PAL, "25", s), INTERLACED),
    # PAL film flagged progressive.
    "pal_22_progressive": lambda s: (source(PAL, "25", s), ()),
    # True interlaced PAL video (50 fields/s).
    "pal_video": lambda s: (source(PAL, "50", s) + ",interlace=scan=tff", INTERLACED),
}


def make_mixed(out_dir, seconds):
    """Hard-telecined film followed by true interlaced video in one stream."""
    half = seconds / 2
    film = source(NTSC, FILM, half) + ",telecine=first_field=top:pattern=23,setpts=PTS-STARTPTS"
    video = source(NTSC, "60000/1001", half) + ",interlace=scan=tff,setpts=PTS-STARTPTS"
    graph = f"{film}[a];{video}[b];[a][b]concat=n=2:v=1:a=0,fps=30000/1001"
    encode(graph, out_dir / "ntsc_mixed.mpg", INTERLACED)


def disc_title(iso, out_dir):
    """Copy title 1 out of an ISO image, as a DVD player reads it; return its VOB."""
    vob = Path(out_dir) / "VTS_01_1.VOB"
    subprocess.run(["xorriso", "-osirrox", "on", "-indev", str(iso), "-extract",
                    "/VIDEO_TS/VTS_01_1.VOB", str(vob)], check=True, capture_output=True)
    return vob


def coded_frame_rate(path):
    """frame_rate_code of the first MPEG-2 sequence header of a file (4: 30000/1001)."""
    es = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v", "-c", "copy",
                         "-frames:v", "1", "-f", "mpeg2video", "-"], check=True,
                        capture_output=True).stdout
    i = es.index(b"\x00\x00\x01\xb3")
    return es[i + 7] & 0x0F


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seconds", type=float, default=8)
    parser.add_argument("--containers", action="store_true",
                        help="also write the soft-telecine sample as MKV, VIDEO_TS and ISO")
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    make_soft(args.output, args.seconds)
    for name, make in SAMPLES.items():
        graph, extra = make(args.seconds)
        encode(graph, args.output / f"{name}.mpg", extra)
    make_mixed(args.output, args.seconds)
    if args.containers:
        make_containers(args.output)
    return sorted(args.output.glob("*.mpg"))


if __name__ == "__main__":
    for sample in main():
        print(sample)
