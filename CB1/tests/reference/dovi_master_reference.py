# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent integer reconstruction, ETSI CCM 001 and declared spatial contract 1."""


def clip(value, low=0, high=65535):
    return max(low, min(high, value))


def shift(value, bits):
    return value >> bits if bits >= 0 else value << -bits


def reshape_component(data, component, bl_codes):
    curves = data["curves"]
    samples = [clip(s, c["pivots"][0], c["pivots"][-1])
               for s, c in zip(bl_codes, curves)]
    curve = curves[component]
    sample = samples[component]
    piece = min(next((i for i, p in enumerate(curve["pivots"][1:]) if sample < p),
                     len(curve["pivots"]) - 2), len(curve["pivots"]) - 2)
    depth = data["bl_depth"]
    order = curve["order"][piece]
    if curve["method"][piece] == 0:
        total = sum(curve["poly"][piece][i] * (sample ** i << (20 - depth * i))
                    for i in range(order + 1))
    else:
        a, b, c = samples
        first = [a << (20 - depth), b << (20 - depth), c << (20 - depth),
                 a * b << (20 - 2 * depth), a * c << (20 - 2 * depth),
                 b * c << (20 - 2 * depth)]
        first.append(first[3] * first[2] >> 20)
        second = [v * v >> 20 for v in first]
        third = [v * w >> 20 for v, w in zip(first, second)]
        terms = first + (second if order >= 2 else []) + (third if order >= 3 else [])
        coefficients = [v for row in curve["mmr"][piece][:order] for v in row]
        total = (curve["mmr_constant"][piece] << 20) + sum(
            coefficient * term for coefficient, term in zip(coefficients, terms))
    return clip(max(0, total) >> (4 + data["denom"]))


def nlq_residual(data, component, el_code):
    if not data["residual"]:
        return 0
    nlq = data["nlq"][component]
    delta = el_code - nlq["offset"]
    if not delta:
        return 0
    sign = -1 if delta < 0 else 1
    scaled = (2 * delta - sign) << (10 - data["el_depth"])
    total = scaled * nlq["slope"] + (nlq["threshold"] << (11 - data["el_depth"])) * sign
    bound = nlq["maximum"] << (11 - data["el_depth"])
    return shift(clip(total, -bound, bound), data["denom"] - 5 - data["el_depth"])


def reconstruct(v, r, output_depth):
    return clip((v + r + (1 << (15 - output_depth))) >> (16 - output_depth),
                0, (1 << output_depth) - 1)


def pixel(plane, x, y):
    return plane[clip(y, 0, len(plane) - 1)][clip(x, 0, len(plane[0]) - 1)]


def reduce_mmr_luma(plane, x, y):
    # Contract 1: adjacent rows 2*y and 2*y+1 of the original BL luma.
    rows = [(pixel(plane, 2 * x - 1, row) + 2 * pixel(plane, 2 * x, row) +
             pixel(plane, 2 * x + 1, row) + 2) >> 2 for row in [2 * y, 2 * y + 1]]
    return (sum(rows) + 1) >> 1


def resample_plane(plane, operation):
    horizontal = operation == "h"
    height, width = len(plane), len(plane[0])
    output = []
    for y in range(height if horizontal else 2 * height):
        row = []
        for x in range(2 * width if horizontal else width):
            n, phase = (x // 2, x % 2) if horizontal else (y // 2, y % 2)
            if horizontal:
                if not phase:
                    row.append(pixel(plane, n, y))
                    continue
                offsets, weights, bits = range(-3, 5), [22, 94, -524, 2456, 2456, -524, 94, 22], 12
            elif operation == "bl-v":
                offsets = range(-3, 3) if not phase else range(-2, 4)
                weights, bits = ([2, -12, 65, 222, -25, 4] if not phase else
                                 [4, -25, 222, 65, -12, 2]), 8
            elif operation == "el-y-v":
                offsets = range(-2, 2) if not phase else range(-1, 3)
                weights, bits = ([-3, 29, 111, -9] if not phase else [-9, 111, 29, -3]), 7
            elif operation == "el-c-v":
                offsets, weights, bits = ([-1, 0], [64, 192], 8) if not phase else ([0, 1], [192, 64], 8)
            else:
                raise ValueError("unsupported spatial operation")
            value = sum(weight * (pixel(plane, n + offset, y) if horizontal else
                                  pixel(plane, x, n + offset))
                        for offset, weight in zip(offsets, weights))
            row.append(clip((value + (1 << (bits - 1))) >> bits))
        output.append(row)
    return output
