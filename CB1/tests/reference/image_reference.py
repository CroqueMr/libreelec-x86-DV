# SPDX-License-Identifier: LGPL-2.1-or-later
# Source-equation composition informed by libplacebo, copyright its authors.
# Independently expressed test arithmetic; public CPU functions retain their
# upstream implementation/license. See LICENSES/LGPL-2.1.txt.
"""Offline source-equation image composition. No CB renderer is called.

Public CPU operators characterize their own pinned implementation. Matrices,
shader equations and policy composition are evaluated independently in double.
Frozen expectations come from the separate compiled evidence control.
"""
import ctypes as C
import functools
import math
import os
import sys

R = sys.modules.get("reference", sys.modules["__main__"])

HPE_INVERSE = [[3.06441879, -2.16597676, 0.10155818],
               [-0.65612108, 1.78554118, -0.12943749],
               [0.01736321, -0.04725154, 1.03004253]]
IDENTITY = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
GAMUT_ENUMS = {"BT709": 3, "P3-D65": 12, "BT2020": 6}

class FilterConfig(C.Structure):
    _fields_ = [("name", C.c_void_p), ("description", C.c_void_p),
                ("allowed", C.c_int), ("recommended", C.c_int),
                ("kernel", C.c_void_p), ("window", C.c_void_p),
                ("radius", C.c_float), ("params", C.c_float*2), ("wparams", C.c_float*2),
                ("clamp", C.c_float), ("blur", C.c_float), ("taper", C.c_float),
                ("polar", C.c_bool), ("antiring", C.c_float)]

class FilterParams(C.Structure):
    _fields_ = [("config", FilterConfig), ("lut_entries", C.c_int), ("cutoff", C.c_float),
                ("max_row_size", C.c_int), ("row_stride_align", C.c_int), ("filter_scale", C.c_float)]

class Filter(C.Structure):
    _fields_ = [("params", FilterParams), ("radius", C.c_float), ("radius_zero", C.c_float),
                ("weights", C.POINTER(C.c_float)), ("row_size", C.c_int),
                ("insufficient", C.c_bool), ("row_stride", C.c_int), ("radius_cutoff", C.c_float)]


def matvec(matrix, vector):
    return [sum(a*b for a, b in zip(row, vector)) for row in matrix]


def target_capability(peak):
    assert R.finite_number(peak) and 0 < peak <= 10000, "valid profile required"
    represented = C.c_float(peak).value
    bound = max(2.0**-150, 2.0**(math.frexp(peak)[1] - 25))
    supported = math.isfinite(represented) and peak > 1e-6 and represented > C.c_float(1e-6).value
    return {"requested": peak, "represented": represented, "rounding_bound": bound,
            "supported": supported,
            "reason": "supported" if supported else "target-unrepresentable"}


def reshape(signal, component):
    pivots = component.get("pivots", [0, 1])
    assert 2 <= len(pivots) <= 9 and all(a < b for a, b in zip(pivots, pivots[1:])), "reshape pivots"
    channel = component.get("channel", 0)
    index = sum(signal[channel] >= p for p in pivots[1:-1])
    segment = component.get("segments", [{"poly": [0, 1, 0]}])[index]
    if "poly" in segment:
        a, b, c = segment["poly"]
        value = (c*signal[channel] + b)*signal[channel] + a
    else:
        coefficients = segment["mmr"]
        assert 1 <= len(coefficients) <= 3, "MMR order"
        x, y, z = signal
        monomials = [x, y, z, x*y, x*z, y*z, x*y*z]
        value = segment.get("constant", 0)
        for order, weights in enumerate(coefficients, 1):
            assert len(weights) == 7, "MMR coefficients"
            value += sum(w*m**order for w, m in zip(weights, monomials))
    return max(pivots[0], min(pivots[-1], value))


def reconstruct_image(inputs):
    identity = inputs["identity"]
    assert identity == inputs["rpu_identity"], "RPU pair"
    assert inputs.get("metadata_valid", True), "invalid reconstruction metadata"
    fel = inputs.get("fel", False)
    if fel:
        assert inputs.get("el") and identity == inputs.get("el_identity"), "FEL pair"
        assert len(inputs["el"]) == len(inputs["rgb"]), "EL raster pairing"
    bits, denom = inputs.get("el_bits", 10), inputs.get("denom", 12)
    assert 8 <= bits <= 16 and 0 <= denom <= 32, "NLQ coding"
    signals, pixels = [], []
    components = inputs.get("reshape", [{"channel": c} for c in range(3)])
    assert len(components) == 3, "reshape components"
    for index, pixel in enumerate(inputs["rgb"]):
        assert len(pixel) == 3 and all(R.finite_number(v) for v in pixel), "source pixels"
        sig = [max(0, min(1, v)) for v in pixel]
        signal = [reshape(sig, comp) for comp in components]
        if fel:
            for channel in range(3):
                code = inputs["el"][index][channel]
                assert R.finite_number(code) and 0 <= code <= 2**bits - 1, "EL code"
                residual = code - inputs["offset"][channel]
                # Independent LINEAR_DZ code equation, not folded shader math.
                if residual:
                    signal[channel] += math.copysign(
                        ((abs(residual) - 0.5)*inputs["slope"][channel] +
                         inputs["threshold"][channel]) / 2**denom, residual)
        signals.append(signal)
        decoded = matvec(inputs.get("ycc", IDENTITY),
                         [v-o for v, o in zip(signal, inputs.get("ycc_offset", [0]*3))])
        lms = [R.pq_decode(max(0, min(1, v))) for v in decoded]
        pixels.append(matvec(HPE_INVERSE, matvec(inputs.get("linear", IDENTITY), lms)))
    return {"rgb": pixels, "signal": signals}


@functools.lru_cache(maxsize=1)
def library():
    assert os.environ.get("CB1_REFERENCE_LIBRARY"), "explicit pinned image library required"
    lib = R.characterized_library(os.environ["CB1_REFERENCE_LIBRARY"])
    for name, params in (("pl_tone_map_params_noop", R.ToneParams),
                         ("pl_gamut_map_params_noop", R.GamutParams)):
        getattr(lib, name).argtypes = [C.POINTER(params)]
        getattr(lib, name).restype = C.c_bool
    lib.pl_get_rgb2xyz_matrix.argtypes = [C.POINTER(R.Primaries)]
    lib.pl_get_rgb2xyz_matrix.restype = R.Matrix
    lib.pl_get_xyz2rgb_matrix.argtypes = [C.POINTER(R.Primaries)]
    lib.pl_get_xyz2rgb_matrix.restype = R.Matrix
    assert (C.sizeof(FilterConfig), C.sizeof(FilterParams), C.sizeof(Filter)) == (80,104,136), "filter ABI"
    lib.pl_filter_generate.argtypes = [C.c_void_p, C.POINTER(FilterParams)]
    lib.pl_filter_generate.restype = C.POINTER(Filter)
    lib.pl_filter_free.argtypes = [C.POINTER(C.POINTER(Filter))]
    return lib


def public_pq(value, decode=False):
    return library().pl_hdr_rescale(3 if decode else 2, 2 if decode else 3, value)


def source_policy(inputs):
    assert R.l1_valid(inputs.get("l1", [])), "one usable L1 required"
    assert inputs.get("metadata_valid", True), "invalid metadata"
    minimum, maximum = inputs["source_min_pq"], inputs["source_max_pq"]
    assert type(minimum) is int and type(maximum) is int and 0 <= minimum < maximum <= 4095, "source mastering codes"
    l1 = inputs["l1"][0]
    max_hint, avg_hint = [C.c_float(l1[k]/4095).value for k in ("max", "avg")]
    min_nits, max_nits = [public_pq(C.c_float(v/4095).value, True) for v in (minimum, maximum)]
    l6 = inputs.get("l6", [])
    assert len(l6) <= 1, "duplicate L6"
    origin = "RPU-source-PQ"
    if l6:
        assert 0 < l6[0]["max"] <= 10000 and 0 <= l6[0]["min"] < l6[0]["max"], "invalid L6"
        min_nits, max_nits = l6[0]["min"], l6[0]["max"]
        origin = "RPU-L6"
    hint_peak, hint_avg = public_pq(max_hint, True), public_pq(avg_hint, True)
    return {"master_min": min_nits, "master_max": max_nits, "max_hint_pq": max_hint,
            "avg_hint_pq": avg_hint, "scene_ratio": hint_avg/hint_peak,
            "origin": origin, "generation": inputs.get("generation", "CM2.9")}


@functools.lru_cache(maxsize=32)
def operators(peak, gamut, min_nits, max_hint, avg_hint):
    lib = library()
    target = target_capability(peak)
    assert target["supported"], "target-unrepresentable"
    target_pq = public_pq(target["represented"])
    sentinel = public_pq(1e-6)
    assert target_pq > sentinel, "target-unrepresentable PQ range"
    input_min = public_pq(min_nits)
    if input_min <= sentinel:
        input_min = 0
    tone = R.ToneParams(function=lib.pl_find_tone_map_function(b"spline"),
                        constants=R.ToneConstants(0.4, 0.1, 0.8, 0.4, 1, 1.5, 0.2, 0.5, 0.5, 0.3, 1),
                        input_scaling=3, output_scaling=3, lut_size=256,
                        input_min=input_min, input_max=max(max_hint, target_pq),
                        input_avg=avg_hint, output_min=0, output_max=target_pq)
    source = lib.pl_raw_primaries_get(6).contents
    dest = lib.pl_raw_primaries_get(GAMUT_ENUMS[gamut]).contents
    gamut_params = R.GamutParams(function=lib.pl_find_gamut_map_function(b"perceptual"),
                                 input_gamut=source, output_gamut=dest, min_luma=0, max_luma=target_pq,
                                 constants=R.GamutConstants(0.3, 0.8, 1.8, 0.7, 0.35),
                                 lut_size_I=48, lut_size_C=32, lut_size_h=256, lut_stride=3)
    tone_lut = (C.c_float*256)()
    lib.pl_tone_map_generate(tone_lut, C.byref(tone))
    tone_active = not lib.pl_tone_map_params_noop(C.byref(tone))
    gamut_active = not lib.pl_gamut_map_params_noop(C.byref(gamut_params))
    raw = (C.c_float*(48*32*256*3))() if gamut_active else None
    if raw is not None:
        lib.pl_gamut_map_generate(raw, C.byref(gamut_params))
    return (tone, tone_lut, raw, tone_active, gamut_active,
            lib.pl_ipt_rgb2lms(C.byref(source)), lib.pl_ipt_lms2rgb(C.byref(dest)))


def matrix_rows(matrix):
    return [list(row) for row in matrix.m]


def tone_lookup(lut, tone, intensity):
    pos = max(0, min(1, (intensity-tone.input_min)/(tone.input_max-tone.input_min)))*255
    index = min(254, math.floor(pos))
    return lut[index] + (pos-index)*(lut[index+1]-lut[index])


def mapper_pq_encode(nits):
    """Retained C/source mapper forward equation, finite extended domain.

    This is not the standalone bounded scalar PQ API. Keep its existing
    negative guard and reference exact-zero convention, but no upper cap.
    """
    assert R.finite_number(nits), "finite mapper nits"
    if nits <= 0:
        return 0.0
    p = (nits/10000)**(2610/16384)
    return ((3424/4096+2413/128*p)/(1+2392/128*p))**(2523/32)


def mapper_pq_decode(pq):
    """Negative-only inverse mapper equation below its finite-domain pole."""
    assert R.finite_number(pq), "finite mapper PQ"
    if pq <= 0:
        return 0.0
    p = pq**(32/2523)
    denominator = 2413/128-2392/128*p
    assert denominator > 0, "mapper PQ inverse pole/domain"
    return 10000*(max(0,p-3424/4096)/denominator)**(16384/2610)


def map_image(pixels, inputs, policy):
    tone, lut, raw, tone_active, gamut_active, to_lms, from_lms = operators(
        inputs["peak"], inputs["gamut"], policy["master_min"],
        policy["max_hint_pq"], policy["avg_hint_pq"])
    lib = library()
    lms2ipt = matrix_rows(R.Matrix.in_dll(lib, "pl_ipt_lms2ipt"))
    ipt2lms = matrix_rows(R.Matrix.in_dll(lib, "pl_ipt_ipt2lms"))
    class Lattice:
        def __getitem__(self, index):
            return R.unpack_ipt(R.pack_ipt(raw[index*3:index*3+3]))
    mapped, toned = [], []
    for pixel in pixels:
        if max(abs(v) for v in pixel) == 0:
            toned.append([0.0]*3)
            mapped.append([0.0]*3)
            continue
        if not tone_active and not gamut_active:
            toned.append(list(pixel))
            mapped.append(list(pixel))
            continue
        lms = matvec(matrix_rows(to_lms), pixel)
        ipt = matvec(lms2ipt, [mapper_pq_encode(v) for v in lms])
        original = ipt[0]
        if tone_active:
            ipt[0] = tone_lookup(lut, tone, original)
            hull = lambda v: ((v-6)*v+9)*v
            factor = min(original/ipt[0], hull(ipt[0])/hull(original)) if original and ipt[0] else 0
            ipt[1:] = [v*factor for v in ipt[1:]]
        toned.append(matvec(matrix_rows(from_lms),
                            [mapper_pq_decode(v) for v in matvec(ipt2lms, ipt)]))
        if gamut_active:
            coords = [ipt[0]/tone.output_max, 2*math.hypot(*ipt[1:]),
                      math.atan2(ipt[2], ipt[1])/(2*math.pi)+0.5]
            ipt = R.lookup_lut(Lattice(), (48, 32, 256), coords)
        rgb = matvec(matrix_rows(from_lms),
                     [mapper_pq_decode(v) for v in matvec(ipt2lms, ipt)])
        mapped.append(rgb)
    return toned, mapped


def container_image(pixels, gamut):
    if gamut == "BT2020":
        return [list(pixel) for pixel in pixels]
    lib = library()
    source = lib.pl_raw_primaries_get(GAMUT_ENUMS[gamut])
    target = lib.pl_raw_primaries_get(6)
    to_xyz = matrix_rows(lib.pl_get_rgb2xyz_matrix(source))
    from_xyz = matrix_rows(lib.pl_get_xyz2rgb_matrix(target))
    return [matvec(from_xyz, matvec(to_xyz, pixel)) for pixel in pixels]


@functools.lru_cache(maxsize=16)
def scaler_weights(ratio, down):
    lib = library()
    cfg = FilterConfig.in_dll(lib, "pl_filter_hermite" if down else "pl_filter_lanczos")
    cfg = FilterConfig.from_buffer_copy(cfg)
    cfg.blur = max(1, 1/ratio)
    params = FilterParams(config=cfg, lut_entries=256, row_stride_align=4)
    generated = lib.pl_filter_generate(None, C.byref(params))
    assert generated and not generated.contents.insufficient, "scaler generation"
    size, stride = generated.contents.row_size, generated.contents.row_stride
    weights = list(generated.contents.weights[:256*stride])
    lib.pl_filter_free(C.byref(generated))
    return size, stride, weights


def scale_image(pixels, size, output_size):
    """Pinned separable LUT convolution, source stage before color mapping.

    Any shrinking axis selects linear Hermite for both passes. Otherwise PQ
    Lanczos is selected once; vertical precedes horizontal in that same domain.
    Endpoint phase alignment and explicit weight renormalization match source.
    """
    width, height = size
    out_width, out_height = output_size
    assert len(pixels) == width*height, "source raster"
    if width == out_width and height == out_height:
        return [list(pixel) for pixel in pixels]
    down = out_width < width or out_height < height
    if not down:
        # Shader delinearize differs from public rescale at exact zero and
        # clamps only negatives, not super-whites (colorspace.c:820,867).
        def encode(v):
            power = (max(0,v)/10000)**(2610/16384)
            return ((3424/4096+2413/128*power)/(1+2392/128*power))**(2523/32)
        pixels = [[encode(v) for v in pixel] for pixel in pixels]
    for axis, count in ((1,out_height), (0,out_width)):
        old_count = width if axis == 0 else height
        if old_count == count:
            continue
        ratio = count/old_count
        taps, stride, weights = scaler_weights(ratio, down)
        new_width, new_height = (count,height) if axis == 0 else (width,count)
        resized = []
        for y in range(new_height):
            for x in range(new_width):
                position = ((x if axis == 0 else y)+0.5)/ratio-0.5
                low = math.floor(position)
                phase = (position-low)*255
                row = min(254,math.floor(phase))
                ws = [weights[row*stride+k]+(phase-row)*(weights[(row+1)*stride+k]-weights[row*stride+k]) for k in range(taps)]
                rgb = [0.0]*3
                for k,w in enumerate(ws):
                    coord = max(0,min(old_count-1,low-(taps//2-1)+k))
                    sample = pixels[y*width+coord] if axis == 0 else pixels[coord*width+x]
                    rgb = [a+w*b for a,b in zip(rgb,sample)]
                rgb = [v/sum(ws) for v in rgb]
                resized.append(rgb)
        pixels, width, height = resized, new_width, new_height
    if down:
        return pixels
    # Linearize once after both passes, with the shader's negative-only clamp.
    def decode(v):
        power = max(0,v)**(32/2523)
        return 10000*(max(power-3424/4096,0)/(2413/128-2392/128*power))**(16384/2610)
    return [[decode(v) for v in pixel] for pixel in pixels]


def geometry_image(pixels, inputs):
    out_width, out_height = inputs.get("output_size", inputs["size"])
    assert len(pixels) == out_width*out_height, "mapped output raster"
    active = inputs.get("active", [0, 0, out_width, out_height])
    result = []
    for y in range(out_height):
        for x in range(out_width):
            if not (active[0] <= x+0.5 < active[2] and active[1] <= y+0.5 < active[3]):
                result.append([0.0]*3)
                continue
            result.append(list(pixels[y*out_width+x]))
    return result


def resolve_image(pixels, bits=10, limited=True):
    assert type(bits) is int and 10 <= bits <= 16, "resolve bits"
    scale = 2**(bits-8)
    offset, span = (16*scale, 219*scale) if limited else (0, 2**bits-1)
    return [[math.floor(offset+span*max(0,min(1,v))+0.5) for v in pixel] for pixel in pixels]


def evaluate_image(case):
    inputs, operation = case["input"], case["operation"]
    reconstructed = reconstruct_image(inputs)
    if operation == "CB1_RECONSTRUCTION_IMAGE":
        return reconstructed
    policy = source_policy(inputs)
    if operation == "CB1_SOURCE_SCENE_POLICY":
        return {"rgb": reconstructed["rgb"], **policy}
    source_pixels = scale_image(reconstructed["rgb"], inputs["size"], inputs.get("output_size", inputs["size"]))
    toned, mapped = map_image(source_pixels, inputs, policy)
    if operation == "CB1_DISPLAY_MAP_IMAGE":
        return {"rgb": toned}
    if operation == "CB1_GAMUT_MAP_IMAGE":
        return {"rgb": mapped}
    if inputs.get("preset"):
        mapped = R.enhancement({"rgb": mapped, "peak": inputs["peak"],
                                "scene_ratio": policy["scene_ratio"]}, inputs["preset"] == "Intense")["rgb"]
    if operation in ("CB1_ENHANCE_NATURAL_IMAGE", "CB1_ENHANCE_INTENSE_IMAGE"):
        return {"rgb": mapped}
    pq = [[R.pq_encode(max(0,min(10000,v))) for v in pixel]
          for pixel in container_image(mapped, inputs["gamut"])]
    pq = geometry_image(pq, inputs)
    # Supplied overlays are already BT2020/PQ. Policy never sees them.
    for overlay in inputs.get("overlays", []):
        index, alpha = overlay["index"], overlay["alpha"]
        pq[index] = [(1-alpha)*v+alpha*w for v,w in zip(pq[index], overlay["rgb"])]
    if inputs.get("flip_y", False):
        width, height = inputs.get("output_size",inputs["size"])
        pq = [pq[y*width+x] for y in range(height-1,-1,-1) for x in range(width)]
    return {"rgb": pq, "codes": resolve_image(pq, inputs.get("bits",10), inputs.get("limited",True))}


def check_image_integrity(case, actual):
    """Separate image acceptance from subjective enhancement preference.

    Runtime budget is one 16-bit normalized step, below 1/16 of a 12-bit
    output code. It is a fixed design requirement, not measured GPU evidence
    or a guaranteed bound on transcendental implementations.
    """
    wanted = case["expected"]["rgb"]
    got = actual["rgb"]
    code_want, code_got = case["expected"]["codes"], actual["codes"]
    assert all(isinstance(raster, list) for raster in (wanted,got,code_want,code_got)), "raster type"
    assert len(wanted) > 0 and len(got) == len(wanted) == len(code_want) == len(code_got), "image shape"
    for raster, numeric in ((wanted,R.finite_number),(got,R.finite_number),
                            (code_want,lambda v:type(v) is int),(code_got,lambda v:type(v) is int)):
        assert all(isinstance(pixel, list) and len(pixel) == 3 and all(numeric(v) for v in pixel)
                   for pixel in raster), "pixel shape/type"
    for index, (left,right) in enumerate(zip(wanted,got)):
        assert all(R.finite_number(v) and 0 <= v <= 1 for v in right), "finite PQ image"
        assert max(abs(a-b) for a,b in zip(left,right)) <= 1/65535, "GPU PQ budget"
        if left == [0,0,0]:
            assert right == [0,0,0], "exact black/border"
        # Direction in normalized PQ midpoint-opponent coordinates. This is
        # not a claim of perceptual or Dolby-native hue equivalence.
        a = [v-sum(left)/3 for v in left]
        b = [v-sum(right)/3 for v in right]
        ca,cb = math.sqrt(sum(v*v for v in a)),math.sqrt(sum(v*v for v in b))
        if ca >= 0.01:
            assert cb > 0, "lost chroma"
            angle = math.degrees(math.acos(max(-1,min(1,sum(x*y for x,y in zip(a,b))/(ca*cb)))))
            assert angle <= 0.1, "opponent hue acceptance"
        else:
            assert max(right)-min(right) <= max(left)-min(left)+2/65535, "neutral drift"
    # The first eight fixture pixels are the independently chosen gray/detail
    # ramp. Border/GUI fixtures have their own exact component expectations.
    if "active" not in case["input"] and len(got) >= 8:
        for i in range(1,8):
            assert max(got[i]) > max(got[i-1]), "lost ramp detail"
    for i,(left,right) in enumerate(zip(case["expected"]["codes"],actual["codes"])):
        for a,b in zip(left,right):
            assert type(b) is int and abs(a-b) <= 1, "resolve code budget"
        if wanted[i] == [0,0,0]:
            assert left == right, "black code"


def evaluate_lifecycle(inputs):
    """Value/availability contract, not a simulated GPU or player framework."""
    pending = committed = cached = surface = None
    retained = set()
    resolved = False
    snapshots = []
    for event in inputs["events"]:
        kind = event["op"]
        accepted = False
        if kind == "prepare":
            identity = event["identity"]
            pending, surface, resolved = None, None, False
            if (event.get("success", True) and identity[2] == event["revision"]
                    and R.finite_number(event.get("pts",0))
                    and R.finite_number(event.get("el_pts",0))):
                pending = list(identity)
                cached = list(identity)
                accepted = True
            else:
                cached = None
        elif kind == "pause":
            accepted = cached == event["identity"]
        elif kind == "resolve":
            if pending and event.get("success", True):
                surface = event["surface"]
                resolved = True
                accepted = True
            else:
                pending = cached = surface = None
                resolved = False
        elif kind == "submit":
            if pending and resolved and surface == event["surface"]:
                retained.add(surface)
                accepted = True
        elif kind == "present":
            if (pending == event["identity"] and resolved and surface == event["surface"]
                    and surface in retained and event.get("success", True)):
                committed = list(pending)
                pending = None
                resolved = False
                accepted = True
            elif event.get("success") is False:
                pending = cached = surface = None
                resolved = False
        elif kind == "release":
            retained.discard(event["surface"])
            accepted = True
        elif kind == "cancel":
            pending = cached = surface = None
            resolved = False
            accepted = True
        elif kind == "reset":
            pending = committed = cached = surface = None
            resolved = False
            accepted = True
        else:
            raise AssertionError("undefined lifecycle event")
        snapshots.append({"accepted": accepted, "pending": pending, "committed": committed,
                          "cached": cached, "surface": surface, "retained": sorted(retained)})
    return {"snapshots": snapshots}
