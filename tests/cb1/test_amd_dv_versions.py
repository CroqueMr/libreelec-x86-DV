"""Compile the real AMD stream setup and native HDMI packers off hardware."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from test_hdr10_transport import function


@unittest.skipUnless(os.environ.get("CB1_KERNEL_SOURCE"), "matched patched kernel required")
class AMDVersions(unittest.TestCase):
    def test_v1_packets_and_frozen_v2(self):
        kernel=Path(os.environ["CB1_KERNEL_SOURCE"])
        amd=(kernel/"drivers/gpu/drm/amd/display/amdgpu_dm/amdgpu_dm_dv.c").read_text()
        hdmi=(kernel/"drivers/video/hdmi.c").read_text()
        names=("hdmi_infoframe_checksum", "hdmi_infoframe_set_checksum",
               "hdmi_avi_infoframe_init", "hdmi_avi_infoframe_check_only",
               "hdmi_avi_infoframe_check", "hdmi_avi_infoframe_pack_only",
               "hdmi_avi_infoframe_pack", "hdmi_vendor_infoframe_init",
               "hdmi_vendor_infoframe_length", "hdmi_vendor_infoframe_check_only",
               "hdmi_vendor_infoframe_check", "hdmi_vendor_infoframe_pack_only",
               "hdmi_vendor_infoframe_pack", "hdmi_dolby_vendor_infoframe_init",
               "hdmi_dolby_vendor_infoframe_check", "hdmi_dolby_vendor_infoframe_pack")
        helpers=["dv_display_supported" if "dv_display_supported(" in amd else "dv_dcn_supported",
                 "dv_copy_packet", "dv_stream_edid"]
        if "dv_sink_supported(" in amd: helpers.append("dv_sink_supported")
        families=sorted(set(re.findall(r"\b(?:DCN|DCE)_VERSION_\w+", function(amd,helpers[0]))))
        code=(Path(__file__).with_name("amd_dv_versions.c")).read_text()
        code=code.replace("@@FAMILIES@@", ",".join(families))
        code=code.replace("@@PACKERS@@", "\n".join(function(hdmi,n) for n in names))
        code=code.replace("@@AMD@@", "\n".join(function(amd,n) for n in helpers)+
                          "\n"+function(amd,"amdgpu_dm_dv_configure_stream"))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            header=(kernel/"include/linux/hdmi.h").read_text()
            (root/"hdmi-test.h").write_text(re.sub(r"^#include .*$", "", header, flags=re.M))
            (root/"test.c").write_text(code)
            built=subprocess.run(["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                "-Wno-unused-function", "-Wno-unused-parameter", "-fsanitize=address,undefined",
                "-I"+str(root), "-I"+str(kernel/"include/drm"), str(root/"test.c"),
                "-o", str(root/"test")], capture_output=True, text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            run=subprocess.run([str(root/"test")],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
