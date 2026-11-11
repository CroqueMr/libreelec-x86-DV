"""Check the shipped EDID parser and the LLDV-only format decision."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'), 'matched Kodi source required')
class LldvFormat(unittest.TestCase):
    def test_selector_accepts_both_2160p24_clocks(self):
        kodi = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        source = (kodi / 'xbmc/windowing/gbm/WinSystemGbm.cpp').read_text()
        timing = source.split('status.currentTiming = ', 1)[1].split(';', 1)[0]
        code = r'''
#include <cassert>
#include <drm_mode.h>
struct Mode
{
  int hdisplay, vdisplay, clock, htotal, vtotal;
  int hsync_start, hsync_end, vsync_start, vsync_end, hskew, vscan;
  unsigned flags;
};
bool supported(const Mode* mode) { return TIMING; }
int main()
{
  const Mode integer{3840, 2160, 297000, 5500, 2250, 5116, 5204, 2168, 2178,
                     0, 0, DRM_MODE_FLAG_PHSYNC | DRM_MODE_FLAG_PVSYNC};
  Mode fractional = integer;
  fractional.clock = 296703;
  Mode fractional30 = fractional;
  fractional30.htotal = 4400;
  fractional30.hsync_start = 4016;
  fractional30.hsync_end = 4104;
  Mode integer60 = fractional30;
  integer60.clock = 594000;
  Mode wrongSync = fractional;
  ++wrongSync.hsync_start;
  Mode interlaced = fractional;
  interlaced.flags |= DRM_MODE_FLAG_INTERLACE;
  Mode widescreen = fractional;
  widescreen.flags |= DRM_MODE_FLAG_PIC_AR_16_9;
  Mode wrongAspect = fractional;
  wrongAspect.flags |= DRM_MODE_FLAG_PIC_AR_4_3;
  assert(supported(&integer));
  assert(supported(&fractional));
  assert(!supported(&fractional30));
  assert(!supported(&integer60));
  assert(!supported(&wrongSync));
  assert(!supported(&interlaced));
  assert(supported(&widescreen));
  assert(!supported(&wrongAspect));
  assert(!supported(nullptr));
}
'''.replace('TIMING', timing)
        with tempfile.TemporaryDirectory() as work:
            source = Path(work) / 'timing.cpp'
            binary = Path(work) / 'timing'
            source.write_text(code)
            libdrm = subprocess.check_output(['pkg-config', '--cflags', 'libdrm'], text=True).split()
            subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            *libdrm, str(source), '-o', str(binary)], check=True)
            subprocess.run([binary], check=True)

    def test_edid_and_selection(self):
        kodi = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        code = r'''
#include "utils/DVBridgeLldv.h"
#include <cassert>
#include <cstring>

using namespace DVBRIDGE;

static void checksum(unsigned char* block)
{
  unsigned char sum = 0;
  for (int i = 0; i < 127; ++i)
    sum += block[i];
  block[127] = -sum;
}

int main()
{
  unsigned char edid[256] = {0,255,255,255,255,255,255,0};
  edid[126] = 1;
  checksum(edid);
  auto* cta = edid + 128;
  const unsigned char lg[] = {2,3,16,0,0xeb,1,0x46,0xd0,0,0x48,2,0xb6,0x7e,0x68,0x86,0x85};
  std::memcpy(cta, lg, sizeof(lg));
  const auto caps = [&] { checksum(cta); return dvbridge_parse_edid(edid, sizeof(edid)); };
  auto sink = caps();
  assert(sink.status == DV_EDID_STANDARD && dvbridge_lldv_422(sink));
  assert(dvbridge_lldv_444_bits(sink) == 0);
  assert(LldvFormatReason(sink, LldvFormat::Y422_10, 0, true) == LldvReason::Driver);
  assert(LldvFormatReason(sink, LldvFormat::Rgb10, LLDV_422, true) == LldvReason::Display);
  assert(LldvFormatReason(sink, LldvFormat::Y422_12, LLDV_422, false) == LldvReason::Timing);
  assert(ChooseLldvFormat(sink, LLDV_422, true) == LldvFormat::Y422_10);
  assert(ChooseLldvFormat(sink, 0, true) == LldvFormat::Auto);

  cta[11] = 0xb5; // Low Latency only, with the extra HDMI interface.
  cta[13] |= 1;  // 10-bit 4:4:4.
  sink = caps();
  assert(sink.status == DV_EDID_LLDV_ONLY && dvbridge_lldv_422(sink));
  assert(dvbridge_lldv_444_bits(sink) == 10);
  assert(ChooseLldvFormat(sink, LldvBit(LldvFormat::Rgb10), true) == LldvFormat::Rgb10);
  assert(ChooseLldvFormat(sink, LldvBit(LldvFormat::Rgb12), true) == LldvFormat::Auto);
  cta[13] &= ~1;
  cta[12] |= 1; // 12-bit 4:4:4.
  sink = caps();
  assert(dvbridge_lldv_444_bits(sink) == 12);
  assert(ChooseLldvFormat(sink, LldvBit(LldvFormat::Y444_12), true) == LldvFormat::Y444_12);
  cta[12] &= ~1;
  cta[9] = 0x20; // Short V1 with the LL bit clear, then set.
  assert(!dvbridge_lldv_422(caps()));
  cta[12] |= 1;
  assert(dvbridge_lldv_422(caps()));

  cta[9] = 0x48;
  std::memcpy(cta + 16, cta + 4, 12);
  cta[2] = 28;
  sink = caps();
  assert(sink.status == DV_EDID_DUPLICATE && !dvbridge_lldv_422(sink));
  assert(LldvFormatReason(sink, LldvFormat::Y422_10, LLDV_422, true) == LldvReason::Edid);
  edid[5] ^= 1;
  assert(!dvbridge_lldv_422(caps()));
}
'''
        with tempfile.TemporaryDirectory() as work:
            source = Path(work) / 'test.cpp'
            binary = Path(work) / 'test'
            source.write_text(code)
            subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            '-I', str(kodi / 'xbmc'), str(source), '-o', str(binary)], check=True)
            subprocess.run([binary], check=True)

    @unittest.skipUnless(os.environ.get('CB1_KERNEL_SOURCE'), 'matched kernel source required')
    def test_kernel_and_kodi_decode_same_caps(self):
        kodi = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        kernel = Path(os.environ['CB1_KERNEL_SOURCE'])
        self.assertEqual((kodi / 'xbmc/utils/DVBridgeEdid.h').read_bytes(),
                         (kernel / 'include/drm/drm_dvbridge_edid.h').read_bytes())
