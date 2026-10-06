# SPDX-License-Identifier: MIT
"""Catch false readiness, domain confusion, and self-generated expectations."""
import json
import os
import struct
from pathlib import Path
import unittest

import reference

ROOT = Path(__file__).resolve().parent


def operation():
    return {
        "id": "CB1_PQ_RESCALE", "status": "ready", "essential": True,
        "domain": "ideal binary64 absolute PQ", "units": "nits to normalized PQ",
        "order": 1, "parameters": {"zero": "library special case"},
        "eligibility": "finite nits in [0,10000]",
        "state": "stateless", "authority": "ideal-st2084-binary64-with-pinned-zero-convention",
        "coverage": ["scalar"], "required_cases": ["pq-100"],
    }


def case():
    return {
        "id": "pq-100", "operation": "CB1_PQ_RESCALE", "mode": "contract-only",
        "generation": "common", "target_class": "none",
        "source": "ideal-st2084-binary64-with-pinned-zero-convention", "input": {"nits": 100.0},
        "expected": {"pq": 0.508078421517399}, "coverage": ["scalar"],
        "comparison": {"domain": "ideal binary64 absolute PQ", "units": "normalized PQ",
                       "rule": "absolute", "limit": 1e-12,
                       "reason": "binary64 independent ST2084 arithmetic roundoff"},
    }


class ContractTests(unittest.TestCase):
    def dv_input(self):
        return {"rgb": [[.6,.1,.2]]*4, "size": [2,2], "active": [0,0,2,2],
                "identity": [1,2,3], "revision": 3, "generation": "CM4",
                "source": {"l1": [{"min": 0, "avg": 512, "max": 3079}],
                           "reconstruction_valid": True, "levels": [1,3,8,254]},
                "peak": 1500.25, "gamut": "P3-D65", "panel": "OLED"}

    def dv_output(self, inputs):
        self.assertTrue(callable(getattr(reference, "transformed_dv_output", None)),
                        "transformed DV metadata contract missing")
        return reference.transformed_dv_output(inputs)

    def test_enhanced_dv_requires_coherent_metadata(self):
        inputs = self.dv_input()
        output = self.dv_output(inputs)
        self.assertEqual(output["l1"], [2458,2458,2458])
        self.assertEqual(output["levels"], [1,5])
        self.assertEqual(output["output_generation"], "CB1_ETSI_LEGACY_LITERAL")
        for changed in ([], [{"min":0,"avg":0,"max":0}]):
            inputs["source"]["l1"] = changed
            with self.assertRaisesRegex(AssertionError,"source L1"):
                self.dv_output(inputs)

    def test_transformed_output_cannot_reuse_stale_trims(self):
        inputs = self.dv_input()
        for forbidden in ([1,2,5], [1,3,5,8,254], [1,4,5], [1,5,10]):
            inputs["output_levels"] = forbidden
            with self.assertRaisesRegex(AssertionError,"legacy levels"):
                self.dv_output(inputs)

    def test_output_metadata_does_not_mutate_source(self):
        import copy
        inputs = self.dv_input()
        frozen = copy.deepcopy(inputs)
        output = self.dv_output(inputs)
        self.assertEqual(inputs, frozen)
        output["rgb"][0][0] = 0
        self.assertEqual(inputs, frozen)

    def test_unknown_light_levels_are_not_measured(self):
        output = self.dv_output(self.dv_input())
        self.assertEqual(output["light_levels"], {"max_cll":0,"max_fall":0,"measured":False})
        self.assertEqual(output["source_pq"], [0,3261])
        self.assertEqual(output["nominal_max_nits"], 1501)
        self.assertEqual(output["container"], "BT2020/PQ")

    def test_metadata_matches_picture_and_revision(self):
        inputs = self.dv_input()
        inputs["revision"] = 4
        with self.assertRaisesRegex(AssertionError,"identity"):
            self.dv_output(inputs)

    def test_dv_linear_reduction_partial_edges_and_saturated_maxrgb(self):
        inputs = self.dv_input()
        inputs.update(size=[3,1], active=[0,0,3,1], rgb=[[1,0,0],[0,1,0],[0,0,0]])
        output = self.dv_output(inputs)
        self.assertEqual(output["groups"], 2)
        self.assertEqual(output["statistics"], [0,.46327,.92655])
        self.assertEqual(output["l1"], [0,3795,1898])
        for rgb in ([[float("nan"),0,0]]*3, [[1.01,0,0]]*3, [[.2,.3]]*3):
            inputs["rgb"] = rgb
            with self.assertRaisesRegex(AssertionError,"raster|PQ"):
                self.dv_output(inputs)

    def test_dv_preserves_true_constants_and_wire_collisions(self):
        self.assertTrue(callable(getattr(reference,"dv_statistics",None)), "output analysis missing")
        for value, code in ((0,0),(.5,2048),(1,4095)):
            out = reference.dv_statistics([[value]*3]*4,[2,2],[0,0,2,2])
            self.assertEqual(out["l1"], [code]*3)
        out = reference.dv_statistics([[v]*3 for v in (.50001,.50003)],[1,2],[0,0,1,2])
        self.assertEqual(out["l1"], [2048]*3)

    def test_dv_deferred_state_never_recycles_unsignaled_storage(self):
        self.assertTrue(callable(getattr(reference,"evaluate_dv_lifecycle",None)), "deferred DV state missing")
        actual = reference.evaluate_dv_lifecycle({"events":[
            {"op":"prepare","identity":[1,2,3],"revision":3},
            {"op":"poll","fence":"timeout"}, {"op":"cancel"},
            {"op":"prepare","identity":[1,2,4],"revision":4},
            {"op":"retire","fence":"signaled"},
            {"op":"prepare","identity":[1,2,4],"revision":4},
            {"op":"reset"}, {"op":"retire","fence":"timeout"}]})
        self.assertEqual([s["status"] for s in actual["snapshots"]],
                         ["pending","pending","cancelled","busy","idle","pending","reset","busy"])
        self.assertIsNone(actual["snapshots"][-1]["committed"])
        self.assertTrue(actual["snapshots"][-1]["storage_busy"])

    def test_frozen_dv_pairs_and_cpu_wire(self):
        import subprocess
        data = json.loads((ROOT/"vectors.json").read_text())
        self.assertTrue(data.get("dv_cases"), "independent DV pairs missing")
        for vector in data["dv_cases"]:
            with self.subTest(case=vector["id"]):
                if "image_input" not in vector["input"] or os.environ.get("CB1_REFERENCE_LIBRARY"):
                    reference.check(vector, reference.evaluate(vector))
                if os.environ.get("CB1_DV_SERIALIZER_CONTROL"):
                    wire = vector["wire"]
                    args = [*vector["expected"]["l1"], vector["expected"]["source_pq"][1],
                            *wire["margins"], wire["refresh"], wire["id"]]
                    actual = subprocess.check_output([os.environ["CB1_DV_SERIALIZER_CONTROL"],
                                                      *map(str,args)],text=True,
                        env=dict(os.environ,ASAN_OPTIONS="halt_on_error=1:abort_on_error=1:detect_leaks=1")).splitlines()
                    self.assertEqual(actual,[wire["payload_hex"],wire["packet_hex"]])
        if not os.environ.get("CB1_DV_SERIALIZER_CONTROL"):
            self.skipTest("explicit existing CPU serializer control required for packet bytes/CRC")

    def test_dv_geometry_half_pixel_sides_and_empty_window(self):
        self.assertTrue(callable(getattr(reference,"dv_active_window",None)), "DV L5 geometry missing")
        for margins, active in (([1,0,0,0],[1,540,1920,1620]),
                                ([0,1,0,0],[0,540,1919,1620]),
                                ([0,0,1,0],[0,541,1920,1620]),
                                ([0,0,0,1],[0,540,1920,1619]),
                                ([0,0,0,0],[0,540,1920,1620])):
            i={"size":[3840,2160],"source_size":[3840,2160],
               "destination":[0,540,1920,1080],"source_margins":margins}
            self.assertEqual(reference.dv_active_window(i),active)
        with self.assertRaisesRegex(AssertionError,"empty"):
            reference.dv_active_window({"size":[3840,2160],"source_size":[3840,2160],
                "destination":[0,540,1920,1080],"source_margins":[1919,1920,0,0]})

    def test_dv_equal_pts_revision_forces_refresh_without_advancing_failure(self):
        events=[{"op":"prepare","identity":[1,2,3],"revision":3,"pts":1},
                {"op":"poll","fence":"signaled"}, {"op":"resolve","surface":"A"},
                {"op":"submit","surface":"A"},
                {"op":"commit","identity":[1,2,3],"surface":"A"},
                {"op":"retire","fence":"signaled"},
                {"op":"prepare","identity":[1,2,4],"revision":4,"pts":1},
                {"op":"poll","fence":"signaled"}, {"op":"resolve","surface":"B"},
                {"op":"submit","surface":"B"},
                {"op":"commit","identity":[1,2,4],"surface":"B","success":False}]
        actual=reference.evaluate_dv_lifecycle({"events":events})["snapshots"]
        self.assertTrue(actual[6]["pending"].get("force_refresh"), "equal-PTS revision refresh missing")
        self.assertEqual(actual[-1]["committed"],[1,2,3])

    def test_dv_new_resolve_invalidates_old_submission(self):
        events=[{"op":"prepare","identity":[1,2,3],"revision":3},
                {"op":"poll","fence":"signaled"}, {"op":"resolve","surface":"previous"},
                {"op":"submit","surface":"previous"},
                {"op":"commit","identity":[1,2,3],"surface":"previous"},
                {"op":"retire","fence":"signaled"},
                {"op":"prepare","identity":[1,3,3],"revision":3},
                {"op":"poll","fence":"signaled"}, {"op":"resolve","surface":"A"},
                {"op":"submit","surface":"A"}, {"op":"resolve","surface":"B"},
                {"op":"commit","identity":[1,3,3],"surface":"A"},
                {"op":"commit","identity":[1,3,3],"surface":"B"},
                {"op":"submit","surface":"A"}, {"op":"submit","surface":"B"},
                {"op":"resolve","surface":"B"},
                {"op":"commit","identity":[1,3,3],"surface":"B"},
                {"op":"submit","surface":"B"},
                {"op":"commit","identity":[1,3,3],"surface":"B"},
                {"op":"commit","identity":[1,3,3],"surface":"B"}]
        actual=reference.evaluate_dv_lifecycle({"events":events})["snapshots"]
        # Literal transaction outcomes, independent of the oracle implementation.
        self.assertEqual([s["status"] for s in actual[6:]],
                         ["pending","ready","resolved","submitted","resolved",
                          "rejected","rejected","rejected","submitted","resolved",
                          "rejected","submitted","committed","rejected"])
        for s in actual[6:18]:
            self.assertEqual(s["committed"],[1,2,3])
            self.assertEqual(s["cached"],[1,2,3])
            self.assertEqual(s["pending"]["identity"],[1,3,3])
        for s in actual[18:]:
            self.assertEqual(s["committed"],[1,3,3])
            self.assertEqual(s["cached"],[1,3,3])
            self.assertIsNone(s["pending"])

    def test_dv_ready_repoll_is_idempotent_for_both_spellings(self):
        for spelling in ("poll","retire"):
            with self.subTest(spelling=spelling):
                events=[{"op":"prepare","identity":[1,2,3],"revision":3},
                        {"op":spelling,"fence":"signaled"},
                        {"op":spelling,"fence":"timeout"},
                        {"op":spelling,"fence":"failed","visible":False,"identity":[9,9,9]}]
                actual=reference.evaluate_dv_lifecycle({"events":events})["snapshots"]
                self.assertEqual([s["status"] for s in actual],["pending","ready","ready","ready"])
                for s in actual[1:]:
                    self.assertEqual(s,{"status":"ready","pending":{"identity":[1,2,3],
                        "ready":True,"force_refresh":True},"committed":None,"cached":None,
                        "storage_busy":True})

    def test_dv_poll_retires_cancel_reset_and_commit_slots(self):
        prepare={"op":"prepare","identity":[1,2,3],"revision":3}
        controls=[([prepare,{"op":"cancel"}],"cancelled",None,None),
                  ([prepare,{"op":"reset"}],"reset",None,None),
                  ([prepare,{"op":"poll","fence":"signaled"},{"op":"resolve","surface":"A"},
                    {"op":"submit","surface":"A"},
                    {"op":"commit","identity":[1,2,3],"surface":"A"}],
                   "committed",[1,2,3],[1,2,3])]
        for events,ending,committed,cached in controls:
            for spelling in ("poll","retire"):
                with self.subTest(ending=ending,spelling=spelling):
                    sequence=events+[{"op":spelling,"fence":"timeout"},
                                     {"op":spelling,"fence":"signaled"},
                                     {"op":spelling,"fence":"timeout"}]
                    actual=reference.evaluate_dv_lifecycle({"events":sequence})["snapshots"]
                    self.assertEqual([s["status"] for s in actual[-4:]],
                                     [ending,"busy","idle","idle"])
                    self.assertEqual([s["storage_busy"] for s in actual[-4:]],
                                     [True,True,False,False])
                    for s in actual[-4:]:
                        self.assertIsNone(s["pending"])
                        self.assertEqual(s["committed"],committed)
                        self.assertEqual(s["cached"],cached)

    def test_dv_independent_descriptor_boundaries_and_geometry_packets(self):
        import subprocess
        controls=json.loads((ROOT/"vectors.json").read_text())["dv_auxiliary_controls"]
        for c in controls["descriptors"]:
            self.assertAlmostEqual(reference.pq_encode(c["nominal_max_nits"]),c["ideal_pq"],delta=1e-12)
            self.assertEqual(reference.dv_code(reference.pq_encode(c["nominal_max_nits"])),c["source_max_pq"])
            if c["peak"] > 1:
                i=self.dv_input(); i["peak"]=c["peak"]
                self.assertEqual(self.dv_output(i)["source_pq"],[0,c["source_max_pq"]])
                self.assertEqual(self.dv_output(i)["nominal_max_nits"],c["nominal_max_nits"])
        for c in controls["geometry"]:
            self.assertEqual(reference.dv_active_window(c["input"]),c["active"])
        if not os.environ.get("CB1_DV_SERIALIZER_CONTROL"):
            self.skipTest("explicit existing CPU serializer control required for geometry/temporal packets")
        for c in controls["geometry"]+controls["wire"]:
            w=c["wire"]
            values=[*c.get("l1",[2048]*3),c.get("source_max_pq",3261),*w["margins"],w["refresh"],w["id"]]
            actual=subprocess.check_output([os.environ["CB1_DV_SERIALIZER_CONTROL"],*map(str,values)],text=True,
                env=dict(os.environ,ASAN_OPTIONS="halt_on_error=1:abort_on_error=1:detect_leaks=1")).splitlines()
            self.assertEqual(actual,[w["payload_hex"],w["packet_hex"]])

    def test_dv_identical_source_statistics_cannot_determine_output_average(self):
        inputs=self.dv_input()
        inputs.update(size=[1,8],active=[0,0,1,8])
        means=[]
        for reduced in ((0,.25,.25,1),(0,.0625,.5625,1)):
            inputs["rgb"]=[[v]*3 for v in reduced for _ in range(2)]
            means.append(self.dv_output(inputs)["statistics"][1])
        self.assertEqual(means,[.375,.40625])

    def test_dv_wrong_source_identity_policy_and_generation_fail(self):
        import copy
        data=json.loads((ROOT/"vectors.json").read_text())
        original=next(v for v in data["dv_cases"] if "image_input" in v["input"])["input"]
        for key,value in (("identity",[1,7,99]),("peak",600),("generation","CM4")):
            inputs=copy.deepcopy(original)
            if key=="identity": inputs["revision"]=99
            inputs[key]=value
            with self.assertRaisesRegex(AssertionError,"identity|policy|generation"):
                self.dv_output(inputs)

    def test_dv_five_decimal_ties_and_format_scope(self):
        self.assertTrue(callable(getattr(reference,"dv_round_statistic",None)), "five-place tie policy missing")
        for value,rounded in ((.500005,.50001),(.5000049,.5),(.000005,.00001),(1,1)):
            self.assertEqual(reference.dv_round_statistic(value),rounded)
        import copy
        data=json.loads((ROOT/"vectors.json").read_text())
        vector=copy.deepcopy(data["dv_cases"][0]); vector["mode"]="Reference Expert"
        row=next(r for r in json.loads((ROOT/"operation-matrix.json").read_text())["operations"]
                 if r["id"]=="CB1_DV_METADATA_PAIR")
        row=copy.deepcopy(row); row["required_cases"]=[vector["id"]]
        with self.assertRaisesRegex(AssertionError,"DV mode"):
            reference.validate_contract([row],[vector])

    def test_enhancement_projects_mapper_excursions_with_common_anchor(self):
        self.assertTrue(callable(getattr(reference,"nominal_cube_projection",None)),
                        "shared nominal-cube entrance projection missing")
        for rgb,want in (([110,50,10],[100,52,20]),
                         ([-10,50,90],[0,48,80]),
                         ([-10,50,110],[0,50,100]),
                         ([110,110,110],[100,100,100]),
                         ([-10,-10,-10],[0,0,0]),
                         ([0,50,100],[0,50,100])):
            self.assertEqual(reference.nominal_cube_projection(rgb,100),want)
        for rgb in ([float("nan"),0,0],[True,0,0],[0,0]):
            with self.assertRaisesRegex(AssertionError,"RGB"):
                reference.nominal_cube_projection(rgb,100)
        controls=json.loads((ROOT/"vectors.json").read_text())["dv_auxiliary_controls"]["projection"]
        for c in controls:
            projected=reference.nominal_cube_projection(c["rgb"],c["peak"])
            for actual,wanted in zip(projected,c["expected"]):
                self.assertAlmostEqual(actual,wanted,delta=1e-12)
            self.assertEqual(reference.nominal_cube_projection(projected,c["peak"]),projected)
        self.assertGreater(controls[-1]["expected"][1],controls[-2]["expected"][1])




    def test_gpu_budget_rejects_malformed_rasters(self):
        import copy
        vector = {"input":{}, "expected":{"rgb":[[0,0,0],[.2,.2,.2]],
                                            "codes":[[64,64,64],[239,239,239]]}}
        for field, changed in (
                ("codes", []), ("codes", [[64,64,64]]),
                ("codes", [[64,64,64],[239,239]]),
                ("codes", [[64,64,64],[239,239,239,239]]),
                ("codes", [[64.,64,64],[239,239,239]]),
                ("codes", [[True,64,64],[239,239,239]]),
                ("rgb", [[0,0,0],[.2,.2]]),
                ("rgb", [[0,0,0],[.2,.2,.2,.2]]),
                ("rgb", [[False,0,0],[.2,.2,.2]]),
                ("rgb", [[float("nan"),0,0],[.2,.2,.2]])):
            actual = copy.deepcopy(vector["expected"])
            actual[field] = changed
            with self.subTest(field=field, changed=changed), self.assertRaises(AssertionError):
                reference.check_image_integrity(vector, actual)

    def test_prepare_rejects_nonfinite_pts_preserving_commit(self):
        for pts in (float("nan"),float("inf"),float("-inf"),True):
            result = reference.evaluate_lifecycle({"events":[
                {"op":"prepare","identity":[1,2,3],"revision":3,"pts":1},
                {"op":"resolve","surface":"A"}, {"op":"submit","surface":"A"},
                {"op":"present","identity":[1,2,3],"surface":"A"},
                {"op":"prepare","identity":[1,2,4],"revision":4,"pts":pts}]})
            with self.subTest(pts=pts):
                self.assertFalse(result["snapshots"][-1]["accepted"])
                self.assertEqual(result["snapshots"][-1]["committed"],[1,2,3])
                self.assertIsNone(result["snapshots"][-1]["cached"])

    def test_image_mode_matches_applied_preset(self):
        import copy
        data = json.loads((ROOT/"vectors.json").read_text())
        cases = [v for v in data["image_cases"] if v["input"].get("preset")]
        self.assertTrue(cases)
        for vector in cases:
            self.assertEqual(vector["mode"],"Enhanced DV",vector["id"])
        vector = copy.deepcopy(cases[0])
        vector["mode"] = "Reference Expert"
        row = next(r for r in json.loads((ROOT/"operation-matrix.json").read_text())["operations"]
                   if r["id"] == vector["operation"])
        row = dict(row, required_cases=[vector["id"]])
        with self.assertRaisesRegex(AssertionError,"mode"):
            reference.validate_contract([row],[vector])

    def test_nonidentity_reconstruction_has_independent_fixed_images(self):
        data = json.loads((ROOT/"vectors.json").read_text())
        cases = [v for v in data["image_cases"] if v["id"].startswith("reconstruct-nonidentity-")]
        self.assertEqual(len(cases),3,"nonidentity reconstruction controls missing")
        for vector in cases:
            reference.check(vector,reference.reconstruct_image(vector["input"]))

    def test_complete_resize_uses_one_domain_without_intermediate_clamp(self):
        controls = json.loads((ROOT/"vectors.json").read_text())["scaler_cases"]
        cases = [c for c in controls if c.get("id") == "two-axis-upscale-overshoot"
                 or c.get("id") == "mixed-axis-downscale-precedence"]
        self.assertEqual(len(cases),2,"complete-resize controls missing")
        overshoot = next(c for c in cases if c["id"] == "two-axis-upscale-overshoot")
        self.assertLess(overshoot["vertical_extrema"][0],0)
        self.assertGreater(overshoot["vertical_extrema"][1],1)
        if not os.environ.get("CB1_REFERENCE_LIBRARY"):
            self.skipTest("explicit pinned library required for complete-resize controls")
        for vector in cases:
            with self.subTest(resize=vector["id"]):
                actual = reference.scale_image(vector["input"],vector["input_size"],vector["output_size"])
                for pixel,wanted in zip(actual,vector["sampled"]):
                    for got,fixed in zip(pixel,wanted):
                        self.assertAlmostEqual(got,fixed,delta=1e-6)

    def test_source_scaling_black_matches_final_zero_contract(self):
        if not os.environ.get("CB1_REFERENCE_LIBRARY"):
            self.skipTest("explicit pinned library required for scaling black")
        for size,target in (([2,2],[4,4]),([4,2],[2,4])):
            scaled = reference.scale_image([[0,0,0]]*(size[0]*size[1]),size,target)
            self.assertEqual(scaled,[[0,0,0]]*(target[0]*target[1]))

    def test_full_image_composition_is_not_scalar_checkpoint(self):
        self.assertTrue(callable(getattr(reference, "evaluate_image", None)),
                        "complete image evaluator missing")
        vectors = json.loads((ROOT / "vectors.json").read_text())["image_cases"]
        self.assertGreaterEqual(len(vectors), 50)
        if not os.environ.get("CB1_REFERENCE_LIBRARY"):
            self.skipTest("explicit pinned library required for full image vectors")
        for vector in vectors:
            with self.subTest(image=vector["id"]):
                reference.check(vector, reference.evaluate_image(vector))

    def test_complete_image_presence_and_source_immutability(self):
        if not os.environ.get("CB1_REFERENCE_LIBRARY"):
            self.skipTest("explicit pinned library required for full source-policy tests")
        import copy
        original = json.loads((ROOT / "vectors.json").read_text())["image_cases"][2]
        for optional in (None, {}, {"L2": [0,0,0], "L3": 0, "L8": [0]}):
            vector = copy.deepcopy(original)
            vector["input"]["optional"] = optional
            before = copy.deepcopy(vector["input"])
            reference.check(vector, reference.evaluate_image(vector))
            self.assertEqual(before, vector["input"])
        for mutate in (lambda i:i.update(l1=[]), lambda i:i.update(l1=[{"min":0,"avg":0,"max":0}]),
                       lambda i:i["l1"].append(dict(i["l1"][0])),
                       lambda i:i.update(metadata_valid=False),
                       lambda i:i.update(rpu_identity=[1,8,1]),
                       lambda i:i.update(el_identity=[1,8,1]),
                       lambda i:i.update(source_max_pq=0),
                       lambda i:i["l6"].append(dict(i["l6"][0]))):
            vector = copy.deepcopy(original)
            mutate(vector["input"])
            with self.assertRaises(AssertionError):
                reference.evaluate_image(vector)

    def test_full_image_integrity_rules_are_executable(self):
        self.assertTrue(callable(getattr(reference,"check_image_integrity",None)),
                        "black/detail/hue image acceptance missing")
        import copy
        data = json.loads((ROOT / "vectors.json").read_text())
        for vector in data["image_cases"]:
            if vector["operation"] == "CB1_OUTPUT_RESOLVE_IMAGE":
                reference.check_image_integrity(vector, vector["expected"])
        vector = next(v for v in data["image_cases"] if v["id"] == "output-0-BT2020-0-0")
        for index in (0,1,8):
            actual = copy.deepcopy(vector["expected"])
            actual["rgb"][index][0] += 0.001
            with self.assertRaises(AssertionError):
                reference.check_image_integrity(vector,actual)

    def test_frozen_lifecycle_vectors_are_executable(self):
        data = json.loads((ROOT / "vectors.json").read_text())
        self.assertTrue(data.get("lifecycle_cases"), "frozen state vectors missing")
        for vector in data["lifecycle_cases"]:
            reference.check(vector, reference.evaluate_lifecycle(vector["input"]))

    def test_full_fel_reference_retains_signed_one_code(self):
        self.assertTrue(callable(getattr(reference, "reconstruct_image", None)),
                        "independent full-FEL reconstruction missing")
        data = {"rgb": [[0.5, 0.5, 0.5]], "el": [[513, 511, 512]],
                "el_bits": 10, "denom": 12, "offset": [512]*3,
                "slope": [1]*3, "threshold": [0]*3, "fel": True,
                "identity": [1, 7, 1], "rpu_identity": [1, 7, 1],
                "el_identity": [1, 7, 1]}
        result = reference.reconstruct_image(data)
        self.assertEqual(result["signal"], [[0.5001220703125, 0.4998779296875, 0.5]])
        data["el_identity"] = [1, 8, 1]
        with self.assertRaisesRegex(AssertionError, "pair"):
            reference.reconstruct_image(data)

    def test_target_capability_does_not_change_valid_profile(self):
        self.assertTrue(callable(getattr(reference, "target_capability", None)),
                        "target representation capability contract missing")
        for peak in (1e-320, 1e-8, 1e-6):
            result = reference.target_capability(peak)
            self.assertEqual(result["requested"], peak)
            self.assertFalse(result["supported"])
        result = reference.target_capability(1500.1)
        self.assertTrue(result["supported"])
        self.assertLessEqual(abs(result["represented"] - 1500.1), result["rounding_bound"])

    def test_above_sentinel_collapsed_public_pq_range_fails_treatment(self):
        if not os.environ.get("CB1_REFERENCE_LIBRARY"):
            self.skipTest("explicit pinned library required for near-sentinel PQ capability")
        import copy
        vector = copy.deepcopy(next(v for v in json.loads((ROOT/"vectors.json").read_text())["image_cases"]
                                    if v["id"] == "output-border-overlay-flip"))
        for peak in (1.0000001111620804e-6,1.000001e-6):
            vector["input"]["peak"] = peak
            with self.subTest(peak=peak), self.assertRaisesRegex(AssertionError,"PQ range"):
                reference.evaluate_image(vector)

    def test_presentation_state_has_owned_final_surface(self):
        self.assertTrue(callable(getattr(reference, "evaluate_lifecycle", None)),
                        "presentation lifecycle vectors missing")

    def test_pending_cancel_preserves_committed_and_caller_surface(self):
        actual = reference.evaluate_lifecycle({"events": [
            {"op":"prepare","identity":[1,2,3],"revision":3},
            {"op":"resolve","surface":"scanout-A"},
            {"op":"submit","surface":"scanout-A"},
            {"op":"present","identity":[1,2,3],"surface":"scanout-A"},
            {"op":"prepare","identity":[1,2,4],"revision":4},
            {"op":"cancel"}]})
        self.assertEqual(actual["snapshots"][-1], {
            "accepted":True,"pending":None,"committed":[1,2,3],
            "cached":None,"surface":None,"retained":["scanout-A"]})

    def test_geometry_uses_source_scaler_before_mapping(self):
        self.assertTrue(callable(getattr(reference, "scale_image", None)),
                        "source-derived Lanczos/Hermite image reference missing")
        if not os.environ.get("CB1_REFERENCE_LIBRARY"):
            self.skipTest("explicit pinned library required for scaler control")
        controls = json.loads((ROOT / "vectors.json").read_text())["scaler_cases"]
        for control in controls:
            actual = reference.scale_image(control["input"], control["input_size"], control["output_size"])
            for got, want in zip(actual, control["sampled"]):
                for value, fixed in zip(got,want):
                    self.assertAlmostEqual(value, fixed, delta=control.get("comparison",{}).get("limit",1e-8))

    def test_lifecycle_requires_resolved_submitted_surface(self):
        result = reference.evaluate_lifecycle({"events": [
            {"op": "prepare", "identity": [1, 2, 3], "revision": 3},
            {"op": "present", "identity": [1, 2, 3], "surface": "scanout-A"},
            {"op": "resolve", "surface": "scanout-A"},
            {"op": "present", "identity": [1, 2, 3], "surface": "scanout-A"},
            {"op": "submit", "surface": "scanout-A"},
            {"op": "present", "identity": [1, 2, 3], "surface": "scanout-A"},
            {"op": "pause", "identity": [1, 2, 3]},
            {"op": "prepare", "identity": [1, 2, 4], "revision": 4},
            {"op": "present", "identity": [1, 2, 3], "surface": "scanout-A"},
            {"op": "resolve", "surface": "scanout-B", "success": False},
            {"op": "pause", "identity": [1, 2, 4]},
            {"op": "reset"}]})
        self.assertEqual([s["accepted"] for s in result["snapshots"]],
                         [True, False, True, False, True, True, True, True,
                          False, False, False, True])
        self.assertEqual(result["snapshots"][5]["committed"], [1,2,3])
        self.assertEqual(result["snapshots"][9]["committed"], [1,2,3])
        self.assertIsNone(result["snapshots"][-1]["cached"])
        self.assertEqual(result["snapshots"][-1]["retained"], ["scanout-A"])

    def test_ideal_vectors_are_not_library_representation_claims(self):
        vectors = json.loads((ROOT / "vectors.json").read_text())["cases"]
        preserved = {
            "pq-zero": ({"pq": 0}, 1e-12),
            "pq-nearblack": ({"pq": 0.02148621379868528}, 1e-12),
            "pq-100": ({"pq": 0.508078421517399}, 1e-12),
            "pq-1000": ({"pq": 0.751827096247041}, 1e-12),
            "pq-10000": ({"pq": 1}, 1e-12),
            "pq-decode-half": ({"nits": 92.24570899406527}, 1e-9),
            "l1-dark": ({"max_pq_y": 0.5001221001221001,
                         "avg_pq_y": 0.12503052503052503}, 1e-15),
            "l1-high-key": ({"max_pq_y": 1, "avg_pq_y": 0.7518925518925519}, 1e-15),
        }
        self.assertEqual(set(preserved), {v["id"] for v in vectors if v["id"] in preserved})
        for vector in vectors:
            if vector["id"] in preserved:
                with self.subTest(case=vector["id"]):
                    self.assertIn("ideal binary64", vector["comparison"]["domain"])
                    self.assertIn("ideal", vector["source"])
                    self.assertEqual(vector["expected"], preserved[vector["id"]][0])
                    self.assertEqual(vector["comparison"]["limit"], preserved[vector["id"]][1])

    def test_source_defined_l1_binary32_values_and_bits(self):
        for avg, maximum, values, bits in (
            (512, 2048, [0.5001221299171448, 0.1250305324792862],
             [0x3f000801, 0x3e000801]),
            (3079, 4095, [1.0, 0.7518925666809082], [0x3f800000, 0x3f407c08]),
            (0, 4095, [1.0, 0.0], [0x3f800000, 0x00000000]),
        ):
            vector = {"operation": "CB1_L1_LIBRARY_REPRESENTATION", "input": {
                "l1": [{"min": 0, "avg": avg, "max": maximum}]}, "expected": {
                    "max_pq_y": values[0], "avg_pq_y": values[1], "bits": bits},
                "comparison": {"domain": "binary32 library PQ hints", "units": "PQ and bits",
                               "rule": "exact", "limit": 0,
                               "reason": "source-defined float division by 4095.0f"}}
            with self.subTest(avg=avg, maximum=maximum):
                reference.check(vector, reference.evaluate(vector))
                wrong = dict(vector["expected"], bits=[bits[0] ^ 1, bits[1]])
                with self.assertRaisesRegex(AssertionError, "bits"):
                    reference.check(vector, wrong)

    def test_public_pq_has_separate_frozen_binary_receipt(self):
        data = json.loads((ROOT / "vectors.json").read_text())
        self.assertIn("public_pq_cases", data)
        self.assertTrue(callable(getattr(reference, "evaluate_public_pq", None)))
        cases = data["public_pq_cases"]
        self.assertEqual([c["expected"]["bits"] for c in cases],
                         [0, 0x3cb003c9, 0x3f021164, 0x3f4077e4, 0x3f800000, 0x42b87cc5])
        for vector in cases:
            self.assertEqual(vector["comparison"]["rule"], "exact")
            self.assertEqual(vector["comparison"]["limit"], 0)
            value = vector["expected"]["value"]
            self.assertEqual(struct.unpack("<I", struct.pack("<f", value))[0],
                             vector["expected"]["bits"])
        if not os.environ.get("CB1_REFERENCE_LIBRARY"):
            self.skipTest("explicit pinned CB1_REFERENCE_LIBRARY required for public PQ receipt")
        lib = reference.characterized_library(os.environ["CB1_REFERENCE_LIBRARY"])
        for vector in cases:
            with self.subTest(case=vector["id"]):
                actual = reference.evaluate_public_pq(lib, vector["input"])
                reference.check(vector, actual)
                with self.assertRaisesRegex(AssertionError, "bits"):
                    reference.check(vector, dict(actual, bits=actual["bits"] ^ 1))

    def test_required_image_stages_cannot_downgrade_to_scalar(self):
        # Independent of the editable JSON coverage and the validator's set.
        stages = ("CB1_RECONSTRUCTION_IMAGE", "CB1_SOURCE_SCENE_POLICY",
                  "CB1_DISPLAY_MAP_IMAGE", "CB1_GAMUT_MAP_IMAGE",
                  "CB1_ENHANCE_NATURAL_IMAGE", "CB1_ENHANCE_INTENSE_IMAGE",
                  "CB1_OUTPUT_RESOLVE_IMAGE", "CB1_ENHANCE_NATURAL_POLICY",
                  "CB1_ENHANCE_INTENSE_POLICY")
        matrix = json.loads((ROOT / "operation-matrix.json").read_text())
        rows = {row["id"]: row for row in matrix["operations"]}
        for identifier in stages:
            for declared in (["scalar"], ["scalar", "image"]):
                row, vector = dict(rows[identifier]), case()
                # Supply unrelated readiness fields, then mutate the actual
                # stage's coverage to scalar (or leave image without pixels).
                row.update(operation())
                row.update(id=identifier, status="ready", coverage=declared)
                vector["operation"] = identifier
                with self.subTest(stage=identifier, coverage=declared), \
                        self.assertRaisesRegex(AssertionError, "image|coverage"):
                    reference.validate_contract([row], [vector])

    def test_contract_rejects_undefined_operation(self):
        vector = case()
        vector["operation"] = "UNDEFINED"
        with self.assertRaisesRegex(AssertionError, "undefined"):
            reference.validate_contract([operation()], [vector])

    def test_contract_rejects_missing_domain_or_expected(self):
        for key in ("domain", "units"):
            row = operation()
            del row[key]
            with self.subTest(key=key), self.assertRaises(AssertionError):
                reference.validate_contract([row], [case()])
        for expected in ({}, None):
            vector = case()
            vector["expected"] = expected
            with self.subTest(expected=expected), self.assertRaises(AssertionError):
                reference.validate_contract([operation()], [vector])

    def test_contract_rejects_unjustified_comparison(self):
        for change in ({"reason": ""}, {"limit": float("nan")},
                       {"rule": "close-enough"}, {"units": ""}, {"domain": ""}):
            vector = case()
            vector["comparison"].update(change)
            with self.subTest(change=change), self.assertRaises(AssertionError):
                reference.validate_contract([operation()], [vector])

    def test_contract_distinguishes_creative_processing(self):
        row = operation()
        row.update(id="L2_DETAIL", creative=True, disposition={
            "parsed": True, "applied": True, "transmitted": False, "not_applied": False})
        vector = case()
        vector["operation"] = "L2_DETAIL"
        with self.assertRaisesRegex(AssertionError, "image"):
            reference.validate_contract([row], [vector])

    def test_contract_requires_all_enabled_operations(self):
        row = operation()
        row.update(id="CB1_DISPLAY_MAP", coverage=["scalar", "image"])
        vector = case()
        vector["operation"] = "CB1_DISPLAY_MAP"
        # A parser/scalar success cannot close an essential image operation.
        row["parameters"]["parser_passed"] = True
        with self.assertRaisesRegex(AssertionError, "coverage"):
            reference.validate_contract([row], [vector], runtime=True)

    def test_essential_cannot_be_not_applied(self):
        row = operation()
        row["status"] = "not_applied"
        with self.assertRaisesRegex(AssertionError, "essential"):
            reference.validate_contract([row], [])

    def test_runtime_rejects_blocked_essential_operation(self):
        row = operation()
        row.update(status="blocked", gap="no independent image oracle")
        with self.assertRaisesRegex(AssertionError, "blocked"):
            reference.validate_contract([row], [], runtime=True)

    def test_duplicate_case_and_operation_are_rejected(self):
        with self.assertRaisesRegex(AssertionError, "duplicate"):
            reference.validate_contract([operation(), operation()], [case()])
        with self.assertRaisesRegex(AssertionError, "duplicate"):
            reference.validate_contract([operation()], [case(), case()])

    def test_case_authority_cannot_be_evaluator_output(self):
        vector = case()
        vector["source"] = "reference.evaluate"
        with self.assertRaisesRegex(AssertionError, "authority"):
            reference.validate_contract([operation()], [vector])

    def test_fixed_pq_expectation(self):
        actual = reference.evaluate(case())
        self.assertIn("pq", actual)
        self.assertAlmostEqual(actual["pq"], 0.508078421517399, delta=1e-12)

    def test_check_rejects_changed_numeric_output(self):
        with self.assertRaisesRegex(AssertionError, "pq"):
            reference.check(case(), {"pq": 0.51})

    def test_check_rejects_nan_and_missing_values(self):
        for actual in ({"pq": float("nan")}, {}):
            with self.subTest(actual=actual), self.assertRaises(AssertionError):
                reference.check(case(), actual)

    def test_evaluator_does_not_read_expected(self):
        vector = case()
        vector["expected"] = {"pq": -999.0}
        self.assertEqual(reference.evaluate(vector), reference.evaluate(case()))

    def test_evaluator_rejects_invalid_inputs(self):
        for nits in (-1.0, 10001.0, float("nan"), float("inf"), True):
            vector = case()
            vector["input"]["nits"] = nits
            with self.subTest(nits=nits), self.assertRaises(AssertionError):
                reference.evaluate(vector)

    def test_all_fixed_vectors(self):
        # Added data is not silently accepted without fixed expected values.
        if not (ROOT / "vectors.json").exists():
            self.fail("fixed vector file is missing")
        data = json.loads((ROOT / "vectors.json").read_text())
        vectors = (data["cases"] + data["image_cases"] + data["lifecycle_cases"]
                   + data["capability_cases"] + data["dv_cases"] + data["dv_lifecycle_cases"])
        matrix = json.loads((ROOT / "operation-matrix.json").read_text())["operations"]
        reference.validate_contract(matrix, vectors)
        for vector in vectors:
            if (vector in data["image_cases"] or "image_input" in vector["input"]) and not os.environ.get("CB1_REFERENCE_LIBRARY"):
                continue  # Explicit dedicated full-image test reports this skip.
            with self.subTest(case=vector["id"]):
                reference.check(vector, reference.evaluate(vector))
        reference.validate_contract(matrix, vectors, runtime=True)

    def test_selective_highlights_are_not_uniform_gain(self):
        inputs = {"rgb": [[0, 0, 0], [0.01, 0.01, 0.01], [150, 150, 150],
                          [1000, 1000, 1000], [1500, 1500, 1500]],
                  "peak": 1500, "scene_ratio": 0.02}
        vector = {"operation": "CB1_ENHANCE_NATURAL_POLICY", "input": inputs}
        actual = reference.evaluate(vector)
        self.assertEqual(actual["rgb"][:3], inputs["rgb"][:3])
        # Independently derived: 1500*(2/3 + (1/5)*(25/27)*(2/9)).
        self.assertAlmostEqual(actual["rgb"][3][0], 1061.7283950617284, delta=1e-9)
        self.assertEqual(actual["rgb"][4], [1500, 1500, 1500])

    def test_intense_midtones_and_high_key_protection(self):
        vector = {"operation": "CB1_ENHANCE_INTENSE_POLICY", "input": {
            "rgb": [[150, 150, 150], [1000, 1000, 1000]],
            "peak": 1500, "scene_ratio": 0.5}}
        actual = reference.evaluate(vector)
        self.assertGreater(actual["rgb"][0][0], 150)
        # High-key scene mask halves k; 1500*(2/3+(7/40)*(2/9)).
        self.assertAlmostEqual(actual["rgb"][1][0], 1058.3333333333333, delta=1e-9)

    def test_external_library_characterization_route_exists(self):
        self.assertTrue(callable(getattr(reference, "characterize_library", None)),
                        "public-library characterization is not implemented")
        if not os.environ.get("CB1_REFERENCE_LIBRARY"):
            self.skipTest("explicit pinned CB1_REFERENCE_LIBRARY required")
        characterized = reference.characterize_library(os.environ["CB1_REFERENCE_LIBRARY"])
        self.assertEqual(characterized["version"], "v7.372.0")
        for sample in characterized["samples"]:
            self.assertAlmostEqual(sample["black"][0], 0, delta=1e-4)
            self.assertAlmostEqual(sample["white"][0], characterized["peak_pq"], delta=1e-4)
            for channel in sample["black"][1:] + sample["white"][1:]:
                self.assertAlmostEqual(channel, 0, delta=1e-4)

    def test_unorm16_neutral_chroma_bias_is_not_hidden(self):
        self.assertTrue(callable(getattr(reference, "pack_ipt", None)),
                        "UNORM16 packing reference is missing")
        self.assertEqual(reference.pack_ipt([0, 0, 0]), [0, 32767, 32767])
        # The pinned shader subtracts 32768/65535, not the packing bias.
        self.assertEqual(reference.unpack_ipt([0, 32767, 32767]),
                         [0, -1 / 65535, -1 / 65535])

    def test_lut_interpolation_keeps_all_eight_corners(self):
        self.assertTrue(callable(getattr(reference, "lookup_lut", None)),
                        "source-defined ICh interpolation reference is missing")
        # 2x2x2 lattice, I fastest. Each channel is affine: I+2*C+4*h.
        lattice = [[v, v + 10, v + 20] for v in range(8)]
        self.assertEqual(reference.lookup_lut(lattice, (2, 2, 2), [0.25, 0.5, 0.75]),
                         [4.25, 14.25, 24.25])
        self.assertEqual(reference.lookup_lut(lattice, (2, 2, 2), [-1, 2, 2]),
                         [6, 16, 26])

    def test_required_case_cannot_be_borrowed_from_another_operation(self):
        first, second = operation(), operation()
        second["id"] = "OTHER"
        second["required_cases"] = ["other-case"]
        first["required_cases"] = ["other-case"]
        vector = case()
        vector.update(id="other-case", operation="OTHER")
        with self.assertRaisesRegex(AssertionError, "required case"):
            reference.validate_contract([first, second], [case(), vector])

    def test_manifest_cannot_drop_essential_image_stage(self):
        self.assertTrue(callable(getattr(reference, "validate_manifest", None)))
        matrix = json.loads((ROOT / "operation-matrix.json").read_text())
        vectors = json.loads((ROOT / "vectors.json").read_text())["cases"]
        matrix["operations"] = [row for row in matrix["operations"]
                                if row["id"] != "CB1_GAMUT_MAP_IMAGE"]
        with self.assertRaisesRegex(AssertionError, "pipeline"):
            reference.validate_manifest(matrix, vectors)

    def test_isolated_policy_ramps_and_repeated_source_are_bounded(self):
        pixels = [[n, n, n] for n in range(0, 1501)]
        for name in ("CB1_ENHANCE_NATURAL_POLICY", "CB1_ENHANCE_INTENSE_POLICY"):
            vector = {"operation": name, "input": {"rgb": pixels, "peak": 1500, "scene_ratio": 0.02}}
            first, repeat = reference.evaluate(vector), reference.evaluate(vector)
            self.assertEqual(first, repeat)
            self.assertEqual(vector["input"]["rgb"], pixels)
            for pixel, following in zip(first["rgb"], first["rgb"][1:]):
                self.assertTrue(0 <= pixel[0] < following[0] <= 1500)
                self.assertEqual(pixel[0], pixel[1])
                self.assertEqual(pixel[1], pixel[2])


if __name__ == "__main__":
    unittest.main()
