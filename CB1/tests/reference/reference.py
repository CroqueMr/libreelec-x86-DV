# SPDX-License-Identifier: MIT
"""Independent scalar/image fixed-vector checks and numerical readiness gates.

This module is test-only. It never calls the CB renderer or uses `expected`
while evaluating inputs. Numerical readiness never approves runtime behavior.
"""
import argparse
import ctypes as C
import copy
import hashlib
import json
import math
import os
import struct
from pathlib import Path

REQUIRED_PIPELINE = {
    "CB1_PQ_RESCALE", "CB1_L1_LIBRARY_REPRESENTATION", "CB1_SOURCE_ELIGIBILITY",
    "CB1_TARGET_DESCRIPTOR", "CB1_HDR10_DESCRIPTOR", "CB1_RECONSTRUCTION_IMAGE",
    "CB1_SOURCE_SCENE_POLICY", "CB1_DISPLAY_MAP_IMAGE", "CB1_GAMUT_MAP_IMAGE",
    "CB1_ENHANCE_NATURAL_IMAGE", "CB1_ENHANCE_INTENSE_IMAGE", "CB1_OUTPUT_RESOLVE_IMAGE",
    "CB1_ENHANCE_NATURAL_POLICY", "CB1_ENHANCE_INTENSE_POLICY",
    "CB1_HDR10_LIFECYCLE",
    "CB1_TARGET_CAPABILITY",
    "CB1_DV_METADATA_PAIR", "CB1_DV_LIFECYCLE",
}
REQUIRED_IMAGE_STAGES = {
    "CB1_RECONSTRUCTION_IMAGE", "CB1_SOURCE_SCENE_POLICY", "CB1_DISPLAY_MAP_IMAGE",
    "CB1_GAMUT_MAP_IMAGE", "CB1_ENHANCE_NATURAL_IMAGE", "CB1_ENHANCE_INTENSE_IMAGE",
    "CB1_OUTPUT_RESOLVE_IMAGE", "CB1_ENHANCE_NATURAL_POLICY", "CB1_ENHANCE_INTENSE_POLICY",
    "CB1_DV_METADATA_PAIR",
}


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def comparison_valid(comparison):
    assert isinstance(comparison, dict), "comparison missing"
    for key in ("domain", "units", "reason"):
        assert isinstance(comparison.get(key), str) and comparison[key].strip(), key
    assert comparison.get("rule") in ("exact", "absolute"), "comparison rule"
    limit = comparison.get("limit")
    assert finite_number(limit) and limit >= 0, "comparison limit"
    assert comparison["rule"] != "exact" or limit == 0, "exact limit"
    for key, bound in comparison.get("component_limits", {}).items():
        assert isinstance(key, str) and finite_number(bound) and bound >= 0, "component limit"


def validate_contract(operations, cases, runtime=False):
    assert operations, "empty operation matrix"
    rows = {}
    for row in operations:
        identifier = row.get("id")
        assert isinstance(identifier, str) and identifier, "operation id"
        assert identifier not in rows, "duplicate operation"
        rows[identifier] = row
        assert type(row.get("essential")) is bool, "essential flag"
        assert row.get("status") in ("ready", "not_applied", "blocked"), "status"
        assert not (row["essential"] and row["status"] == "not_applied"), "essential not-applied"
        if row.get("creative"):
            disposition = row.get("disposition", {})
            assert set(disposition) == {"parsed", "applied", "transmitted", "not_applied"}, "disposition"
            assert all(type(value) is bool for value in disposition.values()), "disposition flags"
            assert disposition["applied"] != disposition["not_applied"], "creative applied ambiguity"
            if disposition["applied"]:
                assert "image" in row.get("coverage", []), "creative image coverage"
            assert row["status"] != "not_applied" or disposition["not_applied"], "creative scope"
        if row["status"] != "ready":
            assert row.get("gap"), "missing gap or scope reason"
            if runtime and row["essential"]:
                raise AssertionError("blocked essential operation: " + identifier)
            continue
        for key in ("domain", "units", "eligibility", "state", "authority"):
            assert isinstance(row.get(key), str) and row[key].strip(), key
        assert type(row.get("order")) is int and row["order"] >= 0, "order"
        assert isinstance(row.get("parameters"), dict) and row["parameters"], "parameters"
        assert row.get("coverage") and row.get("required_cases"), "coverage"
        if identifier in REQUIRED_IMAGE_STAGES:
            assert "image" in row["coverage"], "required image coverage: " + identifier

    seen = set()
    case_owners = {}
    covered = {identifier: set() for identifier in rows}
    for case in cases:
        assert isinstance(case, dict), "case record"
        for key in ("id", "operation", "mode", "generation", "target_class", "source"):
            assert isinstance(case.get(key), str) and case[key], key
        assert case["id"] not in seen, "duplicate case"
        seen.add(case["id"])
        case_owners[case["id"]] = case["operation"]
        assert case["operation"] in rows, "undefined operation"
        if case["operation"] in ("CB1_DV_METADATA_PAIR","CB1_DV_LIFECYCLE"):
            assert case["mode"] == "Enhanced DV", "DV mode"
        row = rows[case["operation"]]
        assert row["status"] == "ready", "case does not establish ready operation"
        assert case["source"] == row["authority"], "case authority mismatch"
        assert isinstance(case.get("input"), dict), "input"
        if case["input"].get("preset") and case["operation"].endswith("_IMAGE"):
            assert case["mode"] == "Enhanced DV", "mode/preset mismatch"
        assert isinstance(case.get("expected"), dict) and case["expected"], "expected"
        comparison_valid(case.get("comparison"))
        assert case["comparison"]["domain"] == row["domain"], "comparison domain"
        assert case.get("coverage"), "case coverage"
        if "image" in case["coverage"]:
            assert case["input"].get("rgb") and case["expected"].get("rgb"), "image pixels missing"
        covered[case["operation"]].update(case["coverage"])
    for identifier, row in rows.items():
        if row["status"] == "ready":
            assert all(case_owners.get(case) == identifier for case in row["required_cases"]), \
                "required case missing or wrong operation: " + identifier
            assert set(row["coverage"]) <= covered[identifier], "coverage missing: " + identifier


def validate_manifest(matrix, cases, runtime=False):
    rows = matrix["operations"]
    assert set(matrix["required_pipeline"]) == REQUIRED_PIPELINE, "pipeline declaration"
    essentials = {row["id"] for row in rows if row.get("essential")}
    assert essentials == REQUIRED_PIPELINE, "pipeline essential stage missing or unclassified"
    validate_contract(rows, cases, runtime=runtime)


def pq_encode(nits):
    assert finite_number(nits) and 0 <= nits <= 10000, "nits input"
    if nits == 0:
        return 0.0  # The pinned public rescale API special-cases exact zero.
    power = (nits / 10000.0) ** (2610.0 / 16384.0)
    return ((3424.0 / 4096.0 + 2413.0 / 128.0 * power) /
            (1.0 + 2392.0 / 128.0 * power)) ** (2523.0 / 32.0)


def pq_decode(pq):
    assert finite_number(pq) and 0 <= pq <= 1, "pq input"
    power = pq ** (32.0 / 2523.0)
    return 10000.0 * (max(power - 3424.0 / 4096.0, 0.0) /
                       (2413.0 / 128.0 - 2392.0 / 128.0 * power)) ** (16384.0 / 2610.0)


def dv_code(value):
    assert finite_number(value) and 0 <= value <= 1, "PQ statistic"
    return min(4095, math.floor(4096 * value + .5))


def dv_round_statistic(value):
    assert finite_number(value) and 0 <= value <= 1, "PQ statistic"
    return math.floor(value*100000+.5)/100000


def dv_statistics(pixels, size, active):
    """Own output analysis, never a replacement for absent source L1."""
    assert len(size) == 2 and all(type(v) is int and v > 0 for v in size), "raster size"
    w, h = size
    assert w <= 3840 and h <= 2160 and len(pixels) == w*h, "raster shape"
    assert all(len(p) == 3 and all(finite_number(v) and 0 <= v <= 1 for v in p)
               for p in pixels), "PQ raster"
    assert len(active) == 4 and all(type(v) is int for v in active), "active window"
    left, top, right, bottom = active
    assert 0 <= left < right <= w and 0 <= top < bottom <= h, "active window"
    samples = []
    for y in range(top, bottom, 2):
        for x in range(left, right, 2):
            group = [pixels[yy*w+xx] for yy in range(y,min(y+2,bottom))
                     for xx in range(x,min(x+2,right))]
            components = [math.fsum(pq_decode(p[c]) for p in group)/len(group)
                          for c in range(3)]
            samples.append(pq_encode(max(components)))
    raw = [min(samples), math.fsum(samples)/len(samples), max(samples)]
    rounded = [dv_round_statistic(v) for v in raw]
    return {"statistics":rounded, "l1":[dv_code(rounded[i]) for i in (0,2,1)],
            "groups":len(samples)}


def dv_active_window(inputs):
    """Positive lround source margins, identical to established CPU L5."""
    w, h = inputs["size"]
    if "source_size" not in inputs:
        return list(inputs.get("active", [0,0,w,h]))
    assert (w,h) == (3840,2160), "DV transport raster"
    sw, sh = inputs["source_size"]
    x,y,dw,dh = inputs["destination"]
    l,r,t,b = inputs.get("source_margins", [0,0,0,0])
    assert all(type(v) is int for v in (sw,sh,x,y,dw,dh,l,r,t,b)), "geometry integers"
    assert 0 < sw <= w and 0 < sh <= h and dw > 0 and dh > 0, "geometry dimensions"
    assert x >= 0 and y >= 0 and x+dw <= w and y+dh <= h, "geometry destination"
    assert not (x%2 or dw%2) and abs(dw*sh/sw-dh) <= 1.01, "geometry transport"
    assert 0 <= l < sw and 0 <= r < sw-l and 0 <= t < sh and 0 <= b < sh-t, "source margins"
    margins = [x+math.floor(l*dw/sw+.5), w-x-dw+math.floor(r*dw/sw+.5),
               y+math.floor(t*dh/sh+.5), h-y-dh+math.floor(b*dh/sh+.5)]
    active = [margins[0],margins[2],w-margins[1],h-margins[3]]
    assert active[0] < active[2] and active[1] < active[3], "empty active window"
    return active


def transformed_dv_output(inputs):
    identity = inputs["identity"]
    assert (len(identity) == 3 and all(type(v) is int and v >= 0 for v in identity)
            and identity[2] == inputs["revision"]), "metadata identity"
    assert inputs["generation"] in ("CM2.9","CM4"), "source generation"
    source = inputs["source"]
    assert l1_valid(source["l1"]), "essential source L1"
    assert source["reconstruction_valid"], "source reconstruction"
    assert inputs.get("output_levels",[1,5]) == [1,5], "legacy levels"
    peak = inputs["peak"]
    assert finite_number(peak) and 1e-6 < peak <= 10000, "nominal peak"
    assert inputs["gamut"] in ("BT709","P3-D65","BT2020"), "nominal gamut"
    assert inputs["panel"] in ("OLED","LCD"), "panel"
    if "source_identity" in inputs:
        assert inputs["source_identity"] == identity, "source identity"
    active = dv_active_window(inputs)
    original = inputs["rgb"]
    if "image_input" in inputs:
        image = inputs["image_input"]
        assert image["identity"] == identity and image["l1"] == source["l1"], "source identity/L1"
        assert image["peak"] == peak and image["gamut"] == inputs["gamut"], "image target policy"
        assert image["generation"] == inputs["generation"], "image generation"
        assert image.get("preset") in ("Natural","Intense"), "image preset"
        image = copy.deepcopy(image)
        image.pop("active",None)
        image.pop("overlays",None)
        image.pop("flip_y",None)
        original = evaluate_image({"operation":"CB1_OUTPUT_RESOLVE_IMAGE","input":image})["rgb"]
    analysis = dv_statistics(original,inputs["size"],active)
    w,h = inputs["size"]
    pixels = [list(p) if active[0] <= i%w < active[2] and active[1] <= i//w < active[3]
              else [0,0,0] for i,p in enumerate(original)]
    return {"rgb":pixels, **analysis, "identity":list(identity),
            "output_generation":"CB1_ETSI_LEGACY_LITERAL", "levels":[1,5],
            "source_pq":[0,dv_code(pq_encode(math.ceil(peak)))],
            "nominal_max_nits":math.ceil(peak), "nominal_gamut":inputs["gamut"],
            "container":"BT2020/PQ", "active":active,
            "light_levels":{"max_cll":0,"max_fall":0,"measured":False}}


def evaluate_dv_lifecycle(inputs):
    """Discrete future-API oracle, not another runtime transport."""
    pending = committed = cached = None
    slot = False
    retiring = False
    resolved = submitted = None
    snapshots = []
    for event in inputs["events"]:
        op = event["op"]
        status = "rejected"
        if op in ("cancel","reset"):
            pending = cached = resolved = submitted = None
            retiring = slot
            if op == "reset":
                committed = None
            status = "reset" if op == "reset" else "cancelled"
        elif op == "prepare":
            ident = event["identity"]
            valid = (len(ident) == 3 and all(type(v) is int and v >= 0 for v in ident)
                     and ident[2] == event["revision"]
                     and finite_number(event.get("pts",0))
                     and finite_number(event.get("el_pts",0)))
            if pending:
                pending = cached = resolved = submitted = None
                retiring = slot
            if not valid or not event.get("success",True):
                cached = None
                status = "failed"
            elif not event.get("capable",True):
                cached = None
                status = "unsupported"
            elif slot:
                status = "busy"
            else:
                pending = {"identity":list(ident),"ready":False,
                           "force_refresh":committed is None or ident[2] != committed[2]
                                            or ident[0] != committed[0]}
                slot = True
                status = "pending"
        elif op in ("poll","retire"):
            if pending and pending["ready"]:
                status = "ready"
            elif pending:
                status = "pending"
                if event.get("fence") == "signaled" and event.get("visible",True):
                    if event.get("identity",pending["identity"]) == pending["identity"]:
                        pending["ready"] = True
                        status = "ready"
                    else:
                        pending = cached = None
                        retiring = slot
                        status = "failed"
                elif event.get("fence") == "failed":
                    pending = cached = None
                    retiring = slot
                    status = "failed"
            else:
                status = "busy" if retiring else "idle"
                if retiring and event.get("fence") == "signaled":
                    slot = retiring = False
                    status = "idle"
        elif op == "resolve":
            if pending and pending["ready"] and event.get("success",True):
                resolved = event["surface"]
                submitted = None
                status = "resolved"
            elif pending and not event.get("success",True):
                pending = cached = resolved = None
                retiring = slot
                status = "failed"
        elif op == "submit":
            if pending and resolved and event["surface"] == resolved:
                submitted = resolved
                status = "submitted"
        elif op == "commit":
            if (pending and pending["ready"] and submitted and event["surface"] == submitted == resolved
                    and event["identity"] == pending["identity"] and event.get("success",True)):
                committed = list(pending["identity"])
                cached = list(committed)
                pending = resolved = submitted = None
                retiring = slot
                status = "committed"
            elif not event.get("success",True):
                pending = cached = resolved = submitted = None
                retiring = slot
                status = "failed"
        elif op == "pause":
            if cached == event["identity"] and event.get("available",True):
                status = "reused"
        else:
            assert False, "undefined DV lifecycle event"
        snapshots.append({"status":status,"pending":copy.deepcopy(pending),
                          "committed":copy.deepcopy(committed),"cached":copy.deepcopy(cached),
                          "storage_busy":slot})
    return {"snapshots":snapshots}


def l1_valid(blocks):
    if len(blocks) != 1 or not isinstance(blocks[0], dict):
        return False
    block = blocks[0]
    values = [block.get(key) for key in ("min", "avg", "max")]
    return (all(type(value) is int for value in values)
            and 0 <= values[0] <= values[1] <= values[2] <= 4095 and values[2] > 0)


def smoothstep(lo, hi, value):
    t = max(0.0, min(1.0, (value - lo) / (hi - lo)))
    return t * t * (3.0 - 2.0 * t)


def nominal_cube_projection(rgb, peak):
    """Own-policy common-neutral contraction, identity for the nominal cube."""
    assert len(rgb) == 3 and all(finite_number(v) for v in rgb), "finite target RGB"
    assert finite_number(peak) and 0 < peak <= 10000, "peak"
    if all(0 <= v <= peak for v in rgb):
        return list(rgb)
    anchor = min(peak,max(0,min(rgb)/2+max(rgb)/2))
    direction = [v-anchor for v in rgb]
    assert all(finite_number(v) for v in direction), "finite target RGB direction"
    ratios = [(peak-anchor)/v if v > 0 else -anchor/v if v < 0 else 1
              for v in direction]
    factor = min(1,*ratios)
    result = [anchor+factor*v for v in direction]
    # A limiting component is mathematically the exact boundary, not a
    # general channel clamp or a tolerance on the common-direction operation.
    for i,v in enumerate(direction):
        if v and ratios[i] == factor:
            result[i] = peak if v > 0 else 0
    assert all(finite_number(v) and 0 <= v <= peak for v in result), "projected target RGB"
    return result


def enhancement(inputs, intense):
    """Own-policy arithmetic in the already mapped nominal target RGB cube.

    scene_ratio is a decoded L1 hint ratio, not measured image CIE-Y/FALL.
    This pointwise reference cannot qualify reconstruction or the gamut stage.
    """
    peak, scene = inputs["peak"], inputs["scene_ratio"]
    assert finite_number(peak) and 0 < peak <= 10000, "peak"
    assert finite_number(scene) and 0 <= scene <= 1, "scene ratio"
    scene_mask = 1 - 0.5 * smoothstep(0.1, 0.5, scene)
    result = []
    for pixel in inputs["rgb"]:
        pixel = nominal_cube_projection(pixel,peak)
        normalized = [v / peak for v in pixel]
        maximum = max(normalized)
        shadow = smoothstep(0.01, 0.02, maximum)
        if maximum == 0 or shadow == 0:
            result.append(list(pixel))
            continue
        onset = (0.02, 0.25) if intense else (0.25, 0.75)
        local = shadow * smoothstep(*onset, maximum)
        k = (0.35 if intense else 0.20) * scene_mask
        expanded = maximum + k * local * maximum * (1 - maximum)
        rgb = [v * expanded / maximum for v in normalized]
        low, high = min(rgb), max(rgb)
        gray = (low + high) / 2
        chroma = (high - low) / 2
        if chroma == 0 and expanded == maximum:
            result.append(list(pixel))
            continue
        room = min(gray, 1 - gray)
        if chroma > 0 and room > 0:
            fraction = min(1.0, chroma / room)
            protection = 4 * fraction * (1 - fraction)
            strength = (0.08 if intense else 0.04) * shadow * scene_mask
            factor = min(1 + strength * protection, room / chroma)
            rgb = [gray + factor * (v - gray) for v in rgb]
        assert all(-1e-12 <= v <= 1 + 1e-12 for v in rgb), "bounded expansion"
        result.append([v * peak for v in rgb])
    return {"rgb": result}


def pack_ipt(ipt):
    """Source-defined UNORM16 conversion, including its asymmetric bias."""
    result = []
    for i, value in enumerate(ipt):
        product = C.c_float(C.c_float(value).value * 65535).value
        biased = C.c_float(product + (32767 if i else 0)).value
        packed = math.floor(biased + 0.5)
        assert 0 <= packed <= 65535, "UNORM16 overflow"
        result.append(packed)
    return result


def unpack_ipt(packed):
    # Exact rational interpretation; GPU subtraction roundoff is a later test.
    return [packed[0] / 65535, (packed[1] - 32768) / 65535,
            (packed[2] - 32768) / 65535]


def lookup_lut(lattice, sizes, coordinates):
    """Endpoint-aligned trilinear ICh lookup with clamp-to-edge addressing."""
    axes = []
    for size, coord in zip(sizes, coordinates):
        position = max(0.0, min(1.0, coord)) * (size - 1)
        low = math.floor(position)
        axes.append((low, min(low + 1, size - 1), position - low))
    output = [0.0, 0.0, 0.0]
    for hside in (0, 1):
        for cside in (0, 1):
            for iside in (0, 1):
                sides = (iside, cside, hside)
                indices = [axis[side] for axis, side in zip(axes, sides)]
                weight = math.prod(axis[2] if side else 1 - axis[2]
                                   for axis, side in zip(axes, sides))
                index = (indices[2] * sizes[1] + indices[1]) * sizes[0] + indices[0]
                for channel, value in enumerate(lattice[index]):
                    output[channel] += weight * value
    return output


class XY(C.Structure):
    _fields_ = [("x", C.c_float), ("y", C.c_float)]


class Primaries(C.Structure):
    _fields_ = [(name, XY) for name in ("red", "green", "blue", "white")]


class Matrix(C.Structure):
    _fields_ = [("m", (C.c_float * 3) * 3)]


class Bezier(C.Structure):
    _fields_ = [(name, C.c_float) for name in ("target_luma", "knee_x", "knee_y")] + [
        ("anchors", C.c_float * 15), ("num_anchors", C.c_uint8)]


class HDR(C.Structure):
    _fields_ = [("prim", Primaries)] + [(name, C.c_float) for name in (
        "min_luma", "max_luma", "max_cll", "max_fall")] + [
        ("scene_max", C.c_float * 3), ("scene_avg", C.c_float), ("ootf", Bezier),
        ("max_pq_y", C.c_float), ("avg_pq_y", C.c_float)]


class ToneConstants(C.Structure):
    _fields_ = [(name, C.c_float) for name in (
        "knee_adaptation", "knee_minimum", "knee_maximum", "knee_default", "knee_offset",
        "slope_tuning", "slope_offset", "spline_contrast", "reinhard_contrast", "linear_knee", "exposure")]


class ToneParams(C.Structure):
    _fields_ = [("function", C.c_void_p), ("constants", ToneConstants),
                ("input_scaling", C.c_int), ("output_scaling", C.c_int), ("lut_size", C.c_size_t)] + [
        (name, C.c_float) for name in ("input_min", "input_max", "input_avg", "output_min", "output_max")] + [
        ("hdr", HDR), ("param", C.c_float)]


class GamutConstants(C.Structure):
    _fields_ = [(name, C.c_float) for name in (
        "perceptual_deadzone", "perceptual_strength", "colorimetric_gamma", "softclip_knee", "softclip_desat")]


class GamutParams(C.Structure):
    _fields_ = [("function", C.c_void_p), ("input_gamut", Primaries), ("output_gamut", Primaries),
               ("min_luma", C.c_float), ("max_luma", C.c_float), ("constants", GamutConstants)] + [
        (name, C.c_int) for name in ("lut_size_I", "lut_size_C", "lut_size_h", "lut_stride")] + [
        ("chroma_margin", C.c_float)]


def characterized_library(path):
    """Load an exact recorded binary, never an arbitrary version-compatible ABI.

    The Task 7 build adds default-off shader/storage options; these public CPU
    primitives, ABI, equations and all frozen expected values remain unchanged.
    Task 8A registers its fresh inverse-helper build identity only; this does
    not qualify its numerical behavior, which still requires the frozen gates.
    """
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    assert digest in {
        "111c6084a8e509f27e2c586e33568c82bf28c778c44b2740230e9bb1571f65af",
        "54d869abe8abc63c7e200ade4a3debc539de148152ff6fc9b0c28a1a66e6d5fa",
        "a48836a77309bc857a27da0e0d28f2bfc088053cf0b42563a1498f49d364fb8f",
        "b04935c9a1b547361a83d34c51e2505da1a0ae6a19c2ad9f18845110f332b6c6",
    }, "library binary receipt"
    assert C.sizeof(C.c_void_p) == 8, "64-bit ABI required"
    assert (C.sizeof(HDR), C.sizeof(ToneParams), C.sizeof(GamutParams)) == (148, 248, 120), "public header ABI"
    lib = C.CDLL(path)
    lib.pl_version.restype = C.c_char_p
    assert lib.pl_version().decode() == "v7.372.0", "library version"
    lib.pl_hdr_rescale.argtypes = [C.c_int, C.c_int, C.c_float]
    lib.pl_hdr_rescale.restype = C.c_float
    lib.pl_raw_primaries_get.argtypes = [C.c_int]
    lib.pl_raw_primaries_get.restype = C.POINTER(Primaries)
    lib.pl_find_tone_map_function.argtypes = [C.c_char_p]
    lib.pl_find_tone_map_function.restype = C.c_void_p
    lib.pl_find_gamut_map_function.argtypes = [C.c_char_p]
    lib.pl_find_gamut_map_function.restype = C.c_void_p
    lib.pl_tone_map_generate.argtypes = [C.POINTER(C.c_float), C.POINTER(ToneParams)]
    lib.pl_tone_map_sample.argtypes = [C.c_float, C.POINTER(ToneParams)]
    lib.pl_tone_map_sample.restype = C.c_float
    lib.pl_gamut_map_generate.argtypes = [C.POINTER(C.c_float), C.POINTER(GamutParams)]
    lib.pl_gamut_map_sample.argtypes = [C.POINTER(C.c_float), C.POINTER(GamutParams)]
    for name in ("pl_tone_map_generate", "pl_gamut_map_generate", "pl_gamut_map_sample"):
        getattr(lib, name).restype = None
    for name in ("pl_ipt_rgb2lms", "pl_ipt_lms2rgb"):
        function = getattr(lib, name)
        function.argtypes = [C.POINTER(Primaries)]
        function.restype = Matrix
    return lib


def float_bits(value):
    return struct.unpack("<I", struct.pack("<f", value))[0]


def evaluate_public_pq(lib, inputs):
    """External pinned-binary authority, not independent proof of library math."""
    value = inputs["value"]
    assert inputs["from"] in (2, 3) and inputs["to"] in (2, 3), "public PQ scaling"
    maximum = 10000 if inputs["from"] == 2 else 1
    assert finite_number(value) and 0 <= value <= maximum, "public PQ input"
    output = lib.pl_hdr_rescale(inputs["from"], inputs["to"], value)
    return {"value": output, "bits": float_bits(output)}


def characterize_library(path):
    """Upstream black/white and 1:1 spline characterization, not a CB image."""
    lib = characterized_library(path)
    peak = pq_encode(1500)
    source = lib.pl_raw_primaries_get(6).contents  # locked enum BT2020
    samples = []
    for name, enum in (("BT709", 3), ("P3-D65", 12), ("BT2020", 6)):
        params = GamutParams(function=lib.pl_find_gamut_map_function(b"perceptual"),
                             input_gamut=source, output_gamut=lib.pl_raw_primaries_get(enum).contents,
                             min_luma=0, max_luma=peak,
                             constants=GamutConstants(0.3, 0.8, 1.8, 0.7, 0.35))
        black, white = (C.c_float * 3)(0, 0, 0), (C.c_float * 3)(peak, 0, 0)
        lib.pl_gamut_map_sample(black, C.byref(params))
        lib.pl_gamut_map_sample(white, C.byref(params))
        samples.append({"gamut": name, "black": list(black), "white": list(white)})
    tone = ToneParams(function=lib.pl_find_tone_map_function(b"spline"),
                      constants=ToneConstants(0.4, 0.1, 0.8, 0.4, 1, 1.5, 0.2, 0.5, 0.5, 0.3, 1),
                      input_scaling=3, output_scaling=3, lut_size=256,
                      input_min=0, input_max=peak, output_min=0, output_max=peak)
    lut = (C.c_float * 256)()
    lib.pl_tone_map_generate(lut, C.byref(tone))
    # The source upstream acceptance rule is fixed before evaluating values.
    for index in (0, 1, 64, 128, 255):
        assert abs(lut[index] - peak * index / 255) <= 1e-5, "upstream neutral spline characterization"
    return {"version": lib.pl_version().decode(), "peak_pq": peak, "samples": samples,
            "tone_identity": [lut[index] for index in (0, 1, 64, 128, 255)]}


def characterize_lut(path):
    """Bounded source-defined LUT probe. It does not render reconstructed RGB."""
    lib = characterized_library(path)
    sizes = (48, 32, 256)
    count = math.prod(sizes)
    output = []
    for name, enum in (("BT709", 3), ("P3-D65", 12), ("BT2020", 6)):
        params = GamutParams(function=lib.pl_find_gamut_map_function(b"perceptual"),
                             input_gamut=lib.pl_raw_primaries_get(6).contents,
                             output_gamut=lib.pl_raw_primaries_get(enum).contents,
                             min_luma=0, max_luma=pq_encode(1500),
                             constants=GamutConstants(0.3, 0.8, 1.8, 0.7, 0.35),
                             lut_size_I=48, lut_size_C=32, lut_size_h=256, lut_stride=3)
        raw = (C.c_float * (count * 3))()
        lib.pl_gamut_map_generate(raw, C.byref(params))
        # Only the sampled eight corners are packed, no new image framework.
        class Lattice:
            def __getitem__(self, index):
                return unpack_ipt(pack_ipt(raw[index * 3:index * 3 + 3]))
        points = [[0, 0, 0.5], [0.5, 0, 0.5], [0.6, 0.3, 0.25], [1, 0, 0.5]]
        output.append({"gamut": name, "float_lut_sha256": hashlib.sha256(bytes(raw)).hexdigest(),
                       "ipt_samples": [lookup_lut(Lattice(), sizes, point) for point in points]})
    return {"sizes": sizes, "packing_bias": 32767, "shader_subtraction": 32768,
            "authority": "external pinned-library characterization; not complete image oracle",
            "targets": output}


def evaluate(case):
    """Evaluate only inputs; fixed expected values are never read here."""
    operation = case["operation"]
    inputs = case["input"]
    if operation == "CB1_DV_METADATA_PAIR":
        return transformed_dv_output(inputs)
    if operation == "CB1_DV_LIFECYCLE":
        return evaluate_dv_lifecycle(inputs)
    if operation == "CB1_HDR10_LIFECYCLE":
        return evaluate_lifecycle(inputs)
    if operation == "CB1_TARGET_CAPABILITY":
        return target_capability(inputs["peak"])
    if operation in REQUIRED_IMAGE_STAGES - {"CB1_ENHANCE_NATURAL_POLICY", "CB1_ENHANCE_INTENSE_POLICY"}:
        return evaluate_image(case)
    if operation in ("CB1_ENHANCE_NATURAL_POLICY", "CB1_ENHANCE_INTENSE_POLICY"):
        return enhancement(inputs, operation == "CB1_ENHANCE_INTENSE_POLICY")
    if operation == "CB1_PQ_RESCALE":
        if "nits" in inputs:
            return {"pq": pq_encode(inputs["nits"])}
        return {"nits": pq_decode(inputs["pq"])}
    if operation in ("CB1_L1_LIBRARY_REPRESENTATION", "CB1_L1_IDEAL_DIVISION"):
        assert l1_valid(inputs["l1"]), "invalid L1"
        block = inputs["l1"][0]
        values = [block["max"] / 4095.0, block["avg"] / 4095.0]
        if operation == "CB1_L1_IDEAL_DIVISION":
            return {"max_pq_y": values[0], "avg_pq_y": values[1]}
        # All 12-bit integer operands and the divisor are exact binary32.
        # Division followed by float rounding matches the source float fields.
        values = [C.c_float(value).value for value in values]
        return {"max_pq_y": values[0], "avg_pq_y": values[1],
                "bits": [float_bits(value) for value in values]}
    if operation == "CB1_SOURCE_ELIGIBILITY":
        return {"eligible": bool(inputs["metadata_valid"] and inputs["reconstruction_valid"]
                                 and l1_valid(inputs["l1"]))}
    if operation in ("CB1_TARGET_DESCRIPTOR", "CB1_HDR10_DESCRIPTOR"):
        peak, panel, gamut = inputs["peak"], inputs["panel"], inputs["gamut"]
        assert finite_number(peak) and 0 < peak <= 10000, "target peak"
        assert panel in ("OLED", "LCD"), "panel"
        assert gamut in ("BT709", "P3-D65", "BT2020"), "gamut"
        if operation == "CB1_TARGET_DESCRIPTOR":
            return {"peak_nits": peak, "nominal_black_nits": 1e-6, "gamut": gamut,
                    "panel": panel, "measured": False}
        return {"container": "BT2020", "transfer": "PQ", "nominal_gamut": gamut,
                "max_luminance": math.ceil(peak), "min_luminance": 0,
                "max_cll": 0, "max_fall": 0, "measured": False}
    raise AssertionError("undefined evaluator operation: " + operation)


def check(case, actual):
    """Compare candidate values to independently frozen expectations."""
    comparison = case["comparison"]
    comparison_valid(comparison)
    expected = case["expected"]
    assert isinstance(actual, dict) and set(actual) == set(expected), "output keys"
    def compare(wanted, got, key):
        if isinstance(wanted, dict):
            assert isinstance(got,dict) and set(got) == set(wanted), key + " keys"
            for name,value in wanted.items():
                compare(value,got[name],key+"."+name)
            return
        if isinstance(wanted, list):
            assert isinstance(got, list) and len(wanted) == len(got), key + " shape"
            for index, (left, right) in enumerate(zip(wanted, got)):
                compare(left, right, f"{key}[{index}]")
            return
        if type(wanted) in (int, float):
            if key == "bits" or key.startswith("bits["):
                assert type(got) is int and got == wanted, key + " exact bits comparison failed"
                return
            assert finite_number(wanted) and finite_number(got), key + " nonfinite"
            root_key = key.split("[",1)[0]
            limit = comparison.get("component_limits", {}).get(root_key, comparison["limit"])
            assert abs(got - wanted) <= limit, key + " comparison failed"
        else:
            assert type(got) is type(wanted) and got == wanted, key + " exact comparison failed"
    for key, wanted in expected.items():
        compare(wanted, actual[key], key)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", action="store_true", help="require all essential image operations ready")
    parser.add_argument("--characterize", action="store_true", help="inspect explicitly configured pinned library")
    parser.add_argument("--characterize-lut", action="store_true", help="probe pinned ICh LUT packing/interpolation")
    args = parser.parse_args()
    if args.characterize:
        print(json.dumps(characterize_library(os.environ["CB1_REFERENCE_LIBRARY"]), indent=2))
        return
    if args.characterize_lut:
        print(json.dumps(characterize_lut(os.environ["CB1_REFERENCE_LIBRARY"]), indent=2))
        return
    root = Path(__file__).resolve().parent
    matrix = json.loads((root / "operation-matrix.json").read_text())
    data = json.loads((root / "vectors.json").read_text())
    vectors = (data["cases"] + data["image_cases"] + data["lifecycle_cases"]
               + data["capability_cases"] + data["dv_cases"] + data["dv_lifecycle_cases"])
    validate_manifest(matrix, vectors, runtime=args.runtime)
    if args.runtime:
        assert os.environ.get("CB1_REFERENCE_LIBRARY"), "explicit pinned image library required"
    skipped = 0
    for case in vectors:
        if (case in data["image_cases"] or "image_input" in case["input"]) and not os.environ.get("CB1_REFERENCE_LIBRARY"):
            skipped += 1
            continue
        check(case, evaluate(case))
        if case["operation"] == "CB1_OUTPUT_RESOLVE_IMAGE":
            check_image_integrity(case,evaluate(case))
    print(f"{len(vectors)-skipped} frozen vectors passed; {skipped} explicitly skipped pinned-library images; no runtime approval")


# Keep one scalar/ABI owner. This focused helper contains image/state arithmetic.
from image_reference import (evaluate_image, reconstruct_image, target_capability,
                             evaluate_lifecycle, scale_image, check_image_integrity)

if __name__ == "__main__":
    main()
