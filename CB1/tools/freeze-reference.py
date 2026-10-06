"""Freeze successful source-identified probes, or compare without updating them."""
import argparse
import hashlib
import json
import math
import os
import re
from pathlib import Path
import subprocess
import time

# Versioned contract of tests/frozen_reference.c, not an arbitrary JSON probe.
PROBE_CONTRACT = "native-basic-v1"
POSITIONS = [[1000,100],[1400,500],[1920,1080],[2500,1700],[2900,2100]]
INPUT_GEOMETRY = [64,64,840,0,2160,2160]
CATEGORIES = ["P5", "P7_MEL", "P7_FEL", "P8.1"]


def validate_probe(data):
    """Validate the fixed native/Basic packet and sampled-RGBA contract."""
    if not isinstance(data, dict) or not isinstance(data.get("renderer"), str) or not data["renderer"]:
        raise SystemExit("Invalid probe renderer identity")
    cases = data.get("cases")
    if not isinstance(cases, list) or len(cases) != len(CATEGORIES):
        raise SystemExit("Invalid probe category count")
    for category, case in zip(CATEGORIES, cases):
        if not isinstance(case, dict) or case.get("category") != category:
            raise SystemExit("Invalid probe category order")
        count, words = case.get("packet_count"), case.get("packet_words")
        if type(count) is not int or not 1 <= count <= 4:
            raise SystemExit("Invalid packet count")
        if not isinstance(words, list) or len(words) != count * 128:
            raise SystemExit("Invalid 128-word packet shape")
        if any(type(word) is not int or not 0 <= word <= 0xffffffff for word in words):
            raise SystemExit("Invalid integer packet word")
        for name in ("native_pq", "hdr10_basic_pq"):
            samples = case.get(name)
            if not isinstance(samples, list) or len(samples) != len(POSITIONS):
                raise SystemExit("Invalid five-sample output: " + name)
            for sample in samples:
                if not isinstance(sample, list) or len(sample) != 4:
                    raise SystemExit("Invalid RGBA sample: " + name)
                if any(type(value) not in (int, float) or not math.isfinite(value) for value in sample):
                    raise SystemExit("Nonfinite or nonnumeric PQ sample: " + name)


here = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--binary", required=True)
parser.add_argument("--source-commit", required=True)
parser.add_argument("--probe-contract", choices=(PROBE_CONTRACT,), required=True)
parser.add_argument("--reference", type=Path, default=here / "frozen-reference.json")
parser.add_argument("--evidence-dir", type=Path, default=here / "evidence")
parser.add_argument("--freeze", action="store_true")
parser.add_argument("--runs", type=int, choices=(1,3), default=1)
parser.add_argument("--evidence-prefix", default=None)
args = parser.parse_args()
if not re.fullmatch(r"[0-9a-f]{40}", args.source_commit):
    parser.error("--source-commit requires a full lowercase Git commit identity")
destination = args.reference
if args.freeze and destination.exists():
    raise SystemExit("Refusing to replace the frozen reference")
args.evidence_dir.mkdir(parents=True, exist_ok=True)
environment = dict(os.environ, LIBGL_ALWAYS_SOFTWARE="1", GALLIUM_DRIVER="llvmpipe", EGL_PLATFORM="surfaceless",
    UBSAN_OPTIONS="halt_on_error=1:abort_on_error=1:print_summary=1:print_stacktrace=1",
    ASAN_OPTIONS="halt_on_error=1:abort_on_error=1:detect_leaks=1:print_summary=1")
evidence_prefix = args.evidence_prefix or ("freeze" if args.freeze else "compare-"+str(time.time_ns()))
runs = []
for i in range(3 if args.freeze else args.runs):
    prefix = args.evidence_dir / f"{evidence_prefix}-{i+1}"
    if any(Path(str(prefix)+suffix).exists() for suffix in ('.stdout','.stderr','.json')):
        raise SystemExit("Refusing to replace child evidence: " + str(prefix))
    run = subprocess.run([args.binary], env=environment, capture_output=True, text=True)
    Path(str(prefix)+'.stdout').write_text(run.stdout)
    Path(str(prefix)+'.stderr').write_text(run.stderr)
    Path(str(prefix)+'.json').write_text(json.dumps({'command':[args.binary],'exit_code':run.returncode,
        'source_commit':args.source_commit,
        'probe_contract':args.probe_contract,
        'probe_tool_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'sanitizer_environment':{key:environment[key] for key in ('ASAN_OPTIONS','UBSAN_OPTIONS')},
        'binary_sha256':hashlib.sha256(Path(args.binary).read_bytes()).hexdigest(),
        'frozen_sha256':hashlib.sha256(destination.read_bytes()).hexdigest() if destination.exists() else None},indent=2)+'\n')
    if run.returncode != 0:
        raise SystemExit(f"Probe failed with exit {run.returncode}: {run.stderr}")
    data = json.loads(run.stdout)
    validate_probe(data)
    runs.append(data)
if args.freeze:
    reference = runs[0]
else:
    record = json.loads(destination.read_text())
    # Pre-contract receipts are accepted only with these exact recorded inputs.
    # They are inspected, not rewritten or relabeled with the compare commit.
    if (record.get("probe_contract", PROBE_CONTRACT) != args.probe_contract or
            record.get("positions") != POSITIONS or record.get("input_geometry") != INPUT_GEOMETRY):
        raise SystemExit("Reference does not match native-basic-v1 geometry/positions")
    reference = record["data"]
    validate_probe(reference)
maximum = 0
for data in runs:
    if data["renderer"] != reference["renderer"]:
        raise SystemExit("Renderer identity changed")
    for expected, actual in zip(reference["cases"],data["cases"],strict=True):
        if expected["category"] != actual["category"]:
            raise SystemExit("Category identity changed")
        if expected["packet_count"] != actual["packet_count"]:
            raise SystemExit("Packet count changed")
        if expected["packet_words"] != actual["packet_words"]:
            raise SystemExit("Exact integer transport changed")
        for name in ("native_pq", "hdr10_basic_pq"):
            for ep, ap in zip(expected[name],actual[name],strict=True):
                for e, a in zip(ep,ap,strict=True):
                    maximum = max(maximum,abs(e-a))
if args.freeze:
    if maximum != 0:
        raise SystemExit("Nonzero repeatability error needs coordinator review before freezing")
    result = {"source_commit":args.source_commit,
              "probe_contract":args.probe_contract,
              "scope":"Synthetic profile-category reconstruction probes, not bitstream conformance",
              "positions":POSITIONS,
              "input_geometry":INPUT_GEOMETRY,
              "repeatability":{"runs":3,"max_absolute_pq_error":maximum,"packet_words_exact":True},
              "proposed_float_tolerance":None,"data":reference}
    destination.write_text(json.dumps(result,indent=2)+"\n")
else:
    if maximum != 0:
        raise SystemExit(f"PQ changed by {maximum}; no nonzero tolerance has been authorized")
print(json.dumps({"mode":"freeze" if args.freeze else "compare", "runs":len(runs),
                  "max_absolute_pq_error":maximum,"exact_transport":True,
                  "frozen_sha256":hashlib.sha256(destination.read_bytes()).hexdigest()}))
