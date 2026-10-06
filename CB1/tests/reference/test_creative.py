# SPDX-License-Identifier: GPL-3.0-or-later
import unittest
from creative_reference import anchors, analysis, trim_rgb, cm4_target


class CreativeContract(unittest.TestCase):
    def test_anchor_domains(self):
        neutral = [2048] * 5
        a = [1800, 2050, 2200, 2048, 2048]
        b = [2100, 2048, 1900, 2048, 2048]
        self.assertEqual(anchors([(2000, a), (3000, b)], 2000, 3500), a)
        self.assertEqual(anchors([(2000, a), (3000, b)], 1800, 3500), a)
        self.assertEqual(anchors([(2000, a), (3000, b)], 2500, 3500),
                         [(x+y)/2 for x, y in zip(a, b)])
        self.assertEqual(anchors([(2000, a), (3000, b)], 3500, 3500), neutral)
        self.assertEqual(anchors([], 2500, 3500), neutral)
        with self.assertRaises(ValueError):
            anchors([(2000, a), (2000, b)], 2500, 3500)

    def test_analysis_is_signed_and_once(self):
        self.assertEqual(analysis([200, 2200, 1400], [2058, 2068, 2018]),
                         [210, 2220, 1370])
        with self.assertRaises(ValueError):
            analysis([10, 2200, 1400], [2000, 2048, 2048])

    def test_neutral_and_black(self):
        # Trim-only reference in absolute linear nits, before output gamut mapping.
        for rgb in [(0, 0, 0), (80, 80, 80), (800, 800, 800), (70, 140, 320)]:
            out = trim_rgb(rgb, 800, [2048] * 5)
            for a, b in zip(out, rgb):
                self.assertAlmostEqual(a, b, places=10)
        self.assertGreater(trim_rgb((0, 0, 0), 800, [2048, 2300, 2048, 2048, 2048])[0], 0)

    def test_cm4_target_requires_an_explicit_table_entry(self):
        self.assertEqual(cm4_target(42, [(42, 3200, 7)]), (3200, 7))
        with self.assertRaises(ValueError):
            cm4_target(42, [])
        with self.assertRaises(ValueError):
            cm4_target(42, [(42, 3200, 7), (42, 3300, 7)])


if __name__ == '__main__':
    unittest.main()
