# SPDX-License-Identifier: MIT
"""Compile the shipped Intel admission and shared HDMI policy."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "projects/Generic/patches/linux/linux-9910-common-dv-policy.patch"


def replacement(path):
    section = PATCH.read_text(encoding="utf-8").split("+++ b/" + path + "\n", 1)[1]
    section = section.split("\n--- ", 1)[0]
    return "\n".join(line[1:] for line in section.splitlines()
                     if line.startswith("+") and not line.startswith("+++")) + "\n"


class DriverPolicyTests(unittest.TestCase):
    def test_display9_to11_admission_preserves_link_guards(self):
        header = replacement("drivers/gpu/drm/i915/display/intel_dv_lab_policy.h")
        program = r'''
#include <assert.h>
#include "intel_dv_lab_policy.h"
#define admitted(v) intel_dv_lab_platform_supported(v)
int main(void)
{
    assert(admitted(9));   /* Kaby/Coffee/Comet Lake display block */
    assert(admitted(10));
    assert(admitted(11));  /* Ice Lake */
    assert(admitted(12));
    assert(admitted(20));
    assert(!admitted(8));
    assert(!admitted(0));
    assert(intel_dv_lab_native_hdmi(false, false, false));
    assert(!intel_dv_lab_native_hdmi(true, false, false));
    assert(!intel_dv_lab_native_hdmi(false, true, true));
    struct drm_dvbridge_link link = {
        .requested = true, .lab_enabled = true, .sink_standard = true,
        .hdmi = true, .native_hdmi = true, .rgb = true, .progressive = true,
        .requested_bpc = 8, .pipe_bpp = 24, .width = 3840, .height = 2160,
        .rounded_refresh = 24
    };
    assert(intel_dv_lab_validate(&link) == 0);
    link.native_hdmi = false;
    assert(intel_dv_lab_validate(&link) == -EOPNOTSUPP);
    link.native_hdmi = true;
    link.sink_standard = false;
    assert(intel_dv_lab_validate(&link) == -EOPNOTSUPP);
    link.sink_standard = true;
    link.limited_range = true;
    assert(intel_dv_lab_validate(&link) == -EINVAL);
    link.limited_range = false;
    link.hdr_blob = true;
    assert(intel_dv_lab_validate(&link) == -EINVAL);
    link.hdr_blob = false;
    link.requested_bpc = 10;
    assert(intel_dv_lab_validate(&link) == -EINVAL);
    link.requested = false;
    assert(intel_dv_lab_validate(&link) == 0); /* Native playback unaffected. */
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            (tree / "linux").mkdir()
            (tree / "drm").mkdir()
            (tree / "linux/types.h").write_text(
                "#include <stdbool.h>\n#include <stddef.h>\ntypedef unsigned char u8;\n")
            (tree / "linux/errno.h").write_text("#define EINVAL 22\n#define EOPNOTSUPP 95\n")
            for name in ("drm_dvbridge.h", "drm_dvbridge_edid.h"):
                (tree / "drm" / name).write_text(replacement("include/drm/" + name))
            (tree / "intel_dv_lab_policy.h").write_text(header)
            (tree / "check.c").write_text(program)
            subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-I", str(tree), str(tree / "check.c"),
                            "-o", str(tree / "check")], check=True)
            result = subprocess.run([str(tree / "check")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
