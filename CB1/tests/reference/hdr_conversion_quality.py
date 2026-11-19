# SPDX-License-Identifier: MIT
"""Opt-in Basic/Expert HDR10 output contract, not a Dolby equivalence claim."""
import math

# ITU-R BT.2124-0 Annex 1: inverse PQ RGB, linear BT.2020 RGB->LMS,
# PQ LMS->ICtCp, then T=Ct/2. DeltaE_ITP=1 indicates potential visibility.
# https://www.itu.int/dms_pubrec/itu-r/rec/bt/R-REC-BT.2124-0-201901-I!!PDF-E.pdf
def itp(rgb_pq):
    def eotf(v):
        v = v**(32/2523)
        return 10000*(max(v-3424/4096, 0)/(2413/128-2392/128*v))**(16384/2610)
    def pq(v):
        v = (v/10000)**(2610/16384)
        return ((3424/4096+2413/128*v)/(1+2392/128*v))**(2523/32)
    rgb = [eotf(v) for v in rgb_pq]
    lms = [pq(sum(a*b for a, b in zip(row, rgb))/4096) for row in
           ((1688, 2146, 262), (683, 2951, 462), (99, 309, 3688))]
    return [sum(a*b for a, b in zip(row, lms))/4096 for row in
            ((2048, 2048, 0), (3305, -6806.5, 3501.5), (17933, -17390, -543))]


def delta_e_itp(a, b):
    return 720*math.sqrt(sum((x-y)**2 for x, y in zip(itp(a), itp(b))))


def check_hdr_conversion_quality(expected, actual, neutral_indices=()):
    """Fixed caps: 4 full-range code10, DE<=1, p99.9 DE<=.25 if >=1000
    pixels, expected/known-neutral <=.25 code10. Never relax signal black.
    Full-range code10 units deliberately also bound limited-range outputs.
    Small rasters cannot establish a meaningful 0.1% tail; report it as None.
    These are numerical gates, not proof about a physical television.
    """
    assert expected and len(expected) == len(actual), 'HDR raster shape'
    for raster in (expected, actual):
        assert all(len(p) == 3 and all(isinstance(v, (int, float)) and
                   math.isfinite(v) and 0 <= v <= 1 for v in p) for p in raster), 'finite PQ RGB'
    neutral_indices = set(neutral_indices)
    deltas, codes, neutral_error = [], [], 0
    for i, (wanted, got) in enumerate(zip(expected, actual)):
        assert wanted != [0, 0, 0] or got == [0, 0, 0], 'exact black/border'
        error = max(abs(a-b) for a, b in zip(wanted, got))*1023
        assert error <= 4, ('four-code10 HDR cap', i, error)
        delta = delta_e_itp(wanted, got)
        assert delta <= 1, ('DeltaE_ITP HDR cap', i, delta)
        if i in neutral_indices or max(wanted)-min(wanted) <= 1e-7:
            neutral_error = max(neutral_error, error)
            assert error <= .25, ('neutral quarter-code10 cap', i, error)
        deltas.append(delta)
        codes.append(error)
    p999 = sorted(deltas)[math.ceil(.999*len(deltas))-1] if len(deltas) >= 1000 else None
    assert p999 is None or p999 <= .25, ('p99.9 DeltaE_ITP HDR cap', p999)
    return dict(max_code10=max(codes), max_delta_e_itp=max(deltas),
                p999_delta_e_itp=p999, max_neutral_code10=neutral_error, pixels=len(actual))
