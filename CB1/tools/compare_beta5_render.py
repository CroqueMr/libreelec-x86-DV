#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stream complete shader outputs from separately built Beta5 and candidate engines."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def build(source, build_dir, binary, mutate=False):
    flags_file = build_dir/'tests/CMakeFiles/scaled_adaptive.dir/flags.make'
    flags = []
    for line in flags_file.read_text().splitlines():
        if line.startswith(('C_DEFINES =', 'C_INCLUDES =', 'C_FLAGS =')):
            flags.extend(shlex.split(line.split('=', 1)[1]))
    link = shlex.split((build_dir/'tests/CMakeFiles/scaled_adaptive.dir/link.txt').read_text())
    command = [link[0], *flags, '-UNDEBUG', '-DCB1_RENDER_IMPLEMENTATION="'+str(source/'src/dvbridge_render.c')+'"',
               '-I'+str(source/'src'), '-I'+str(ROOT/'tests'), str(ROOT/'tests/render_compatibility.c')]
    if mutate:
        command.append('-DCB1_MUTATE_CAPTURE=1')
    subprocess.run([*command, '-o', str(binary), *link[link.index('-o')+2:]],
                   cwd=build_dir/'tests', check=True)


def read_block(stream, size):
    chunks = bytearray()
    while len(chunks) < size:
        part = stream.read(size-len(chunks))
        if not part:
            break
        chunks.extend(part)
    return bytes(chunks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--baseline-build', type=Path, required=True)
    parser.add_argument('--candidate-build', type=Path, required=True)
    parser.add_argument('--negative-control', action='store_true', help='Intentionally corrupt one candidate capture byte')
    args = parser.parse_args()
    old = args.baseline.resolve()
    if old == ROOT:
        parser.error('Use a separately frozen normal Beta5 baseline')
    expected = '7a0878d2c9c0742bf0a353afc3ff8ec140ff47af7630c8be0689873aaf8fbd3c'
    actual = hashlib.sha256((old/'src/dvbridge_render.c').read_bytes()).hexdigest()
    if actual != expected:
        parser.error('Frozen Beta5 renderer identity mismatch: '+actual)
    env = dict(os.environ, EGL_PLATFORM='surfaceless', LIBGL_ALWAYS_SOFTWARE='1', GALLIUM_DRIVER='llvmpipe')
    with tempfile.TemporaryDirectory(prefix='cb1-render-') as temp:
        binaries = [Path(temp)/'old', Path(temp)/'new']
        build(old, args.baseline_build.resolve(), binaries[0])
        build(ROOT, args.candidate_build.resolve(), binaries[1], args.negative_control)
        with tempfile.TemporaryFile() as old_log, tempfile.TemporaryFile() as new_log:
            processes = [subprocess.Popen([str(binary)], stdout=subprocess.PIPE, stderr=log, env=env)
                         for binary, log in zip(binaries, (old_log, new_log))]
            total = 0
            mismatch = None
            try:
                while True:
                    a, b = [read_block(p.stdout, 1024*1024) for p in processes]
                    if a != b:
                        first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
                        mismatch = total+first
                        break
                    total += len(a)
                    if not a:
                        break
            finally:
                if mismatch is not None:
                    for p in processes:
                        p.terminate()
                exits = [p.wait() for p in processes]
                for log in (old_log, new_log):
                    log.seek(0)
                    print(log.read().decode(errors='replace'), end='', file=sys.stderr)
            if mismatch is not None:
                raise SystemExit('First different capture byte: '+str(mismatch))
            if any(exits) or not total:
                raise SystemExit('Capture failed: '+str(exits))
    print(json.dumps({'bytes_compared': total, 'exact': True,
                      'quad_exchange': 'See driver capability in capture logs; unavailable paths are unqualified',
                      'hardware_test': False}, indent=2))


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('Run without Python -O')
    main()
