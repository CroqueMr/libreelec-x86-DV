# SPDX-License-Identifier: GPL-3.0-only
"""Independent scalar controls; not a Dolby display-management emulator."""


def pq(nits):
    v = (nits / 10000) ** (2610 / 16384)
    return ((3424 / 4096 + 2413 / 128 * v) / (1 + 2392 / 128 * v)) ** (2523 / 32)


def analysis(l1, l3=None):
    out = [v + (o - 2048) for v, o in zip(l1, l3 or [2048]*3)]
    if not 0 <= out[0] <= out[2] <= out[1] <= 4095:
        raise ValueError('Invalid effective analysis')
    return out


def anchors(table, target, master):
    table = sorted(table)
    if len({q for q, _ in table}) != len(table):
        raise ValueError('Duplicate anchor')
    if not table:
        return [2048]*5
    if target <= table[0][0]:
        return list(table[0][1])
    for q, controls in table:
        if q == target:
            return list(controls)
    lower = max((a for a in table if a[0] < target), default=None)
    upper = min((a for a in table if a[0] > target), default=None)
    if upper is None:
        if master <= lower[0] or target >= master:
            return [2048]*5
        upper = (master, [2048]*5)
    t = (target-lower[0]) / (upper[0]-lower[0])
    return [x*(1-t)+y*t for x, y in zip(lower[1], upper[1])]


def trim_rgb(rgb, target, codes):
    s, o, p = codes[0]/4096+.5, codes[1]/4096-.5, codes[2]/4096+.5
    c, g = codes[3]/4096-.5, codes[4]/4096-.5
    out = [target*max(0, min(1, v/target*s+o))**p for v in rgb]
    y = sum(v*w for v, w in zip(out, (.22897, .69174, .07929)))
    if y <= 0 or g == 0:
        return out
    return [v*((1+c)*v/y)**g if v > 0 else 0 for v in out]


def cm4_target(index, table):
    matches = [(maximum, minimum) for i, maximum, minimum in table if i == index]
    if len(matches) != 1:
        raise ValueError('Missing or duplicate target')
    return matches[0]
