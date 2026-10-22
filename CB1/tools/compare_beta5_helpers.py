#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compare replacement helpers against a separately supplied frozen Beta5 CB1 tree."""
import argparse
import json
import os
from pathlib import Path
import shlex
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    return subprocess.check_output([str(arg) for arg in args])


def compare_cache(executables, directory):
    paths = [directory/'old.cache', directory/'new.cache']
    def content(path):
        return path.read_bytes() if path.exists() else None
    def compare(limit):
        outputs = [run(binary, path, limit) for binary, path in zip(executables, paths)]
        assert outputs[0] == outputs[1], ('cache transcript', limit)
        assert content(paths[0]) == content(paths[1]), ('cache bytes', limit)
    cases = 0
    for limit in (0, 1, 4096, 16384, 64*1024*1024):
        for path in paths:
            path.unlink(missing_ok=True)
        compare(limit)
        valid = content(paths[0]) or b'pl_cache'+struct.pack('=II', 1, 0)
        variants = [valid, b'', valid[:12], valid+b'x', valid[:-1]]
        for offset in (0, 8, 12, 16, 24, 32, 40, len(valid)//2):
            if offset < len(valid):
                broken = bytearray(valid)
                broken[offset] ^= 255
                variants.append(bytes(broken))
        variants.append(b'pl_cache'+struct.pack('=IIQQQ', 1, 1, 1, 2**64-1, 0))
        for blob in variants:
            for path in paths:
                path.write_bytes(blob)
            compare(limit)
            cases += 1
    return {'cases': cases, 'transcripts_equal': True, 'saved_bytes_equal': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True, type=Path, help='Frozen CB1 directory, not this candidate')
    parser.add_argument('--ffmpeg-prefix', required=True, type=Path, help='Matched patched FFmpeg prefix')
    args = parser.parse_args()
    baseline = args.baseline.resolve()
    if baseline == ROOT:
        parser.error('Baseline must be a separately frozen source tree')
    cc = shlex.split(os.environ.get('CC', 'cc'))
    flags = ['-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
             *shlex.split(os.environ.get('CFLAGS', ''))]
    placebo = shlex.split(run('pkg-config', '--cflags', '--libs', 'libplacebo').decode())
    includes = ['-I'+str(args.ffmpeg_prefix/'include')]
    with tempfile.TemporaryDirectory(prefix='cb1-beta5-helper-') as temp:
        directory = Path(temp)
        caches = []
        for name, source in (('old', baseline), ('new', ROOT)):
            binary = directory/('cache-'+name)
            subprocess.run([*cc, *flags, '-I'+str(source/'src'),
                            str(ROOT/'tests/cache_compatibility.c'), str(source/'src/dvbridge_cache.c'),
                            *placebo, '-o', str(binary)], check=True)
            caches.append(binary)
        cache = compare_cache(caches, directory)
        wrapper = directory/'oracle.c'
        wrapper.write_text('''#include "dvbridge_metadata_bounds.h"
#include "mpv_dvbridge_cm4.h"
int beta5_wire(unsigned level,const uint8_t *raw,size_t size,uint8_t *out)
{return dvbridge_cm4_wire(level,raw,size,out);}
bool beta5_bounds(const void *metadata,size_t bytes)
{return dvbridge_metadata_bounds(metadata,bytes);}
''')
        oracle = directory/'oracle.o'
        subprocess.run([*cc, *flags, *includes, '-I'+str(baseline/'src'),
                        '-c', str(wrapper), '-o', str(oracle)], check=True)
        binary = directory/'metadata'
        subprocess.run([*cc, *flags, *includes, '-I'+str(ROOT/'src'),
                        str(ROOT/'tests/metadata_compatibility.c'), str(oracle), '-o', str(binary)], check=True)
        metadata = json.loads(run(binary))
    print(json.dumps({'cache': cache, 'metadata': metadata}, indent=2))


if __name__ == '__main__':
    main()
