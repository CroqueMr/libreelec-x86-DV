# SPDX-License-Identifier: MIT
import importlib.util
import unittest


class HDRConversionQualityTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('hdr_conversion_quality'),
                             'HDR-only quality checker is not implemented')
        import hdr_conversion_quality as quality
        self.q = quality

    def test_itu_published_blue_patch(self):
        actual = self.q.itp([296/1023, 201/1023, 582/1023])
        for got, expected in zip(actual, [.3557, .1346, -.1614]):
            self.assertAlmostEqual(got, expected, delta=.00005)

    def test_four_code_neutral_exceeds_one_jnd(self):
        a, b = [.5]*3, [.5+4/1023]*3
        self.assertGreater(self.q.delta_e_itp(a, b), 2.8)
        with self.assertRaisesRegex(AssertionError, 'DeltaE_ITP'):
            self.q.check_hdr_conversion_quality([a], [b])

    def test_saturated_dark_channel_witness_passes(self):
        expected = [[.4571946859359741, .7219524383544922, .01835990510880947]]
        actual = [[.4574306309223175, .7219408750534058, .02103736437857151]]
        metrics = self.q.check_hdr_conversion_quality(expected, actual)
        self.assertAlmostEqual(metrics['max_delta_e_itp'], .03582041556, places=8)

    def test_black_stays_exact(self):
        with self.assertRaisesRegex(AssertionError, 'exact black'):
            self.q.check_hdr_conversion_quality([[0, 0, 0]], [[1e-10]*3])

    def test_expected_neutral_has_quarter_code_limit(self):
        with self.assertRaisesRegex(AssertionError, 'neutral'):
            self.q.check_hdr_conversion_quality([[.5]*3], [[.5+.3/1023]*3])

    def test_fixture_known_neutral_not_evaded_by_reference_roundoff(self):
        with self.assertRaisesRegex(AssertionError, 'neutral'):
            self.q.check_hdr_conversion_quality([[.500001, .5, .499999]],
                                                [[.500001+.3/1023, .5, .499999]], [0])

    def test_component_error_over_four_codes_rejected_even_low_delta_e(self):
        with self.assertRaisesRegex(AssertionError, 'four-code'):
            self.q.check_hdr_conversion_quality([[.6, .7, .02]], [[.6, .7, .025]])

    def test_large_raster_percentile_catches_widespread_sub_jnd_error(self):
        with self.assertRaisesRegex(AssertionError, 'p99.9'):
            self.q.check_hdr_conversion_quality([[.5, .4, .3]]*1000,
                                                [[.5007, .4007, .3007]]*1000)

    def test_domain_and_shape_errors_rejected(self):
        for actual in ([[float('nan'), .2, .3]], [[-1e-5, .2, .3]],
                       [[1.01, .2, .3]], [], [[.1, .2]]):
            with self.subTest(actual=actual), self.assertRaises(AssertionError):
                self.q.check_hdr_conversion_quality([[.1, .2, .3]], actual)

    def test_native_and_enhanced_cannot_opt_in(self):
        import reference
        actual = dict(rgb=[[.5]*3], codes=[[512]*3])
        for mode in ('Native DV', 'Enhanced Natural', 'Enhanced Signature'):
            with self.subTest(mode=mode), self.assertRaisesRegex(AssertionError, 'HDR-only'):
                reference.check_image_integrity(dict(mode=mode, expected=actual), actual,
                                                hdr_conversion_quality=True)


if __name__ == '__main__':
    unittest.main()
