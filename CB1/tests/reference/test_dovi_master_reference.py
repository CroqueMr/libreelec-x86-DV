# SPDX-License-Identifier: GPL-3.0-or-later
"""Literal fixed-point witnesses, independent of the production GPU helpers."""
import copy
import unittest
from pathlib import Path
import subprocess
import sys

try:
    import dovi_master_reference as reference
except ModuleNotFoundError:
    reference = None


def metadata():
    curve = {"pivots": [0, 1023], "method": [0], "order": [1],
             "poly": [[0, 1 << 23, 0]], "mmr_constant": [0],
             "mmr": [[[0] * 7 for _ in range(3)]]}
    return {"bl_depth": 10, "el_depth": 10, "output_depth": 12, "denom": 23,
            "residual": False, "curves": [copy.deepcopy(curve) for _ in range(3)],
            "nlq": [{"offset": 512, "slope": 8192, "threshold": 4096,
                     "maximum": 131072} for _ in range(3)]}


class IntegerReference(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(reference, "independent Master Reference oracle missing")

    def test_stored_gpu_vectors_match_the_independent_generator(self):
        folder=Path(__file__).parent
        produced=subprocess.check_output([sys.executable,str(folder/'generate_master_vectors.py')])
        self.assertEqual(produced,(folder/'master_vectors.h').read_bytes())

    def test_literal_polynomial_endpoint(self):
        data = metadata()
        data["curves"][0].update(pivots=[256, 768], order=[2], poly=[[0, 0, 1 << 23]])
        self.assertEqual(reference.reshape_component(data, 0, [900, 0, 0]), 36864)
        self.assertEqual(reference.reconstruct(36864, 0, 12), 2304)
        self.assertEqual(reference.reshape_component(data, 0, [0, 0, 0]), 4096)

    def test_pivot_interval_boundary(self):
        data = metadata()
        data["curves"][0].update(pivots=[0, 512, 1023], method=[0, 0],
            order=[1, 1], poly=[[0, 1 << 23, 0], [1 << 22, 0, 0]])
        self.assertEqual(reference.reshape_component(data, 0, [511, 0, 0]), 32704)
        self.assertEqual(reference.reshape_component(data, 0, [512, 0, 0]), 32768)
        self.assertEqual(reference.reshape_component(data, 0, [1023, 0, 0]), 32768)

    def test_literal_residual_bounds(self):
        data = metadata()
        data["residual"] = True
        for sample, want in [(768, 1088), (256, 960), (512, 1024)]:
            residual = reference.nlq_residual(data, 0, sample)
            self.assertEqual(reference.reconstruct(16384, residual, 12), want)

    def test_disabled_residual(self):
        self.assertEqual(reference.nlq_residual(metadata(), 0, 768), 0)

    def test_negative_rounding(self):
        data = metadata()
        data["residual"] = True
        data["nlq"][0].update(offset=2, slope=1, threshold=0)
        self.assertEqual(reference.nlq_residual(data, 0, 1), -1)

    def test_final_depth_rounding(self):
        self.assertEqual(reference.reconstruct(7, 0, 12), 0)
        self.assertEqual(reference.reconstruct(8, 0, 12), 1)
        self.assertEqual(reference.reconstruct(31, 0, 10), 0)
        self.assertEqual(reference.reconstruct(32, 0, 10), 1)
        self.assertEqual(reference.reconstruct(65535, 65535, 12), 4095)
        self.assertEqual(reference.reconstruct(0, -1, 12), 0)

    def test_mmr_orders(self):
        for order, want in [(1, 32768), (2, 16384), (3, 8192)]:
            data = metadata()
            curve = data["curves"][1]
            curve.update(method=[1], order=[order])
            curve["mmr"][0][order - 1][0] = 1 << 23
            self.assertEqual(reference.reshape_component(data, 1, [512, 512, 512]), want)

    def test_mmr_intermediate_truncation(self):
        data = metadata()
        curve = data["curves"][1]
        curve.update(method=[1], order=[3])
        curve["mmr"][0][2][6] = 1 << 23
        # Raw first-order triple is 250623; second 59902; third 14317.
        self.assertEqual(reference.reshape_component(data, 1, [513, 511, 979]), 894)

    def test_signed_clipping(self):
        data = metadata()
        data["curves"][0]["poly"][0] = [-(1 << 40), 0, 0]
        self.assertEqual(reference.reshape_component(data, 0, [512, 512, 512]), 0)
        data["curves"][0]["poly"][0] = [1 << 40, 0, 0]
        self.assertEqual(reference.reshape_component(data, 0, [512, 512, 512]), 65535)

    def test_mmr_grid_edges_and_second_row(self):
        plane = [[16 * y + 4 * x for x in range(4)] for y in range(4)]
        self.assertEqual(reference.reduce_mmr_luma(plane, 0, 0), 9)
        self.assertEqual(reference.reduce_mmr_luma(plane, 1, 0), 16)
        self.assertEqual(reference.reduce_mmr_luma(plane, 0, 1), 41)

    def test_filter_constant_edges(self):
        for operation in ["bl-v", "el-y-v", "el-c-v", "h"]:
            self.assertTrue(all(v == 257 for row in
                reference.resample_plane([[257]], operation) for v in row))

    def test_horizontal_impulse(self):
        self.assertEqual(reference.resample_plane([[0, 0, 4096, 0, 0, 0]], "h")[0],
                         [0, 0, 0, 2456, 4096, 2456, 0, 0, 0, 94, 0, 22])

    def test_vertical_impulse(self):
        values = reference.resample_plane([[0], [256], [0], [0]], "bl-v")
        self.assertEqual([row[0] for row in values], [0, 65, 222, 222, 65, 0, 0, 4])


if __name__ == "__main__":
    unittest.main()
