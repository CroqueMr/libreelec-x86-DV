# SPDX-License-Identifier: MIT
"""Compare raw receiver words with the LLDV HDMI test carrier."""
import argparse
from array import array
from pathlib import Path
import struct
import sys


def verify(carrier, capture, width, height, depth):
    if width <= 0 or width % 2 or height <= 0 or depth not in (10, 12):
        raise ValueError("Expected an even width, positive height and 10 or 12 useful bits")
    pixels = width * height
    if len(carrier) != 4 * pixels or len(capture) != 4 * pixels:
        raise ValueError("Expected one tightly packed XRGB8888 raster and one yuv422p12le frame")

    words = array("H", capture)
    if sys.byteorder != "little":
        words.byteswap()
    values = memoryview(words)
    luma, cb, cr = values[:pixels], values[pixels:3*pixels//2], values[3*pixels//2:]
    low_bits = [0, 0, 0]
    for i, (b0, g0, r0, _, b1, g1, r1, _) in enumerate(struct.iter_unpack("8B", carrier)):
        y0, y1 = g0 * 16 + (b0 & 15), g1 * 16 + (b1 & 15)
        u, v = r0 * 16 + (b0 >> 4), r1 * 16 + (b1 >> 4)
        low_bits[0] |= (y0 | y1) & 3
        low_bits[1] |= u & 3
        low_bits[2] |= v & 3
        expected = (y0, y1, u, v)
        actual = (luma[2*i], luma[2*i+1], cb[i], cr[i])
        if actual != expected:
            row, pair = divmod(i, width // 2)
            raise ValueError(f"Row {row}, pair {pair}: expected Y0/Y1/Cb/Cr {expected}, got {actual}")
    if depth == 10 and any(low_bits):
        raise ValueError(f"10-bit carrier has nonzero padding in Y/Cb/Cr: {low_bits}")
    return low_bits


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("carrier", type=Path, help="sent little-endian XRGB8888 test raster")
    parser.add_argument("capture", type=Path, help="received right-aligned planar 12-bit LE words")
    parser.add_argument("--width", type=int, default=3840)
    parser.add_argument("--height", type=int, default=2160)
    parser.add_argument("--bits", type=int, choices=(10, 12), required=True)
    args = parser.parse_args()
    try:
        low_bits = verify(args.carrier.read_bytes(), args.capture.read_bytes(),
                          args.width, args.height, args.bits)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")
    print(f"All Y/Cb/Cr words match. Low-bit coverage Y/Cb/Cr: {low_bits}")


if __name__ == "__main__":
    main()
