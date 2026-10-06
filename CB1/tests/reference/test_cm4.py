# SPDX-License-Identifier: GPL-3.0-only
"""Independent CM4 contract checks, before runtime/GPU qualification."""
import importlib.util
import json
import math
from pathlib import Path
import unittest

SPEC = importlib.util.find_spec('cm4_reference')
if SPEC:
    import cm4_reference as cm4
else:
    cm4 = None

BT2020 = [[.708, .292], [.170, .797], [.131, .046], [.3127, .3290]]
NEUTRAL = {'primary': [2048] * 6}


class CM4Contract(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(cm4, 'independent CM4 reference is not implemented')

    def coefficients(self, **controls):
        return cm4.decode_controls({**NEUTRAL, **controls}, 1000, BT2020)

    def test_neutral_exact(self):
        coeff = self.coefficients()
        self.assertEqual(coeff['sop'], [1, 0, 1])
        self.assertEqual(coeff['mid_exponent'], 1)
        self.assertEqual(coeff['clip_strength'], 0)
        self.assertEqual(coeff['detail_mix'], 0)
        self.assertEqual(coeff['secondary_gain'], [1]*6)
        for rgb in [(0, 0, 0), (125, 125, 125), (70, 140, 320), (1000,)*3]:
            self.assertEqual(cm4.trim_rgb(rgb, coeff), list(rgb))
        absent = cm4.decode_controls({}, 1000, BT2020)
        self.assertEqual(absent['present'], 0)
        self.assertNotEqual(absent['present'], coeff['present'])

    def test_units_and_finite_domain(self):
        coeff = self.coefficients(primary=[2048, 2304, 2048, 2048, 2048, 2048])
        self.assertEqual(cm4.trim_rgb((0,)*3, coeff), [62.5]*3)
        for peak in [0, -1, math.inf, math.nan]:
            with self.assertRaises(ValueError):
                cm4.decode_controls(NEUTRAL, peak, BT2020)
        for invalid in [math.inf, math.nan]:
            with self.assertRaises(ValueError):
                cm4.trim_rgb((invalid, 1, 2), coeff)
        for controls in [{'mid_contrast': 4096}, {'hue': [256]*6},
                         {'primary': [2048]*5}, {'clip_trim': -1}]:
            with self.assertRaises(ValueError):
                self.coefficients(**controls)

    def test_midpoint_symmetry(self):
        for word in [0, 2048, 3072, 4095]:
            coeff = self.coefficients(mid_contrast=word)
            self.assertAlmostEqual(cm4.trim_rgb((500,)*3, coeff)[0], 500, places=10)
            a = cm4.trim_rgb((250,)*3, coeff)[0]
            b = cm4.trim_rgb((750,)*3, coeff)[0]
            self.assertAlmostEqual(a+b, 1000, places=10)
            self.assertEqual(cm4.trim_rgb((0,)*3, coeff), [0]*3)
            self.assertEqual(cm4.trim_rgb((1000,)*3, coeff), [1000]*3)

    def test_clip_monotone(self):
        for word in [0, 2048, 4095]:
            coeff = self.coefficients(clip_trim=word)
            values = [cm4.trim_rgb((i,)*3, coeff)[0] for i in range(1001)]
            self.assertEqual(values, sorted(values))
            self.assertTrue(all(0 <= v <= 1000 for v in values))
            self.assertAlmostEqual(values[250], 250, places=10)
            self.assertAlmostEqual(values[500], 500, places=10)
        self.assertEqual(cm4.trim_rgb((1000,)*3, self.coefficients(clip_trim=0)), [750]*3)

    def test_secondary_wrap_and_achromatic(self):
        coeff = self.coefficients(saturation=[255, 128, 0, 128, 128, 128],
                                  hue=[0, 128, 255, 128, 128, 128])
        for gray in [0, 1e-12, 25, 500, 1000]:
            self.assertEqual(cm4.trim_rgb((gray,)*3, coeff), [gray]*3)
        left = cm4.circular_weights(-math.pi+1e-9, coeff['hue_centres'])
        right = cm4.circular_weights(math.pi-1e-9, coeff['hue_centres'])
        self.assertAlmostEqual(sum(left), 1, places=14)
        self.assertLess(max(abs(a-b) for a, b in zip(left, right)), 1e-8)
        self.assertNotEqual(cm4.trim_rgb((500, 80, 40), coeff), [500, 80, 40])

    def test_decoded_interpolation(self):
        lower = self.coefficients(mid_contrast=2048)
        upper = self.coefficients(mid_contrast=4095, hue=[255]*6)
        result = cm4.blend_coefficients(lower, upper, .5)
        self.assertAlmostEqual(result['mid_exponent'], (1+2**(2047/2048))/2, places=14)
        self.assertEqual(result['one_anchor'], (1 << 9))
        self.assertNotAlmostEqual(result['mid_exponent'], 2**(2047/4096), places=6)
        with self.assertRaises(ValueError):
            cm4.blend_coefficients(lower, upper, 1.1)

    def test_enhanced_objective_endpoints(self):
        for peak in [500, 800, 1000, 1500, 2000]:
            for headroom in [-.5, 0, .5]:
                for preset in ['Natural', 'Signature']:
                    values = [cm4.enhanced_objective((cm4.eotf(i/100*cm4.pq(peak)),)*3,
                              peak, headroom, 1, preset)[0] for i in range(101)]
                    self.assertEqual(values[0], 0)
                    self.assertAlmostEqual(values[-1], peak, places=7)
                    self.assertEqual(values, sorted(values))
                    self.assertLess(values[10], peak/2)
        natural = cm4.enhanced_objective((100,)*3, 1000, .2, 1, 'Natural')
        signature = cm4.enhanced_objective((100,)*3, 1000, .2, 1, 'Signature')
        self.assertNotEqual(natural, signature)

    def test_signature_does_not_darken_authored_midtones(self):
        # A positive preset must not turn 100 authored nits into about 85 nits.
        for headroom in [0, .2, .5]:
            output=cm4.enhanced_objective((100,)*3,1000,headroom,1,'Signature')
            self.assertGreater(output[0],100)
        self.assertEqual(cm4.enhanced_objective((0,)*3,1000,.2,1,'Signature'),[0]*3)

    def test_natural_preserves_general_scene_brightness(self):
        for headroom in [-.5,0,.5]:
            output=cm4.enhanced_objective((100,)*3,1000,headroom,1,'Natural')
            self.assertLessEqual(abs(cm4.pq(output[0])-cm4.pq(100)),2/1024)

    def test_inactive_scene_preserves_authored_response(self):
        for preset in ['Natural','Signature']:
            for rgb in [(0,)*3,(100,)*3,(75,20,10)]:
                self.assertEqual(cm4.enhanced_objective(rgb,1000,.5,0,preset),list(rgb))

    def test_frozen_analytical_vectors(self):
        fixture = json.loads(Path(__file__).with_name('cm4-vectors.json').read_text())
        self.assertEqual(fixture['algorithm'], 'cb1-cm4-v1')
        for case in fixture['cases']:
            coeff = cm4.decode_controls(case['controls'], case['peak_nits'], BT2020)
            got = cm4.trim_rgb(case['input_nits'], coeff)
            for value, expected in zip(got, case['expected_nits']):
                self.assertAlmostEqual(value, expected, delta=case['tolerance_nits'], msg=case['name'])


if __name__ == '__main__':
    unittest.main()
