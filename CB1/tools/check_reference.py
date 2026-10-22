# SPDX-License-Identifier: MIT
"""Compare complete capture receipts; never alters or regenerates the oracle."""
import json
import re
import sys

def complete(case):
    if not isinstance(case, dict) or not all(isinstance(case.get(k), str) and case[k]
            for k in ('case_id', 'requested_mode', 'active_mode')):
        return False
    if not isinstance(case.get('environment'), dict) or not all(case['environment'].get(k)
            for k in ('gpu', 'driver', 'filter')):
        return False
    capture = case.get('capture')
    if (not isinstance(capture, dict) or capture.get('scope') != 'whole_frame'
            or not isinstance(capture.get('format'), str) or not capture['format']
            or not all(type(capture.get(k)) is int and capture[k] > 0 for k in ('width', 'height'))):
        return False
    frames = case.get('frames')
    if not isinstance(frames, list) or not frames:
        return False
    for index, frame in enumerate(frames):
        if not isinstance(frame, dict) or frame.get('index') != index:
            return False
        pts = frame.get('pts')
        if not isinstance(pts, list) or len(pts) != 2 or not all(type(x) is int for x in pts) or pts[1] <= 0:
            return False
        if not all(isinstance(frame.get(k), str) and re.fullmatch('[0-9a-f]{64}', frame[k])
                for k in ('video_sha256', 'metadata_sha256')):
            return False
    return True

def compare_case(reference: dict, candidate: dict) -> dict:
    valid = complete(reference) and complete(candidate)
    result = {key: False for key in ('pixel_equal', 'metadata_equal', 'frames_equal', 'mode_equal', 'compatible')}
    result['complete'] = valid
    if not valid:
        return result
    result['compatible'] = (reference['case_id'] == candidate['case_id']
                            and reference['environment'] == candidate['environment']
                            and reference['capture'] == candidate['capture'])
    result['mode_equal'] = all(reference[k] == candidate[k] for k in ('requested_mode', 'active_mode'))
    left, right = reference['frames'], candidate['frames']
    result['frames_equal'] = [(f['index'], f['pts']) for f in left] == [(f['index'], f['pts']) for f in right]
    for field, key in (('video_sha256', 'pixel_equal'), ('metadata_sha256', 'metadata_equal')):
        result[key] = len(left) == len(right) and all(a[field] == b[field] for a, b in zip(left, right))
    return result

def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print('usage: check_reference.py REFERENCE.json CANDIDATE.json', file=sys.stderr)
        return 2
    try:
        with open(argv[0], encoding='utf-8') as stream:
            reference = json.load(stream)
        with open(argv[1], encoding='utf-8') as stream:
            candidate = json.load(stream)
        result = compare_case(reference, candidate)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    if not result['complete'] or not result['compatible']:
        return 2
    return 0 if all(result.values()) else 1

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
