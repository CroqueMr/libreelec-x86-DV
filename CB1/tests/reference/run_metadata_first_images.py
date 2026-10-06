# SPDX-License-Identifier: MIT
"""Standard-equivalent pixels and independent source-metadata wire oracle."""
import copy
import json
from pathlib import Path
import subprocess
import sys
from run_gpu_images import wire
from run_enhanced_dv_images import crc_division, check_transport


def packet(pair, margins):
    source = pair['input']['image_input']
    payload = bytearray.fromhex(pair['wire']['payload_hex'])
    assert len(payload) == 95 and payload[75] == 1 and payload[86] == 5
    payload[1] = 1
    payload[64:68] = b''.join(source[k].to_bytes(2, 'big')
                             for k in ('source_min_pq', 'source_max_pq'))
    l1 = source['l1'][0]
    payload[76:82] = b''.join(l1[k].to_bytes(2, 'big') for k in ('min', 'max', 'avg'))
    payload[87:95] = b''.join(x.to_bytes(2, 'big') for x in margins)
    if source.get('generation') == 'CM4':
        payload[70] = 3
        payload[82:82] = b'\x00\x00\x00\x02\xfe\x00\x00'
    prefix = bytes([0, 0, 0, len(payload) >> 8, len(payload) & 255])
    body = prefix + payload + bytes(124 - len(prefix) - len(payload))
    return body + crc_division(body).to_bytes(4, 'big')


def check(pair, actual, margins):
    source = pair['input']['image_input']
    l1 = source['l1'][0]
    assert actual['source_pq'] == [source['source_min_pq'], source['source_max_pq']]
    assert actual['l1'] == [l1[k] for k in ('min', 'max', 'avg')]
    assert actual['source_cm_version'] == (40 if source.get('generation') == 'CM4' else 29)
    assert actual['statistics'] == [0, 0, 0] and actual['raw_record'] == [0] * 12
    assert actual['margins'] == margins
    expected = packet(pair, margins)
    assert actual['packet_hex'] == expected.hex()
    # The C probe already compares every intermediate pixel bit-for-bit with
    # the Standard renderer. This independently verifies its final RGB8 wire.
    transport = copy.deepcopy(pair)
    transport['expected']['rgb'] = actual['rgb']
    check_transport(transport, actual, expected)


def main():
    root = Path(__file__).parent
    pairs = [p for p in json.loads((root/'vectors.json').read_text())['dv_cases']
             if 'image_input' in p['input']]
    assert len(pairs) == 48
    additional = json.loads((root/'dv-conformant-scaled-vectors.json').read_text())['dv_cases']
    assert len(additional) == 12
    pairs += additional
    valid = negative = failed = 0
    for pair in pairs:
        source = copy.deepcopy(pair['input']['image_input'])
        source.update(bits=10, limited=True)
        ineligible = pair['id'].startswith('dv-pair-output-scaled-')
        args = [sys.argv[1], source['preset']] + (['negative-geometry'] if ineligible else [])
        result = subprocess.run(args, input=wire(dict(input=source)), capture_output=True, text=True)
        print(pair['id'], 'exit', result.returncode, flush=True)
        if result.returncode == 77:
            print('SKIP: required real transport capability unavailable')
            return 77
        if result.returncode:
            print(result.stderr, end=''); failed += 1; continue
        actual = json.loads(result.stdout)
        if ineligible:
            assert actual == dict(negative_geometry=True)
            negative += 1
            continue
        w, h = pair['input']['size']
        try:
            check(pair, actual, [0, 3840-w, 0, 2160-h])
        except AssertionError:
            print('FAIL independent metadata/CRC/transport', json.dumps(actual), flush=True)
            failed += 1
        valid += 1
    seed = next(p for p in pairs if p['id'] == 'dv-pair-output-0-BT2020-0-1')
    for side, active in enumerate(([1, 0, 2, 2], [0, 0, 1, 2], [0, 1, 2, 2], [0, 0, 2, 1])):
        control = copy.deepcopy(seed)
        source = control['input']['image_input']
        source.update(size=[4, 4], output_size=[2, 2], rgb=[[.5]*3]*16, el=[[512]*3]*16)
        words = wire(dict(input={**source, 'bits': 10, 'limited': True})).split()
        words[19+side] = '1'
        result = subprocess.run([sys.argv[1], source['preset']], input=' '.join(words)+'\n',
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        actual = json.loads(result.stdout)
        l, t, r, b = active
        assert all(pixel == [0, 0, 0] for i, pixel in enumerate(actual['rgb'])
                   if not (l <= i % 2 < r and t <= i // 2 < b))
        control['input'].update(size=[2, 2], active=active)
        check(control, actual, [l, 3840-r, t, 2160-b])
    assert valid == 48 and negative == 12
    print('PASS Standard pixel identity, source L1/mastering, L5/CM4/CRC, final transport:',
          valid, 'pairs;', negative, 'negative geometries; 4 fractional borders;', failed, 'failures')
    return bool(failed)


if __name__ == '__main__':
    sys.exit(main())
