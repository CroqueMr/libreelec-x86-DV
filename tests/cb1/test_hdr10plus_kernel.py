"""Compile HDR10+ contracts from a matched patched kernel, without hardware."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def function(source, name):
    match = re.search(r'^(?:static )?(?:bool|int|void|u8|u32|ssize_t)(?:\n| )' + name + r'\(', source, re.M)
    if not match:
        raise ValueError('Missing kernel function: ' + name)
    start = source.index('{', match.start())
    depth, end = 1, start + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[match.start():end]


class HDR10PlusKernelTests(unittest.TestCase):
    def test_packet_admission_frame_update_and_hdmi_roundtrip(self):
        location = os.environ.get('CB1_KERNEL_SOURCE')
        if not location:
            self.skipTest('Set CB1_KERNEL_SOURCE to the matched patched kernel')
        kernel = Path(location)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            connector = (kernel / 'drivers/gpu/drm/drm_connector.c').read_text()
            amd = (kernel / 'drivers/gpu/drm/amd/display/amdgpu_dm/amdgpu_dm.c').read_text()
            self.assertTrue('int drm_connector_check_hdr10plus(' in connector,
                            'The matched kernel lacks frame-owned HDR10+ admission')
            (root / 'connector_check.inc').write_text(function(connector, 'drm_connector_check_hdr10plus'))
            (root / 'frame_mask.inc').write_text(function(connector, 'drm_atomic_hdr10plus_frame_mask'))
            (root / 'amd_packet.inc').write_text(function(amd, 'fill_hdr10plus_info_packet'))
            (root / 'amd_stream.inc').write_text(function(amd, 'fill_hdr10plus_stream_packet'))
            (root / 'amd_frame.inc').write_text(function(amd, 'hdr10plus_has_frame_update'))
            intel = (kernel / 'drivers/gpu/drm/i915/display/intel_hdmi.c').read_text()
            (root / 'intel_check.inc').write_text(function(intel, 'intel_hdmi_hdr10plus_check'))
            header = (kernel / 'include/linux/hdmi.h').read_text()
            (root / 'hdmi-test.h').write_text(re.sub(r'^#include .*$', '', header, flags=re.M))
            hdmi = (kernel / 'drivers/video/hdmi.c').read_text()
            names = ('hdmi_infoframe_checksum', 'hdmi_infoframe_set_checksum',
                     'hdmi_vendor_infoframe_init', 'hdmi_vendor_infoframe_length',
                     'hdmi_vendor_infoframe_check_only', 'hdmi_vendor_infoframe_check',
                     'hdmi_vendor_infoframe_pack_only', 'hdmi_vendor_infoframe_pack',
                     'hdmi_dolby_vendor_infoframe_init', 'hdmi_dolby_vendor_infoframe_check',
                     'hdmi_dolby_vendor_infoframe_pack', 'hdmi_dolby_vendor_infoframe_unpack',
                     'hdmi_hdr10plus_vendor_infoframe_pack', 'hdmi_hdr10plus_vendor_infoframe_unpack',
                     'hdmi_vendor_any_infoframe_check_only', 'hdmi_vendor_any_infoframe_pack_only',
                     'hdmi_vendor_any_infoframe_unpack')
            (root / 'hdmi-functions.inc').write_text('\n'.join(function(hdmi, name) for name in names))
            display = (kernel / 'drivers/gpu/drm/i915/display/intel_display.c').read_text()
            for code, entry, assignment in (
                (display, 'int intel_atomic_check(', 'state->hdr10plus_primary_mask ='),
                (amd, 'static int amdgpu_dm_atomic_check(', 'hdr10plus_primary_mask =')):
                code = code[code.rindex(entry):]
                self.assertLess(code.index(assignment), code.index('drm_atomic_helper_check_modeset('))
            for test in ('connector', 'packet', 'amd', 'infoframe', 'intel', 'frame_mask'):
                with self.subTest(contract=test):
                    binary = root / test
                    compiled = subprocess.run(['cc', '-Wall', '-Wextra', '-Werror',
                        '-Wno-unused-function', '-fsanitize=address,undefined',
                        '-I' + str(root), '-I' + str(kernel / 'include/drm'),
                        str(ROOT / 'tests/cb1' / ('hdr10plus_' + test + '.c')),
                        '-o', str(binary)], capture_output=True, text=True)
                    self.assertEqual(compiled.returncode, 0, compiled.stderr)
                    run = subprocess.run([str(binary)], capture_output=True, text=True)
                    self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == '__main__':
    unittest.main()
