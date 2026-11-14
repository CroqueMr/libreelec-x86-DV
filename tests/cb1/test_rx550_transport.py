"""Check the RX 550 route before it can request the native DV property."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_hdr10_transport import function


@unittest.skipUnless(os.environ.get('CB1_KERNEL_SOURCE'), 'matched kernel required')
class RX550Transport(unittest.TestCase):
    def test_only_native_standard_at_the_reported_mode(self):
        kernel = Path(os.environ['CB1_KERNEL_SOURCE'])
        owner = (kernel / 'drivers/gpu/drm/amd/display/amdgpu_dm/amdgpu_dm_dv.c').read_text()
        code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
enum { DCE_VERSION_11_2, DCE_VERSION_11_22 };
struct dc_context { int dce_version; struct { unsigned chip_id; } asic_id; };
struct drm_display_mode { int hdisplay, vdisplay, clock, vic; };
static int drm_match_cea_mode(const struct drm_display_mode *mode) { return mode->vic; }
''' + function(owner, 'dv_rx550') + '\n' + function(owner, 'dv_rx550_mode') + r'''
int main(void)
{
    struct dc_context ctx = { DCE_VERSION_11_2, { 0x699f } };
    struct drm_display_mode mode = { 3840, 2160, 296703, 93 };
    assert(dv_rx550(&ctx));
    assert(dv_rx550_mode(&mode));
    mode.clock = 297000;
    assert(!dv_rx550_mode(&mode));
    mode.clock = 296703;
    mode.vic = 95;
    assert(!dv_rx550_mode(&mode));
    mode.vic = 93;
    mode.hdisplay = 4096;
    assert(!dv_rx550_mode(&mode));
    ctx.asic_id.chip_id = 0x67df;
    assert(!dv_rx550(&ctx));
    ctx.asic_id.chip_id = 0x699f;
    ctx.dce_version = DCE_VERSION_11_22;
    assert(!dv_rx550(&ctx));
    assert(!dv_rx550(NULL));
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'test.c'
            binary = Path(directory) / 'test'
            source.write_text(code)
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            str(source), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)
