# SPDX-License-Identifier: MIT
"""Compare complete capture receipts; never alters or regenerates the oracle."""
import json
import re
import sys

EMPTY_SHA256 = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'

def valid_sha(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None

def complete(case):
    if not isinstance(case, dict) or not all(isinstance(case.get(k), str) and case[k]
            for k in ('case_id', 'requested_mode', 'active_mode', 'expected_active_mode')):
        return False
    if (not all(valid_sha(case.get(k)) for k in ('input_sha256', 'binary_sha256'))
            or not isinstance(case.get('options'), dict) or not case['options']
            or 'model_sha256' not in case
            or (case['model_sha256'] is not None and not valid_sha(case['model_sha256']))
            or (case['options'].get('ai') is True and not valid_sha(case['model_sha256']))):
        return False
    if not isinstance(case.get('environment'), dict) or not all(case['environment'].get(k)
            for k in ('gpu', 'driver', 'filter')):
        return False
    capture = case.get('capture')
    if (not isinstance(capture, dict) or capture.get('scope') != 'whole_frame'
            or not isinstance(capture.get('format'), str) or not capture['format']
            or not all(type(capture.get(k)) is int and capture[k] > 0
                       for k in ('width', 'height', 'video_bytes_per_frame'))
            or type(capture.get('metadata_required')) is not bool):
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
        if not all(valid_sha(frame.get(k)) for k in ('video_sha256', 'metadata_sha256')):
            return False
        if (type(frame.get('video_bytes')) is not int
                or frame['video_bytes'] != capture['video_bytes_per_frame']
                or frame['video_sha256'] == EMPTY_SHA256
                or type(frame.get('metadata_bytes')) is not int or frame['metadata_bytes'] < 0
                or (capture['metadata_required'] and frame['metadata_bytes'] == 0)
                or (frame['metadata_bytes'] == 0) != (frame['metadata_sha256'] == EMPTY_SHA256)):
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
                            and reference['capture'] == candidate['capture']
                            and all(reference[k] == candidate[k]
                                    for k in ('input_sha256', 'options', 'model_sha256')))
    result['mode_equal'] = (reference['requested_mode'] == candidate['requested_mode']
                            and reference['expected_active_mode'] == candidate['expected_active_mode']
                            and all(case['active_mode'] == case['expected_active_mode']
                                    for case in (reference, candidate)))
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
