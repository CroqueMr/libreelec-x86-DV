"""Execute the production output-hook routing conditions without a GPU."""
from pathlib import Path
import re
from types import SimpleNamespace
import unittest


SOURCE = (Path(__file__).resolve().parents[2] / "CB1/src/dvbridge_render.c").read_text()


def condition(expression, **values):
    expression = expression.replace("->", ".").replace("&&", " and ").replace("||", " or ")
    expression = re.sub(r"!(?!=)", " not ", expression)
    return bool(eval(expression.strip(), {"__builtins__": {}}, values))


class MasterScalingTests(unittest.TestCase):
    def test_scaled_master_avoids_the_materialized_output_hook(self):
        gate = re.search(r"mask.scaled_quad=(.*?);", SOURCE).group(1)
        hook = re.search(r"\.input = (master && !direct_reference.*?)[?] PL_HOOK_SIG_TEX", SOURCE).group(1)
        for profile5 in (False, True):
            for direct in (False, True):
                for quad in (False, True):
                    with self.subTest(profile5=profile5, direct=direct, quad=quad):
                        mask = SimpleNamespace(profile5_transport=profile5, scaled_quad=False)
                        values = dict(mask=mask, master=True, direct_reference=direct,
                                      r=SimpleNamespace(fragment_quad=quad))
                        mask.scaled_quad = condition(gate, **values)
                        materialized = condition(hook, **values)
                        self.assertEqual(materialized, not direct and not quad,
                                         "Scaled Master must not request an extra FP32 output surface with quad support")


if __name__ == "__main__":
    unittest.main()
