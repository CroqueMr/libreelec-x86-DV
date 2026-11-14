"""Check the shipped EDID parser and the LLDV-only format decision."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'), 'matched Kodi source required')
class LldvFormat(unittest.TestCase):
    def test_edid_render_target(self):
        kodi = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        code = r'''
#include "utils/DVBridgeLldv.h"
#include <cassert>
#include <cmath>
#include <cstring>
using namespace DVBRIDGE;

int main()
{
  unsigned char edid[256] = {0,255,255,255,255,255,255,0};
  edid[126] = 1;
  auto* cta = edid + 128;
  const unsigned char lg[] = {2,3,16,0,0xeb,1,0x46,0xd0,0,0x48,2,0xb6,0x7e,0x68,0x86,0x85};
  std::memcpy(cta, lg, sizeof(lg));
  const auto checksum = [](unsigned char* block) {
    unsigned char sum = 0;
    for (int i = 0; i < 127; ++i) sum += block[i];
    block[127] = -sum;
  };
  checksum(edid);
  const auto read = [&] { checksum(cta); return ReadLldvDisplay(edid, sizeof(edid)); };
  auto target = read();
  assert(target.status == LldvEdidStatus::Ready);
  assert(target.sink.version == 2 && target.black == 0);
  assert(std::abs(target.peak - 2484) < 1);
  assert(target.reported[0] == 0.6875 && target.reported[4] == 0.1484375);
  assert(target.reported != target.primaries);
  assert(ReadLldvDisplay(edid, 128).status == LldvEdidStatus::Incomplete);
  assert(ReadLldvDisplay(nullptr, 0).status == LldvEdidStatus::Missing);
  edid[7] ^= 1;
  assert(read().status == LldvEdidStatus::Invalid);
  edid[7] ^= 1;
  cta[9] = 0x68;
  assert(read().status == LldvEdidStatus::UnsupportedBlock);
  cta[9] = 0x48;
  cta[14] = 0x80;
  cta[15] = 0x80;
  assert(read().status == LldvEdidStatus::UnsupportedGamut);
  cta[12] = 0;
  cta[13] = 0;
  cta[14] = 0;
  cta[15] = 0;
  assert(read().status == LldvEdidStatus::InvalidPrimaries);
  const unsigned char shortV1[] = {0x28, 0x24, 0x00, 0x59, 0x8a, 0x62, 0x84};
  std::memcpy(cta + 9, shortV1, sizeof(shortV1));
  target = read();
  assert(target.sink.version == 1 && target.peak == 1000 && target.black == 0);
  assert(target.status == LldvEdidStatus::Ready);
  assert(target.reported[1] == 0.3125 && target.reported[2] == 69 / 256.0);
  cta[12] &= ~3u;
  assert(read().status == LldvEdidStatus::NoLowLatency);
  cta[2] = 4;
  assert(read().status == LldvEdidStatus::NoDolbyVision);
}
'''
        with tempfile.TemporaryDirectory() as work:
            source = Path(work) / 'target.cpp'
            binary = Path(work) / 'target'
            source.write_text(code)
            subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-I',
                            str(kodi / 'xbmc'), str(source), '-o', str(binary)], check=True)
            subprocess.run([binary], check=True)

    def test_selector_accepts_only_the_approved_uhd_cta_modes(self):
        from test_native_video_source import body

        kodi = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        source = (kodi / 'xbmc/windowing/gbm/WinSystemGbm.cpp').read_text()
        owner = body(source, 'CWinSystemGbm::GetLldvConnectorStatus() const')
        code = r'''
#include <cassert>
#include <drm_mode.h>
#include <memory>
#include <mutex>
#include <optional>
#include <string_view>
#include "utils/DVBridgeLldv.h"

using namespace DVBRIDGE;

struct Mode
{
  int hdisplay, vdisplay, clock, htotal, vtotal;
  int hsync_start, hsync_end, vsync_start, vsync_end, hskew, vscan;
  unsigned flags;
};
using drmModeModeInfo = Mode;
struct Connector
{
  uint32_t id=17;
  std::optional<uint64_t> active=0;
  bool connected=true;
  const Mode* advertised{};
  int GetModesCount() const { return advertised ? 1 : 0; }
  const Mode* GetModeForIndex(int index) const { return index == 0 ? advertised : nullptr; }
  uint32_t* GetConnectorId() { return &id; }
  bool IsConnected() const { return connected; }
  bool SupportsProperty(std::string_view key) const { return key=="CB1_LLDV_FORMAT"; }
  std::optional<uint64_t> GetPropertyEnumValue(std::string_view key, std::string_view name) const
  {
    assert(SupportsProperty(key));
    if (name=="YCbCr 4:2:2 10 useful bits") return 1;
    if (name=="YCbCr 4:2:2 12 bits") return 2;
    if (name=="YCbCr 4:2:2 10 bits forced") return 3;
    return {};
  }
  std::optional<uint64_t> ReadPropertyValue(std::string_view key) const
  {
    assert(SupportsProperty(key));
    return active;
  }
};
struct CDRMAtomic
{
  const Mode* mode{};
  Connector connector;
  bool active=true, pending=false, committed=false;
  Connector* GetConnector() { return &connector; }
  const Mode* GetSelectedMode() const { return mode; }
  bool IsActive() const { return active; }
  bool HasPendingCB1Page() const { return pending; }
  bool IsSelectedModeCommitted() const { return committed; }
};
struct Window
{
  std::shared_ptr<CDRMAtomic> m_DRM=std::make_shared<CDRMAtomic>();
  mutable std::mutex m_lldvEdidMutex;
  LldvDisplay m_lldvDisplay;
  uint32_t m_lldvEdidConnector=17;
  uint64_t m_lldvEdidGeneration=2;
  LldvTransport m_lldvRejected;
  LldvConnectorStatus Read() const OWNER
};

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
  Mode integer30 = fractional30;
  integer30.clock = 297000;
  Mode integer25 = integer;
  integer25.htotal = 5280;
  integer25.hsync_start = 4896;
  integer25.hsync_end = 4984;
  Mode fractional25 = integer25;
  fractional25.clock = 296703;
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
  Window window;
  window.m_lldvDisplay.sink.status=DV_EDID_LLDV_ONLY;
  window.m_lldvDisplay.sink.lldv_422=true;
  window.m_lldvDisplay.status=LldvEdidStatus::Ready;
  auto& drm=*window.m_DRM;
  const auto supported = [&](const Mode* mode) {
    drm.mode=mode;
    return window.Read().currentTiming;
  };
  assert(supported(&integer));
  assert(supported(&fractional));
  assert(supported(&fractional30));
  assert(supported(&integer30));
  assert(supported(&integer25));
  assert(!supported(&fractional25));
  assert(!supported(&integer60));
  assert(!supported(&wrongSync));
  assert(!supported(&interlaced));
  assert(supported(&widescreen));
  assert(!supported(&wrongAspect));
  assert(!supported(nullptr));
  drm.connector.advertised=&fractional;
  assert(!supported(&integer60) && window.Read().availableTiming);
  assert(!SelectLldvTransport(window.Read(), 0).connectorId);
  assert(SelectLldvTransport(window.Read(), 0, true).format==LldvFormat::Y422_10);
  assert(!SelectLldvTransport(window.Read(), int(LldvFormat::Rgb10), true).connectorId);
  drm.mode=&fractional;
  drm.connector.active=2;
  assert(window.Read().currentTiming && !window.Read().timingCommitted);
  drm.committed=true;
  drm.pending=true;
  assert(!window.Read().timingCommitted);
  drm.pending=false;
  auto readback=window.Read();
  assert(readback.timingCommitted && readback.active==LldvFormat::Y422_12);
  assert(readback.connectorId==17 && !readback.activeForced);
  assert(SelectLldvTransport(readback, 0).edidGeneration==2);
  window.m_lldvDisplay.status=LldvEdidStatus::Incomplete;
  assert(LldvUnavailableLabel(window.Read(), 0, true)==41226);
  assert(!SelectLldvTransport(window.Read(), 0).connectorId);
  window.m_lldvDisplay.status=LldvEdidStatus::Ready;
  ++window.m_lldvEdidGeneration;
  assert(SelectLldvTransport(window.Read(), 0).edidGeneration==3);
  drm.connector.active=3;
  readback=window.Read();
  assert(readback.active==LldvFormat::Y422_10 && readback.activeForced);
  readback.driverFormats &= ~LldvBit(LldvFormat::Y422_10);
  const auto chosen=SelectLldvTransport(readback, 0);
  assert(chosen.connectorId==17 && chosen.format==LldvFormat::Y422_10 && chosen.forced);
  drm.connector.active.reset();
  assert(window.Read().active==LldvFormat::Auto);
  drm.active=false;
  assert(!window.Read().timingCommitted);
  drm.active=true;
  drm.connector.connected=false;
  assert(!window.Read().timingCommitted && window.Read().connectorId==0);
}
'''.replace('OWNER', owner)
        with tempfile.TemporaryDirectory() as work:
            source = Path(work) / 'timing.cpp'
            binary = Path(work) / 'timing'
            source.write_text(code)
            libdrm = subprocess.check_output(['pkg-config', '--cflags', 'libdrm'], text=True).split()
            subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            '-I', str(kodi / 'xbmc'), *libdrm, str(source), '-o', str(binary)],
                           check=True)
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
  assert(LldvFormatReason(sink, LldvFormat::Y422_10, 0, true, true) == LldvReason::Ready);
  assert(LldvFormatReason(sink, LldvFormat::Y422_10, 0, false, true) == LldvReason::Timing);
  assert(LldvFormatReason(sink, LldvFormat::Y422_12, 0, true, true) == LldvReason::Driver);
  assert(ChooseLldvFormat(sink, LldvBit(LldvFormat::Y422_12), true, true) == LldvFormat::Y422_10);
  assert(ChooseLldvFormat(sink, LldvBit(LldvFormat::Y422_12), false, true) == LldvFormat::Auto);
  assert(LldvRequiresForcing(LldvFormat::Y422_10, 0, true));
  assert(!LldvRequiresForcing(LldvFormat::Y422_10, LLDV_422, true));
  assert(ChooseLldvFormat(sink, LLDV_422, true, true) == LldvFormat::Y422_10);

  cta[11] = 0xb5; // Low Latency only, with the extra HDMI interface.
  cta[13] |= 1;  // 10-bit 4:4:4.
  sink = caps();
  assert(sink.status == DV_EDID_LLDV_ONLY && dvbridge_lldv_422(sink));
  assert(dvbridge_lldv_444_bits(sink) == 10);
  assert(ChooseLldvFormat(sink, LldvBit(LldvFormat::Rgb10), true) == LldvFormat::Rgb10);
  assert(ChooseLldvFormat(sink, LldvBit(LldvFormat::Rgb10), true, true) == LldvFormat::Rgb10);
  assert(ChooseLldvFormat(sink, LldvBit(LldvFormat::Rgb12), true) == LldvFormat::Auto);
  cta[13] &= ~1;
  cta[12] |= 1; // 12-bit 4:4:4.
  sink = caps();
  assert(dvbridge_lldv_444_bits(sink) == 12);
  assert(ChooseLldvFormat(sink, LldvBit(LldvFormat::Y444_12), true) == LldvFormat::Y444_12);
  cta[12] &= ~1;
  cta[9] = 0x20; // Short V1 with the LL bit clear, then set.
  sink = caps();
  assert(!dvbridge_lldv_422(sink));
  assert(LldvFormatReason(sink, LldvFormat::Y422_10, 0, true, true) == LldvReason::Display);
  assert(ChooseLldvFormat(sink, 0, true, true) == LldvFormat::Auto);
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
