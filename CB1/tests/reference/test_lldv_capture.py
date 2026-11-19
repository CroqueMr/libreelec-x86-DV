# SPDX-License-Identifier: MIT
"""Checks for the offline verifier of captured LLDV link words."""
from pathlib import Path
import runpy
import struct
import unittest

VERIFY = runpy.run_path(str(Path(__file__).resolve().parents[2] /
                            'tools/verify_lldv_capture.py'))['verify']


class LldvCaptureTests(unittest.TestCase):
    def test_independent_known_pair(self):
        # Pair from the standalone probe. Capture planes are Y, Cb, Cr.
        carrier = bytes.fromhex('93127800c645ab00')
        words = (0x123, 0x456, 0x789, 0xabc)
        capture = struct.pack('<4H', *words)
        self.assertEqual(VERIFY(carrier, capture, 2, 1, 12), [3, 1, 0])
        with self.assertRaisesRegex(ValueError, 'Row 0, pair 0'):
            VERIFY(carrier, struct.pack('<4H', *words[:2], words[3], words[2]), 2, 1, 12)
        with self.assertRaisesRegex(ValueError, 'Row 0, pair 0'):
            VERIFY(carrier, struct.pack('<4H', *words[:3], words[3] + 1), 2, 1, 12)
        with self.assertRaisesRegex(ValueError, 'nonzero padding'):
            VERIFY(carrier, capture, 2, 1, 10)
        ten = bytes.fromhex('80127800c445ab00')
        self.assertEqual(VERIFY(ten, struct.pack('<4H', *(v & ~3 for v in words)), 2, 1, 10),
                         [0, 0, 0])
        with self.assertRaisesRegex(ValueError, 'one tightly packed'):
            VERIFY(carrier, capture[:-2], 2, 1, 12)
