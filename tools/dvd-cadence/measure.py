#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Measure cadence reconstruction methods on the synthetic DVD corpus.

For each sample and method, the decoded stream is processed with a libavfilter graph
and compared with the progressive frames the sample was made from. The output is
resampled to the reference rate first, so a field-rate deinterlace and an inverse
telecine are compared on the same frames.

usage: measure.py CORPUS_DIR [--json OUT]
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import corpus  # noqa: E402

# Stock Kodi on the x86 Generic build (VAAPI): Auto falls back to VAAPI Bob; the FFmpeg
# software path uses bwdif at field rate. "weave" shows the coded frames unchanged.
METHODS = {
    "weave": "",
    "bwdif": "bwdif=mode=send_field:parity=auto:deint=all",
    "ivtc": "fieldmatch=order=auto:combmatch=full,"
            "bwdif=mode=send_frame:parity=auto:deint=interlaced,decimate",
    "fieldmatch": "fieldmatch=order=auto:combmatch=full,"
                  "bwdif=mode=send_frame:parity=auto:deint=interlaced",
}

# Progressive frames each sample was made from: (size, rate).
REFERENCE = {
    "ntsc_soft32": (corpus.NTSC, corpus.FILM),
    "ntsc_hard32": (corpus.NTSC, corpus.FILM),
    "ntsc_video": (corpus.NTSC, "60000/1001"),
    "pal_22": (corpus.PAL, "25"),
    "pal_22_progressive": (corpus.PAL, "25"),
    "pal_video": (corpus.PAL, "50"),
}


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
         "stream=r_frame_rate,avg_frame_rate,field_order", "-of", "json", str(path)],
        check=True, capture_output=True, text=True).stdout
    return json.loads(out)["streams"][0]


def frames(path):
    """Decoded frame flags as Kodi receives them: (interlaced, repeat_pict, pts)."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
         "frame=interlaced_frame,repeat_pict,best_effort_timestamp_time", "-of", "csv=p=0",
         str(path)], check=True, capture_output=True, text=True).stdout
    result = []
    for line in out.split():
        fields = dict(zip(("best_effort_timestamp_time", "interlaced_frame", "repeat_pict"),
                          line.split(",")))
        pts = fields.get("best_effort_timestamp_time", "N/A")
        result.append((fields.get("interlaced_frame") == "1", int(fields.get("repeat_pict", 0)),
                       None if pts == "N/A" else float(pts)))
    return result


def process(path, graph, reference, seconds):
    """Frame count of the method output and mean PSNR against the reference.

    An output with the reference frame count is compared frame by frame. Any other
    output is first resampled to the reference rate by timestamp.
    """
    size, rate = reference
    method = graph or "null"
    count = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vf", method,
         "-an", "-f", "null", "-"], check=True, capture_output=True, text=True).stderr
    produced = int(re.findall(r"frame=\s*(\d+)", count)[-1])
    num, _, den = rate.partition("/")
    expected = round(float(num) / float(den or 1) * seconds)
    # psnr pairs frames by timestamp, so both inputs get the same time base.
    align = (f"settb=1/({rate}),setpts=N" if produced == expected
             else f"setpts=PTS-STARTPTS,fps={rate}")
    filtergraph = (f"[0:v]{method},{align},format=yuv420p[a];"
                   f"{corpus.source(size, rate, seconds)},settb=1/({rate}),setpts=N[r];"
                   f"[a][r]psnr")
    psnr = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-filter_complex", filtergraph,
         "-an", "-f", "null", "-"], check=True, capture_output=True, text=True).stderr
    match = re.search(r"PSNR .* average:([\d.inf]+)", psnr)
    return produced, float(match.group(1)) if match else None


def measure(corpus_dir, seconds):
    rows = []
    for name, reference in REFERENCE.items():
        path = Path(corpus_dir) / f"{name}.mpg"
        info = probe(path)
        for method, graph in METHODS.items():
            produced, psnr = process(path, graph, reference, seconds)
            rows.append({"sample": name, "field_order": info.get("field_order"),
                         "stream_rate": info["avg_frame_rate"], "method": method,
                         "frames": produced, "fps": round(produced / seconds, 3),
                         "psnr": psnr})
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--seconds", type=float, default=8)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    rows = measure(args.corpus, args.seconds)
    print(f"{'sample':20} {'method':10} {'frames':>6} {'fps':>7} {'psnr':>6}")
    for row in rows:
        psnr = f"{row['psnr']:.2f}" if row["psnr"] is not None else "-"
        print(f"{row['sample']:20} {row['method']:10} {row['frames']:6} {row['fps']:7} {psnr:>6}")
    if args.json:
        args.json.write_text(json.dumps(rows, indent=2) + "\n")


if __name__ == "__main__":
    sys.exit(main())
