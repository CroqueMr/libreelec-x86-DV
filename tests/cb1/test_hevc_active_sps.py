"""Exercise HEVC format callbacks on IDRs with repeated parameter sets."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


# One self-contained 64x64 intra picture. Both parameter sets signal level 1.
VPS = bytes.fromhex("40010c01ffff0408000003009fa800000300001eba0240")
SPS = bytes.fromhex("4201010408000003009fa800000300001ea020810596e92930bc05a02000000300200000030021")
PPS = bytes.fromhex("4401c0718112")
IDR = bytes.fromhex("2801ade0d117ce73238b80")


def picture(*parameter_sets):
    return b"".join(b"\x00\x00\x00\x01" + nal for nal in (*parameter_sets, PPS, IDR))


class HEVCActiveSPS(unittest.TestCase):
    def test_only_effective_changes_reconfigure_the_decoder(self):
        prefix = os.environ.get("FFMPEG_TEST_PREFIX")
        if not prefix:
            self.skipTest("Set FFMPEG_TEST_PREFIX to the matched FFmpeg build")

        # Change only general_level_idc. The alternative headers are valid at this size.
        other_sps = SPS.replace(b"\x1e", b"\x3c")
        other_vps = VPS.replace(b"\x1e", b"\x3c")
        original = picture(VPS, SPS)
        cases = {
            "repeat": ([original] * 3, 1),
            "unused SPS": ([original, picture(VPS, other_sps, SPS), original], 1),
            "active SPS changes and returns": ([original, picture(VPS, other_sps), original], 3),
            "changed VPS under the same SPS": ([original, picture(other_vps, SPS)], 2),
        }

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            binary = directory / "decode"
            subprocess.run(["cc", "-std=c11", "-I" + prefix + "/include",
                            str(Path(__file__).with_name("hevc_active_sps.c")),
                            "-L" + prefix + "/lib", "-lavcodec", "-lavutil", "-o", str(binary)],
                           check=True)
            for threads in (1, 3):
                for name, (pictures, callbacks) in cases.items():
                    with self.subTest(threads=threads, case=name):
                        paths = []
                        for index, access_unit in enumerate(pictures):
                            path = directory / f"frame-{index}.hevc"
                            path.write_bytes(access_unit)
                            paths.append(str(path))
                        run = subprocess.run([str(binary), str(threads), *paths],
                                             env=dict(os.environ, LD_LIBRARY_PATH=prefix + "/lib"),
                                             capture_output=True, text=True)
                        self.assertEqual(run.returncode, 0, run.stderr)
                        self.assertEqual(run.stdout.strip(), f"{callbacks} callbacks, {len(pictures)} frames")
