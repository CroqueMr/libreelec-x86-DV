# SPDX-License-Identifier: MIT
"""Catch accidental bounded-scalar caps at the signed/extended mapper seam."""
import math
import json
import os
from pathlib import Path
import unittest
import reference as R
import image_reference as I


class MapperDomainTests(unittest.TestCase):
    def test_forward_boundary_without_upper_guard(self):
        self.assertTrue(hasattr(I,"mapper_pq_encode"),"extended mapper equation required")
        self.assertEqual(I.mapper_pq_encode(0),0)
        self.assertEqual(I.mapper_pq_encode(-1),0)
        self.assertEqual(I.mapper_pq_encode(10000),1)
        self.assertGreater(I.mapper_pq_encode(10001),1)
        self.assertEqual(I.mapper_pq_encode(37418),1.1339130126547765)
        with self.assertRaises(AssertionError): R.pq_encode(10001)

    def test_reverse_boundary_and_finite_domain_pole(self):
        self.assertTrue(hasattr(I,"mapper_pq_decode"),"extended mapper equation required")
        self.assertEqual(I.mapper_pq_decode(0),0)
        self.assertEqual(I.mapper_pq_decode(-1),0)
        self.assertEqual(I.mapper_pq_decode(1),10000)
        self.assertGreater(I.mapper_pq_decode(1.001),10000)
        pole=(2413/2392)**(2523/32)
        for value in (pole,math.inf,math.nan):
            with self.assertRaises(AssertionError): I.mapper_pq_decode(value)
        with self.assertRaises(AssertionError): R.pq_decode(1.001)

    @unittest.skipUnless(os.environ.get("CB1_REFERENCE_LIBRARY"),"explicit pinned library required")
    def test_independent_extended_complete_outputs(self):
        root=Path(__file__).parent
        original=json.loads((root/'vectors.json').read_text())
        fixed=json.loads((root/'scaled-output-vectors.json').read_text())
        self.assertEqual(len(fixed['cases']),3)
        self.assertEqual(fixed['source_vectors_sha256'],R.hashlib.sha256((root/'vectors.json').read_bytes()).hexdigest())
        for case in fixed['cases']:
            source=next(c for c in original['scaler_cases'] if c.get('id')==case['source_scaler_id'])
            inputs=case['input'];policy=I.source_policy(inputs)
            _,mapped=I.map_image(source['sampled'],inputs,policy)
            pq=[[R.pq_encode(max(0,min(10000,v))) for v in p] for p in I.container_image(mapped,inputs['gamut'])]
            error=max(abs(a-b) for p,q in zip(pq,case['expected']['rgb']) for a,b in zip(p,q))
            self.assertLessEqual(error,1e-10) # Existing complete binary64 PQ contract.
            self.assertEqual(I.resolve_image(pq,12,True),case['expected']['codes'])


if __name__=="__main__":unittest.main()
