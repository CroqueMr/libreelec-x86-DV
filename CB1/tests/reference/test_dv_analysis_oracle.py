import unittest
from decimal import Decimal as D
from dv_analysis_oracle import permitted_bins, qualify, record_values

class QualificationBins(unittest.TestCase):
    def test_stable_bin(self):
        self.assertEqual(permitted_bins(D('.500001')), (D('.5'), D('.5')))

    def test_exact_upper_threshold(self):
        self.assertEqual(permitted_bins(D('.500004')), (D('.5'), D('.50001')))

    def test_exact_tie_is_not_a_stable_gpu_bin(self):
        self.assertEqual(permitted_bins(D('.500005')), (D('.5'), D('.50001')))

    def test_domain_endpoints(self):
        self.assertEqual(permitted_bins(D(0)), (D(0), D(0)))
        self.assertEqual(permitted_bins(D(1)), (D(1), D(1)))

    def test_corrupt_raw_mean_cannot_hide_behind_constant_selection(self):
        record=[0x3f000000,0x40000000,0x3f000000,3]
        with self.assertRaises(AssertionError):
            qualify(record,[D('.5')]*3,[D('.5')]*3,[.5]*3,'corrupt')

    def test_exact_scalar_rounding_is_not_relaxed(self):
        record=[0x3f000000,0x3fc00000,0x3f000000,3]
        with self.assertRaises(AssertionError):
            qualify(record,[D('.5')]*3,[D('.5')]*3,[.50001]*3,'wrong-round')

    def test_constant_keeps_cpu_division_separate(self):
        raw,selected,rounded,exact=record_values([0x3f333333,0x40066666,0x3f333333,3])
        self.assertLess(raw[1],raw[0])
        self.assertNotEqual(raw[1],exact)
        self.assertEqual(selected[0],selected[1])
        self.assertEqual(rounded,[.7]*3)

    def test_exact_binary32_half_up_threshold(self):
        raw,selected,rounded,exact=record_values([0x3c800000,0x3d400000,0x3c800000,3])
        self.assertEqual(rounded,[.01563]*3)

    def test_nonconstant_lower_endpoint_keeps_raw_mean(self):
        raw,selected,rounded,_=record_values([0x3eff3041,0x490dee74,0x3eff3042,1166400])
        self.assertLess(raw[1],raw[0])
        self.assertEqual(selected[1],float(raw[0]))
        self.assertEqual(rounded,[.49842]*3)

    def test_nonconstant_upper_endpoint_keeps_raw_mean(self):
        raw,selected,rounded,_=record_values([0x3f333334,0x40066668,0x3f333335,3])
        self.assertGreater(raw[1],raw[2])
        self.assertEqual(selected[1],float(raw[2]))
        self.assertEqual(rounded,[.7]*3)
