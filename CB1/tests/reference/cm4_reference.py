# SPDX-License-Identifier: GPL-3.0-only
"""Binary64 CB1 CM4 contract. No renderer or candidate C code is called.

IPT/HPE constants: pinned libplacebo colorspace.c, LGPL-2.1-or-later.
Control equations: independent CB1 design, not a licensed Dolby mapper.
"""
import math

BT2020 = [[.708, .292], [.170, .797], [.131, .046], [.3127, .3290]]
HPE = [[.40024, .70760, -.08081], [-.22630, 1.16532, .04570], [0, 0, .91822]]
IPT = [[.4, .4, .2], [4.455, -4.851, .396], [.8056, .3572, -1.1628]]
IPT_INVERSE = [[1, .0975689, .205226], [1, -.113876, .133217], [1, .0326151, -.676887]]
VERTICES = [(1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 1, 1), (0, 0, 1), (1, 0, 1)]


def clamp(v, low=0.0, high=1.0):
    return max(low, min(high, v))


def pq(nits):
    if not math.isfinite(nits) or nits < 0:
        raise ValueError('finite nonnegative luminance required')
    v = (nits/10000)**(2610/16384)
    return ((3424/4096 + 2413/128*v)/(1 + 2392/128*v))**(2523/32)


def eotf(value):
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError('PQ domain required')
    v = value**(32/2523)
    return 10000*(max(v-3424/4096, 0)/(2413/128-2392/128*v))**(16384/2610)


def matvec(matrix, vector):
    return [sum(a*b for a, b in zip(row, vector)) for row in matrix]


def multiply(a, b):
    return [[sum(a[i][k]*b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def inverse(matrix):
    rows = [list(row)+[int(i == j) for j in range(3)] for i, row in enumerate(matrix)]
    for j in range(3):
        pivot = max(range(j, 3), key=lambda i: abs(rows[i][j]))
        rows[j], rows[pivot] = rows[pivot], rows[j]
        if abs(rows[j][j]) < 1e-12:
            raise ValueError('singular primaries')
        scale = rows[j][j]
        rows[j] = [v/scale for v in rows[j]]
        for i in range(3):
            if i != j:
                scale = rows[i][j]
                rows[i] = [a-scale*b for a, b in zip(rows[i], rows[j])]
    return [row[3:] for row in rows]


def basis(primaries):
    if len(primaries) != 4 or any(len(p) != 2 or not all(math.isfinite(v) for v in p)
                                 or p[1] <= 0 for p in primaries):
        raise ValueError('finite positive-y primaries required')
    if primaries[3] != [.3127, .3290]:
        raise ValueError('reference accepts D65 targets only')
    xyz = [[x/y, 1, (1-x-y)/y] for x, y in primaries]
    columns = [[xyz[j][i] for j in range(3)] for i in range(3)]
    scales = matvec(inverse(columns), xyz[3])
    rgb_xyz = [[v*scales[j] for j, v in enumerate(row)] for row in columns]
    cross = [[.92 if i == j else .04 for j in range(3)] for i in range(3)]
    rgb_lms = multiply(multiply(cross, HPE), rgb_xyz)
    luma = rgb_xyz[1]
    luma = [v/sum(luma) for v in luma]
    return luma, rgb_lms, inverse(rgb_lms)


def to_ipt(rgb, coefficients):
    return matvec(IPT, [pq(max(0, v)) for v in matvec(coefficients['rgb_to_lms'], rgb)])


def from_ipt(ipt, coefficients):
    return matvec(coefficients['lms_to_rgb'], [eotf(clamp(v)) for v in matvec(IPT_INVERSE, ipt)])


def circular_weights(hue, centres):
    weights = [math.exp(4*(math.cos(hue-c)-1)) for c in centres]
    return [v/sum(weights) for v in weights]


def decode_controls(controls, peak_nits, primaries):
    if not math.isfinite(peak_nits) or not 0 < peak_nits <= 10000:
        raise ValueError('finite positive peak required')
    def words(key, count, maximum):
        value = controls[key]
        value = value if isinstance(value, (list, tuple)) else [value]
        if len(value) != count or any(type(v) is not int or not 0 <= v <= maximum for v in value):
            raise ValueError('invalid '+key)
        return value
    c = {'peak_nits': peak_nits, 'primaries': primaries, 'sop': [1, 0, 1],
         'chroma_base': 1.0, 'saturation_gain': 1.0, 'mid_exponent': 1.0,
         'clip_strength': 0.0, 'detail_mix': 0.0, 'secondary_gain': [1.0]*6,
         'secondary_rotation': [0.0]*6, 'present': 0, 'one_anchor': 0}
    c['luma'], c['rgb_to_lms'], c['lms_to_rgb'] = basis(primaries)
    if 'primary' in controls:
        p = words('primary', 6, 4095)
        c.update(sop=[p[0]/4096+.5, p[1]/4096-.5, p[2]/4096+.5],
                 chroma_base=2**((p[3]-2048)/4096),
                 saturation_gain=2**((p[4]-2048)/4096),
                 detail_mix=.30*(p[5]-2048)/2048, present=63)
    if 'mid_contrast' in controls:
        c['mid_exponent'] = 2**((words('mid_contrast', 1, 4095)[0]-2048)/2048)
        c['present'] |= 1 << 6
    if 'clip_trim' in controls:
        c['clip_strength'] = .25*(words('clip_trim', 1, 4095)[0]-2048)/2048
        c['present'] |= 1 << 7
    if 'saturation' in controls:
        c['secondary_gain'] = [2**((v-128)/256) for v in words('saturation', 6, 255)]
        c['present'] |= 1 << 8
    if 'hue' in controls:
        c['secondary_rotation'] = [math.pi/12*(v-128)/128 for v in words('hue', 6, 255)]
        c['present'] |= 1 << 9
    c['hue_centres'] = [math.atan2(ipt[2], ipt[1]) for ipt in
                         (to_ipt([v*peak_nits/4 for v in rgb], c) for rgb in VERTICES)]
    return c


def blend_coefficients(lower, upper, weight):
    if not math.isfinite(weight) or not 0 <= weight <= 1 or lower['primaries'] != upper['primaries']:
        raise ValueError('bounded matching-gamut interpolation required')
    if lower['peak_nits'] != upper['peak_nits']:
        raise ValueError('coefficients must use the same output basis')
    out = dict(lower)
    for key in ['sop', 'chroma_base', 'saturation_gain', 'mid_exponent', 'clip_strength',
                'detail_mix', 'secondary_gain', 'secondary_rotation']:
        a, b = lower[key], upper[key]
        out[key] = [x+(y-x)*weight for x, y in zip(a, b)] if isinstance(a, list) else a+(b-a)*weight
    out['present'] = lower['present'] | upper['present']
    out['one_anchor'] = lower['present'] ^ upper['present']
    return out


def trim_rgb(rgb_nits, coefficients):
    if len(rgb_nits) != 3 or not all(math.isfinite(v) for v in rgb_nits):
        raise ValueError('finite RGB required')
    c, p = coefficients, coefficients['peak_nits']
    rgb = list(rgb_nits)
    if c['sop'] != [1, 0, 1]:
        slope, offset, power = c['sop']
        rgb = [p*clamp(v/p*slope+offset)**power for v in rgb]
    y = sum(v*w for v, w in zip(rgb, c['luma']))
    if y > 0 and c['mid_exponent'] != 1:
        x, a = clamp(y/p), c['mid_exponent']
        mapped = x**a/(x**a+(1-x)**a)
        rgb = [p*mapped]*3 if rgb[0] == rgb[1] == rgb[2] else [v*(p*mapped/y) for v in rgb]
    y = sum(v*w for v, w in zip(rgb, c['luma']))
    if y > 0 and c['clip_strength'] != 0:
        x = clamp(y/p)
        t = clamp((x-.5)/.5)
        mapped = clamp(x+c['clip_strength']*x*t*t*(3-2*t))
        rgb = [p*mapped]*3 if rgb[0] == rgb[1] == rgb[2] else [v*(p*mapped/y) for v in rgb]
    colour = (c['chroma_base'] != 1 or c['saturation_gain'] != 1 or
              c['secondary_gain'] != [1]*6 or c['secondary_rotation'] != [0]*6)
    if not colour or max(rgb)-min(rgb) <= 1e-12:
        return rgb
    ipt = to_ipt(rgb, c)
    if math.hypot(ipt[1], ipt[2]) < 1e-7:
        return rgb
    z = clamp(ipt[0]/pq(p))
    gain = c['saturation_gain']*c['chroma_base']**(2*z-1)
    ipt[1], ipt[2] = ipt[1]*gain, ipt[2]*gain
    weights = circular_weights(math.atan2(ipt[2], ipt[1]), c['hue_centres'])
    gain = math.exp(sum(w*math.log(g) for w, g in zip(weights, c['secondary_gain'])))
    turn = sum(w*t for w, t in zip(weights, c['secondary_rotation']))
    ct, cp = ipt[1], ipt[2]
    ipt[1] = gain*(math.cos(turn)*ct-math.sin(turn)*cp)
    ipt[2] = gain*(math.sin(turn)*ct+math.cos(turn)*cp)
    return from_ipt(ipt, c)


def enhanced_objective(rgb_nits, peak_nits, headroom, scene, preset, primaries=BT2020):
    """Independent authored-response objective, in absolute linear nits."""
    if preset not in ['Natural', 'Signature'] or not math.isfinite(headroom) or not -.5 <= headroom <= .5:
        raise ValueError('bounded preset objective required')
    if not math.isfinite(scene) or not 0 <= scene <= 1:
        raise ValueError('bounded scene required')
    c=decode_controls({},peak_nits,primaries)
    if scene==0:
        return list(rgb_nits)
    y=sum(v*w for v,w in zip(rgb_nits,c['luma']))
    x=clamp(y/peak_nits)
    gate=clamp(y);gate=gate*gate*(3-2*gate)
    high=clamp((x-.25)/.75);high=high*high*(3-2*high)
    gain=scene*gate*(.04 if preset=='Signature' else .04*max(0,headroom)*high)
    mapped=y+gain*max(0,y)*(1-x)
    maximum=max(rgb_nits)
    if max(rgb_nits)-min(rgb_nits)>1e-12:
        room=clamp((peak_nits-maximum)/max(1e-6,peak_nits-y))
        mapped=y+(mapped-y)*room
    rgb=[v*mapped/y for v in rgb_nits] if y>0 else list(rgb_nits)
    if max(rgb)-min(rgb)<=1e-12:
        return rgb
    ipt=to_ipt(rgb,c)
    saturation=2**(scene*(64 if preset=='Signature' else 32*max(0,headroom))*clamp(1-maximum/peak_nits)/4096)
    ipt[1]*=saturation;ipt[2]*=saturation
    return from_ipt(ipt,c)
