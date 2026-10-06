"""Lossless captured-pixel oracle, independent of the GPU reduction record."""
from collections import Counter
from decimal import Decimal as D, localcontext
import argparse
import hashlib
import math
from pathlib import Path
import struct

from dv_analysis_oracle import ERROR, analyze, code, halfup, permitted_bins, record_values


def analyze_capture(pixels, width, height):
    if width <= 0 or height <= 0 or len(pixels) != width*height*16:
        raise ValueError('exact RGBA32F capture geometry required')
    words = memoryview(pixels).cast('I')
    populations = Counter()
    for y in range(0, height, 2):
        for x in range(0, width, 2):
            group = []
            for yy in range(y, min(y+2, height)):
                for xx in range(x, min(x+2, width)):
                    offset = (yy*width+xx)*4
                    group.extend(words[offset:offset+3])
                    if words[offset+3] != 0x3f800000:
                        raise ValueError('captured analyzer alpha must be one')
            populations[tuple(group)] += 1
    weighted = []
    for bits, count in populations.items():
        values = [struct.unpack('<f', struct.pack('<I', q))[0] for q in bits]
        if not all(math.isfinite(q) and 0 <= q <= 1 for q in values):
            raise ValueError('captured PQ pixel outside finite domain')
        rgb = [values[n:n+3] for n in range(0, len(values), 3)]
        # Decimal equations decode each represented RGB component before the
        # linear group average and maximum. Multiplicity only avoids replaying
        # identical captured groups; it does not assume a uniform source.
        size = (2, 2) if len(rgb) == 4 else (len(rgb), 1)
        statistics, groups = analyze(rgb, size, (0, 0, *size))
        assert groups == 1
        weighted.append((statistics[0], count))
    groups = sum(populations.values())
    with localcontext() as context:
        context.prec = 100
        mean = sum(value*count for value, count in weighted)/groups
    return [min(value for value, _ in weighted), mean,
            max(value for value, _ in weighted)], groups, populations


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    pixels = (args.directory/'rgb-active.f32').read_bytes()
    record = list(struct.unpack('<12I', (args.directory/'record.u32').read_bytes()))
    expected, groups, populations = analyze_capture(pixels, 2160, 2160)
    assert groups == 1166400 == record[3]
    raw, selected, rounded, _ = record_values(record)
    errors = [observed-reference for observed, reference in zip(raw, expected)]
    selected_errors = [D.from_float(observed)-reference
                       for observed, reference in zip(selected, expected)]
    assert all(abs(error) <= ERROR for error in errors + selected_errors)
    bins = [permitted_bins(reference) for reference in expected]
    for observed, reference, (low, high) in zip(rounded, expected, bins):
        assert low <= D(str(observed)) <= high
        if low == high:
            assert D(str(observed)) == halfup(reference)
        if code(low) == code(high):
            assert code(D(str(observed))) == code(halfup(reference))
    print('ACTUAL_PIXEL_QUALIFICATION expected_decimal=', list(map(str, expected)),
          'raw_errors=', list(map(str, errors)),
          'selected_errors=', list(map(str, selected_errors)),
          'rounded=', rounded, 'codes=', [code(D(str(q))) for q in rounded],
          'ideal_source_image=not_inferred_from_P010_or_record')
    print('CAPTURE_ORACLE precision=100 active=840,0,2160,2160',
          'groups=', groups, 'distinct_groups=', len(populations),
          'sha256=', hashlib.sha256(pixels).hexdigest(),
          'raw=', list(map(str, raw)), 'selected=', selected)
    for name in ('record.u32', 'source-p010.u16', 'source-rpu.bin'):
        data = (args.directory/name).read_bytes()
        print('CAPTURE_INPUT', name, 'bytes=', len(data),
              'sha256=', hashlib.sha256(data).hexdigest())


if __name__ == '__main__':
    main()
