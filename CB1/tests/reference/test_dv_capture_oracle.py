import struct
import unittest
from decimal import Decimal as D
from dv_capture_oracle import analyze_capture


class CapturedPixels(unittest.TestCase):
    def test_black_and_white_groups_have_independent_exact_statistics(self):
        pixels = b''.join(struct.pack('<4f', q, q, q, 1) for q in [0, 0, 1, 1]*2)
        statistics, groups, populations = analyze_capture(pixels, 4, 2)
        self.assertEqual(statistics, [D(0), D('.5'), D(1)])
        self.assertEqual(groups, 2)
        self.assertEqual(sum(populations.values()), 2)

    def test_shape_is_not_inferred_from_record_count(self):
        with self.assertRaises(ValueError):
            analyze_capture(bytes(16), 2, 2)

    def test_nonfinite_pixel_cannot_be_selected_away(self):
        pixels = struct.pack('<4f', float('nan'), 0, 0, 1)*4
        with self.assertRaises(ValueError):
            analyze_capture(pixels, 2, 2)
