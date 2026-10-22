# SPDX-License-Identifier: MIT
"""Reject changes hidden by identical averages, modes or incomplete captures."""
from copy import deepcopy
import hashlib
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))

try:
    from check_reference import compare_case
except ModuleNotFoundError:
    def compare_case(reference, candidate):
        raise AssertionError('Comparison implementation is not present yet')

def sample():
    return {
        'case_id': 'synthetic-master', 'requested_mode': 'master-reference',
        'active_mode': 'master-reference',
        'environment': {'gpu': 'test-gpu', 'driver': 'test-driver', 'filter': 'reference'},
        'capture': {'scope': 'whole_frame', 'width': 1, 'height': 1, 'format': 'RGB8'},
        'frames': [{'index': 0, 'pts': [0, 30],
                    'video_sha256': hashlib.sha256(bytes([10, 20, 30])).hexdigest(),
                    'metadata_sha256': hashlib.sha256(bytes([1, 2, 3])).hexdigest()}]
    }

class Comparisons(unittest.TestCase):
    def test_one_code_difference_is_rejected(self):
        ref = sample(); actual = deepcopy(ref)
        actual['frames'][0]['video_sha256'] = hashlib.sha256(bytes([10, 20, 31])).hexdigest()
        self.assertFalse(compare_case(ref, actual)['pixel_equal'])

    def test_one_metadata_byte_difference_is_rejected(self):
        ref = sample(); actual = deepcopy(ref)
        actual['frames'][0]['metadata_sha256'] = hashlib.sha256(bytes([1, 2, 4])).hexdigest()
        self.assertFalse(compare_case(ref, actual)['metadata_equal'])

    def test_missing_frame_is_rejected(self):
        ref = sample(); actual = deepcopy(ref); actual['frames'] = []
        self.assertFalse(compare_case(ref, actual)['frames_equal'])

    def test_fallback_is_not_an_identical_result(self):
        ref = sample(); actual = deepcopy(ref); actual['active_mode'] = 'fallback'
        self.assertFalse(compare_case(ref, actual)['mode_equal'])

    def test_different_gpu_or_filter_is_incompatible(self):
        for field in ('gpu', 'driver', 'filter'):
            ref = sample(); actual = deepcopy(ref); actual['environment'][field] = 'other'
            self.assertFalse(compare_case(ref, actual)['compatible'])

    def test_empty_expected_video_is_incomplete(self):
        ref = sample(); ref['frames'] = []
        self.assertFalse(compare_case(ref, deepcopy(ref))['complete'])

    def test_identical_complete_case_passes(self):
        ref = sample(); result = compare_case(ref, deepcopy(ref))
        for key in ('pixel_equal', 'metadata_equal', 'frames_equal',
                    'mode_equal', 'compatible', 'complete'):
            self.assertTrue(result[key], key)

    def test_missing_metadata_digest_is_incomplete(self):
        ref = sample(); actual = deepcopy(ref)
        del actual['frames'][0]['metadata_sha256']
        self.assertFalse(compare_case(ref, actual)['complete'])

    def test_changed_timestamp_or_frame_order_is_rejected(self):
        ref = sample(); actual = deepcopy(ref); actual['frames'][0]['pts'] = [1, 30]
        self.assertFalse(compare_case(ref, actual)['frames_equal'])

    def test_malformed_capture_is_incomplete(self):
        ref = sample()
        for actual in (None, {}, {'frames': 'wrong'}, dict(ref, frames=[None])):
            self.assertFalse(compare_case(ref, actual)['complete'])

    def test_invalid_hash_is_incomplete(self):
        ref = sample(); actual = deepcopy(ref); actual['frames'][0]['video_sha256'] = 'sampled'
        self.assertFalse(compare_case(ref, actual)['complete'])

    def test_missing_or_sampled_capture_is_incomplete(self):
        ref = sample()
        for capture in (None, {}, dict(ref['capture'], scope='sampled_pixels')):
            actual = deepcopy(ref); actual['capture'] = capture
            self.assertFalse(compare_case(ref, actual)['complete'])

    def test_same_bytes_with_different_layout_are_incompatible(self):
        ref = sample(); actual = deepcopy(ref); actual['capture']['format'] = 'YUV8'
        self.assertFalse(compare_case(ref, actual)['compatible'])

if __name__ == '__main__':
    unittest.main()
