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
        owner = body(source, 'CWinSystemGbm::GetLldvConnectorStatus(bool snapshot) const')
        timing = body(source, 'int LldvTimingIndex(')
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
int LldvTimingIndex(const drmModeModeInfo* mode, bool cta93FractionalOnly = false) TIMING
struct Connector
{
  uint32_t id=17;
  std::optional<uint64_t> active=0;
  bool connected=true;
  bool cta93FractionalOnly=false;
  bool r615=false;
  bool r615Native16=false;
  std::optional<uint64_t> nativeFormats;
  uint64_t acceptedNativeFormat=0;
  bool nativeLldvActive=true;
  bool r580=false;
  bool r580Native10=false;
  bool intelNativeRgb10=false;
  bool amdNative444=false;
  const Mode* advertised{};
  const Mode* alternate{};
  int GetModesCount() const { return alternate ? 2 : advertised ? 1 : 0; }
  const Mode* GetModeForIndex(int index) const { return index == 0 ? advertised : alternate; }
  uint32_t* GetConnectorId() { return &id; }
  bool IsConnected() const { return connected; }
  std::string_view GetType() const { return "HDMI-A"; }
  bool SupportsProperty(std::string_view key) const
  {
    return key=="CB1_LLDV_FORMAT" || (nativeFormats && key=="CB1_NATIVE_LLDV_FORMATS") ||
        (r615 && key=="CB1_NATIVE_LLDV_ACTIVE") ||
        (r580 && (key=="CB1_NATIVE_LLDV_422" || key=="CB1_NATIVE_LLDV_ACTIVE"));
  }
  std::optional<uint64_t> GetPropertyValue(std::string_view key) const
  {
    assert(key=="CB1_LLDV_CTA93_23976_ONLY");
    return cta93FractionalOnly ? std::optional<uint64_t>(1) : std::nullopt;
  }
  std::optional<uint64_t> GetPropertyEnumValue(std::string_view key, std::string_view name) const
  {
    assert(SupportsProperty(key));
    if (r615)
    {
      if (name=="YCbCr 4:2:2 10 bits forced") return 1;
      if (name=="YCbCr 4:2:2 12 bits packed") return 2;
      if (name=="YCbCr 4:2:2 12 bits RGB16" && r615Native16) return 3;
      if (nativeFormats)
      {
        if (name=="RGB 12 bits RGB16") return 4;
        if (name=="YCbCr 4:4:4 10 bits RGB10") return 5;
        if (name=="YCbCr 4:4:4 12 bits RGB16") return 6;
        if (name=="YCbCr 4:2:2 10 bits RGB10 lab") return 7;
        if (name=="RGB 10 bits RGB10") return 8;
      }
      return {};
    }
    if (r580)
    {
      if (name=="YCbCr 4:2:2 10 bits RGB10 lab") return 2;
      if (name=="YCbCr 4:2:2 10 bits forced") return 1;
      return {};
    }
    if (amdNative444)
    {
      if (name=="YCbCr 4:2:2 10 bits RGB10 lab") return 3;
      if (name=="YCbCr 4:4:4 10 bits RGB10") return 4;
      if (name=="YCbCr 4:2:2 10 bits forced") return 1;
      return {};
    }
    if (intelNativeRgb10)
    {
      if (name=="RGB 10 bits RGB10") return 3;
      if (name=="YCbCr 4:2:2 10 bits forced") return 1;
      return {};
    }
    if (name=="YCbCr 4:2:2 10 useful bits") return 1;
    if (name=="YCbCr 4:2:2 12 bits") return 2;
    if (name=="YCbCr 4:2:2 10 bits forced") return 3;
    return {};
  }
  std::optional<uint64_t> ReadPropertyValue(std::string_view key) const
  {
    if (key=="CB1_NATIVE_LLDV_FORMATS") return nativeFormats;
    if (key=="CB1_NATIVE_LLDV_ACTIVE")
      return nativeFormats ? acceptedNativeFormat : nativeLldvActive ? 1 : 0;
    if (key=="CB1_NATIVE_LLDV_422") return r580Native10 ? 1 : 0;
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
  std::array<unsigned, 10> m_lldvRejectedTimings{};
  bool usableRgb16{};
  bool HasLldvRgb16Scanout() const { return usableRgb16; }
  bool HasLldvRgb10Scanout() const { return true; }
  LldvConnectorStatus Read(bool snapshot = false) const OWNER
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
  drm.connector.cta93FractionalOnly=true;
  assert(supported(&fractional));
  assert(!supported(&integer));
  assert(!supported(&integer25));
  assert(!supported(&fractional30));
  drm.connector.advertised=&integer;
  assert(!window.Read().availableTiming);
  drm.connector.advertised=&fractional;
  assert(window.Read().availableTiming);
  drm.connector.cta93FractionalOnly=false;
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

  // One wire format at 23.976 cannot invalidate 24, 25, or either 30 Hz timing.
  const auto native10 = SelectLldvTransport(readback, 0);
  const auto native12 = SelectLldvTransport(readback, int(LldvFormat::Y422_12));
  window.m_lldvRejectedTimings[LldvTimingIndex(&fractional)] = LldvTransportBit(native10);
  assert(LldvUnavailableLabel(window.Read(), int(LldvFormat::Y422_10), false) ==
         LLDV_DRIVER_REJECTED_LABEL);
  assert(SelectLldvTransport(window.Read(), 0).format == LldvFormat::Y422_12);
  window.m_lldvRejectedTimings[LldvTimingIndex(&fractional)] |= LldvTransportBit(native12);
  assert(LldvUnavailableLabel(window.Read(), 0, true) == LLDV_DRIVER_REJECTED_LABEL);
  assert(!SelectLldvTransport(window.Read(), 0).connectorId);
  const std::array<const Mode*, 5> unaffected{
      &integer, &integer25, &integer30, &fractional30, &widescreen};
  for (const auto* other : unaffected)
  {
    drm.mode = other;
    assert(SelectLldvTransport(window.Read(), 0).format == LldvFormat::Y422_10);
  }
  drm.mode = &integer60;
  drm.connector.alternate = &integer;
  assert(SelectLldvTransport(window.Read(), 0, true).format == LldvFormat::Y422_10);
  const auto snapshot = window.Read(true);
  assert(snapshot.modeRejections.size() == 2 && snapshot.modeRejections[0].first == 0);
  assert(snapshot.modeRejections[0].second == (LldvTransportBit(native10) | LldvTransportBit(native12)));
  assert(snapshot.modeRejections[1].first == 1 && snapshot.modeRejections[1].second == 0);
  drm.mode = &fractional;
  auto withAlternateCarrier = window.Read();
  withAlternateCarrier.rgb10Scanout = true;
  assert(SelectLldvTransport(withAlternateCarrier, 0).rgbScanoutBits == 10);
  withAlternateCarrier.currentRejected |= LldvTransportBit(SelectLldvTransport(withAlternateCarrier, 0));
  assert(!SelectLldvTransport(withAlternateCarrier, 0).connectorId);
  assert(SelectLldvTransport(withAlternateCarrier, LLDV_FORCE_422_10).forced);
  auto withForcedCarrier = window.Read();
  withForcedCarrier.driverFormats = 0;
  assert(!SelectLldvTransport(withForcedCarrier, 0).connectorId);
  assert(SelectLldvTransport(withForcedCarrier, LLDV_FORCE_422_10).forced);
  ++drm.connector.id;
  assert(!SelectLldvTransport(window.Read(), 0).connectorId);
  window.m_lldvEdidConnector = drm.connector.id;
  window.m_lldvRejectedTimings = {};
  assert(SelectLldvTransport(window.Read(), 0).format == LldvFormat::Y422_10);
  drm.connector.id = window.m_lldvEdidConnector = 17;
  window.m_lldvDisplay.status=LldvEdidStatus::Incomplete;
  assert(LldvUnavailableLabel(window.Read(), 0, true)==41281);
  assert(!SelectLldvTransport(window.Read(), 0).connectorId);
  window.m_lldvDisplay.status=LldvEdidStatus::Ready;
  ++window.m_lldvEdidGeneration;
  assert(SelectLldvTransport(window.Read(), 0).edidGeneration==3);
  drm.connector.active=3;
  readback=window.Read();
  assert(readback.active==LldvFormat::Y422_10 && readback.activeForced);
  readback.driverFormats &= ~LldvBit(LldvFormat::Y422_10);
  assert(SelectLldvTransport(readback, 0).format==LldvFormat::Y422_12);
  const auto chosen=SelectLldvTransport(readback, LLDV_FORCE_422_10);
  assert(chosen.connectorId==17 && chosen.format==LldvFormat::Y422_10 && chosen.forced);
  drm.connector.r615=true;
  drm.connector.active=2;
  readback=window.Read();
  assert(readback.packed42212 && readback.forced42210);
  assert(readback.active==LldvFormat::Y422_12 && !readback.activeForced);
  assert(readback.driverFormats==LldvBit(LldvFormat::Y422_12));
  assert(!SelectLldvTransport(readback, 0).connectorId);
  assert(LldvUnavailableLabel(readback, int(LldvFormat::Y422_12), false)==41210);
  window.m_lldvDisplay.sink.lldv_422_12=true;
  assert(LldvUnavailableLabel(window.Read(), int(LldvFormat::Y422_12), false)==LLDV_CHOOSE_FORMAT_LABEL);
  assert(SelectLldvTransport(window.Read(), LLDV_PACKED_422_12).format==LldvFormat::Y422_12);
  drm.connector.active=1;
  assert(window.Read().active==LldvFormat::Y422_10 && window.Read().activeForced);

  drm.connector.r615Native16=true;
  assert(window.Read().packed42212);
  window.usableRgb16=true;
  readback=window.Read();
  assert(!readback.packed42212 && readback.rgb16Scanout);
  assert(SelectLldvTransport(readback, 0).rgbScanoutBits==16);
  assert(SelectLldvTransport(readback, LLDV_FORCE_422_10).forced);
  window.m_lldvDisplay.sink.lldv_422_12=false;
  assert(!SelectLldvTransport(window.Read(), 0).connectorId);
  assert(LldvUnavailableLabel(window.Read(), int(LldvFormat::Y422_12), false)==41210);
  window.m_lldvDisplay.sink.lldv_422_12=true;
  drm.connector.active=3;
  assert(window.Read().active==LldvFormat::Y422_12);
  assert(window.Read().activeRgbScanoutBits==16);
  drm.connector.nativeLldvActive=false;
  assert(window.Read().active==LldvFormat::Auto);

  drm.connector.nativeFormats=(1ULL<<4) | (1ULL<<5) | (1ULL<<6);
  window.m_lldvDisplay.sink.lldv_444_bits=12;
  readback=window.Read();
  assert(readback.packed42212 && !readback.rgb16Scanout);
  assert(SelectLldvTransport(readback, 0).format==LldvFormat::Rgb12);
  assert(SelectLldvTransport(readback, 0).rgbScanoutBits==16);
  assert(SelectLldvTransport(readback, int(LldvFormat::Y444_12)).rgbScanoutBits==16);
  assert(!SelectLldvTransport(readback, int(LldvFormat::Y444_10)).connectorId);
  drm.connector.active=4;
  drm.connector.acceptedNativeFormat=6;
  assert(window.Read().active==LldvFormat::Auto);
  drm.connector.acceptedNativeFormat=4;
  assert(window.Read().active==LldvFormat::Rgb12);
  window.usableRgb16=false;
  assert(LldvUnavailableLabel(window.Read(), int(LldvFormat::Rgb12), false)==41211);
  window.m_lldvDisplay.sink.lldv_444_bits=10;
  assert(SelectLldvTransport(window.Read(), 0).format==LldvFormat::Y444_10);
  assert(SelectLldvTransport(window.Read(), 0).rgbScanoutBits==10);
  assert(SelectLldvTransport(window.Read(), LLDV_FORCE_422_10).forced);
  *drm.connector.nativeFormats|=1ULL<<7;
  assert(SelectLldvTransport(window.Read(), 0).format==LldvFormat::Y422_10);
  assert(!SelectLldvTransport(window.Read(), LLDV_FORCE_422_10).forced);
  drm.connector.nativeFormats.reset();

  drm.connector.r615=false;
  drm.connector.intelNativeRgb10=true;
  window.m_lldvDisplay.sink.lldv_444_bits=10;
  drm.connector.active=3;
  readback=window.Read();
  assert(readback.active==LldvFormat::Rgb10 && readback.activeRgbScanoutBits==10);
  assert(SelectLldvTransport(readback, 0).format==LldvFormat::Rgb10);
  assert(SelectLldvTransport(readback, 0).rgbScanoutBits==10);
  assert(SelectLldvTransport(readback, LLDV_FORCE_422_10).forced);
  window.m_lldvDisplay.sink.lldv_444_bits=12;
  assert(LldvUnavailableLabel(window.Read(), int(LldvFormat::Rgb10), false)==41210);

  drm.connector.intelNativeRgb10=false;
  drm.connector.r580=true;
  assert(!SelectLldvTransport(window.Read(), 0).connectorId);
  assert(SelectLldvTransport(window.Read(), LLDV_FORCE_422_10).forced);
  drm.connector.r580Native10=true;
  assert(SelectLldvTransport(window.Read(), 0).rgbScanoutBits==10);
  assert(!SelectLldvTransport(window.Read(), LLDV_FORCE_422_10).forced);
  drm.connector.active=2;
  assert(window.Read().active==LldvFormat::Auto);
  drm.connector.nativeLldvActive=true;
  assert(window.Read().active==LldvFormat::Y422_10 && window.Read().activeRgbScanoutBits==10);

  drm.connector.r580=false;
  drm.connector.amdNative444=true;
  drm.connector.nativeFormats=(1ULL<<3) | (1ULL<<4);
  window.m_lldvDisplay.sink.lldv_444_bits=10;
  drm.connector.active=4;
  readback=window.Read();
  assert(readback.active==LldvFormat::Y444_10 && readback.activeRgbScanoutBits==10);
  assert(SelectLldvTransport(readback, 0).format==LldvFormat::Y422_10);
  assert(SelectLldvTransport(readback, int(LldvFormat::Y444_10)).format==LldvFormat::Y444_10);
  *drm.connector.nativeFormats&=~(1ULL<<4);
  assert(LldvUnavailableLabel(window.Read(), int(LldvFormat::Y444_10), false)==41211);

  drm.connector.active.reset();
  assert(window.Read().active==LldvFormat::Auto);
  drm.active=false;
  assert(!window.Read().timingCommitted);
  drm.active=true;
  drm.connector.connected=false;
  assert(!window.Read().timingCommitted && window.Read().connectorId==0);
}
'''.replace('OWNER', owner).replace('TIMING', timing)
        with tempfile.TemporaryDirectory() as work:
            source = Path(work) / 'timing.cpp'
            binary = Path(work) / 'timing'
            source.write_text(code)
            libdrm = subprocess.check_output(['pkg-config', '--cflags', 'libdrm'], text=True).split()
            subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            '-I', str(kodi / 'xbmc'), *libdrm, str(source), '-o', str(binary)],
                           check=True)
            subprocess.run([binary], check=True)

    def test_resolution_prefers_an_unrefused_exact_kodi_mode(self):
        from test_native_video_source import body
        from test_process_info_metadata import run

        kodi = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        source = (kodi / 'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        choose = body(source, 'CWinSystemGbmGLESContext::PlayerLedResolution(')
        reason = body(source, 'CWinSystemGbmGLESContext::PlayerLedResolutionReason(')
        program = r'''
#include "utils/DVBridgeLldv.h"
#include <algorithm>
#include <cassert>
#include <charconv>
#include <mutex>
#include <optional>
#include <string>
using RESOLUTION = int;
constexpr RESOLUTION RES_INVALID=-1, RES_DESKTOP=0;
constexpr unsigned D3DPRESENTFLAG_MODEMASK=1;
struct Mode
{
  std::string strId;
  double fRefreshRate{};
  int iWidth=3840, iHeight=2160, iScreenWidth=3840, iScreenHeight=2160;
  unsigned dwFlags{};
};
struct CDisplaySettings
{
  std::vector<Mode> modes;
  static CDisplaySettings& GetInstance(){static CDisplaySettings settings;return settings;}
  size_t ResolutionInfoSize() const{return modes.size();}
  const Mode& GetResolutionInfo(RESOLUTION index) const{return modes.at(index);}
};
namespace DVBRIDGE
{
enum class OutputMode{PlayerLed};
struct Preferences
{
  OutputMode output=OutputMode::PlayerLed;
  bool hdr10TransportFallback{};
  int lldvFormat{};
} preferences;
Preferences FrameOutputSettings(){return preferences;}
}
struct Window
{
  DVBRIDGE::LldvConnectorStatus m_dvLldvStatus;
  mutable std::mutex m_dvCapabilityMutex;
  struct Caps{bool playerLed=true;};
  Caps GetDVOutputCapabilities(void*,const DVBRIDGE::Preferences&,bool) const{return {};}
  bool LldvSupportsPlaybackTiming(double) const{return true;}
  std::optional<RESOLUTION> Choose(double fps,bool atStartup=false) const CHOOSE_BODY
  int PlayerLedResolutionReason(RESOLUTION resolution,int preference) const REASON_BODY
};

int main()
{
  using namespace DVBRIDGE;
  constexpr double film=24000.0/1001;
  CDisplaySettings::GetInstance().modes={{"0",60},{"",film},{"4",film},{"5",film},{"6",24}};
  Window window;
  auto& status=window.m_dvLldvStatus;
  status.display.status=LldvEdidStatus::Ready;
  status.sink.status=DV_EDID_LLDV_ONLY;
  status.sink.lldv_422=true;
  status.connectorId=403;
  status.driverFormats=LLDV_422;
  status.currentTiming=false;
  status.availableTiming=true;
  const auto ten=LldvTransportBit({403,LldvFormat::Y422_10});
  const auto twelve=LldvTransportBit({403,LldvFormat::Y422_12});
  status.modeRejections={{4,ten|twelve},{6,0}};
  assert(!window.Choose(film));
  assert(window.Choose(film,true)==2);
  assert(window.Choose(24)==4);
  assert(window.PlayerLedResolutionReason(2,0)==LLDV_DRIVER_REJECTED_LABEL);
  assert(window.PlayerLedResolutionReason(4,0)==0);
  assert(window.PlayerLedResolutionReason(1,0)!=LLDV_DRIVER_REJECTED_LABEL);
  status.modeRejections.emplace_back(5,0);
  assert(window.Choose(film,true)==3);
  status.modeRejections.front().second=ten;
  assert(window.Choose(film)==2);
  preferences.lldvFormat=static_cast<int>(LldvFormat::Y422_10);
  assert(window.Choose(film)==3);
  status.currentTiming=true;
  status.currentRejected=ten;
  assert(window.PlayerLedResolutionReason(RES_INVALID,preferences.lldvFormat)==LLDV_DRIVER_REJECTED_LABEL);
  preferences.hdr10TransportFallback=true;
  assert(!window.Choose(film,true));
}
'''.replace('CHOOSE_BODY', choose).replace('REASON_BODY', reason)
        run(self, {'test.cpp': program})

    def test_menu_keeps_live_forced_format_when_auto_is_unavailable(self):
        from test_process_info_metadata import run
        from test_native_video_source import body

        kodi = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        menu = body((kodi / 'xbmc/dialogs/DVPlaybackModes.cpp').read_text(),
                    'bool ShowLldvFormatMenu(bool forCircuit, bool inPlayback)\n')
        self.assertIn('i <= static_cast<int>(LldvFormat::Y444_12)', menu)
        self.assertIn('selected <= LldvFormat::Y444_12', menu)
        self.assertIn('dvbridge_lldv_444_bits(display.sink)', menu)
        self.assertIn('SelectLldvTransport(status, 0, allowModeSwitch)', menu)
        start = menu.index('  const int choice = dialog->GetSelectedItem();')
        finish = menu.index('  return true;', start) + len('  return true;')
        program = r'''
#include "utils/DVBridgeLldv.h"
#include <cassert>

using namespace DVBRIDGE;

struct Dialog
{
  int choice{};
  bool confirmed{true};
  int GetSelectedItem() const { return choice; }
  bool IsConfirmed() const { return confirmed; }
};

struct Settings
{
  int stored{LLDV_FORCE_422_10};
  bool SetInt(const char*, int value) { stored = value; return true; }
  void Save() {}
};

bool Confirm(const Dialog* dialog, Settings* settings, bool forCircuit,
             const LldvConnectorStatus& status, const LldvConnectorStatus& current,
             bool inPlayback = false)
{
  const bool allowModeSwitch = !inPlayback && status.active == LldvFormat::Auto;
  PREFERENCES
  CONFIRM
}

int main()
{
  LldvConnectorStatus current{};
  current.connectorId = 17;
  current.edidGeneration = 2;
  current.display.status = LldvEdidStatus::Ready;
  current.sink.status = DV_EDID_LLDV_ONLY;
  current.sink.lldv_422 = true;
  current.currentTiming = true;
  current.forced42210 = true;
  current.active = LldvFormat::Y422_10;
  Dialog dialog;
  Settings settings;
  assert(!Confirm(&dialog, &settings, false, current, current));
  assert(settings.stored == LLDV_FORCE_422_10);
  current.active = LldvFormat::Auto;
  assert(!Confirm(&dialog, &settings, true, current, current));
  assert(Confirm(&dialog, &settings, false, current, current));
  assert(settings.stored == 0);
  dialog.choice = static_cast<int>(LldvFormat::Y422_10);
  dialog.confirmed = false;
  assert(!Confirm(&dialog, &settings, true, current, current));
  dialog.confirmed = true;
  auto changed = current;
  ++changed.edidGeneration;
  assert(!Confirm(&dialog, &settings, true, current, changed));
  assert(settings.stored == 0);
  assert(Confirm(&dialog, &settings, true, current, current));
  assert(settings.stored == LLDV_FORCE_422_10);
  current.currentRejected = LldvTransportBit(SelectLldvTransport(current, LLDV_FORCE_422_10));
  current.availableTiming = true;
  assert(!Confirm(&dialog, &settings, true, current, current, true));
  assert(Confirm(&dialog, &settings, true, current, current));
  dialog.choice = 0;
  assert(Confirm(&dialog, &settings, false, {}, {}));
  assert(settings.stored == 0);
}
'''.replace('CONFIRM', menu[start:finish]).replace('PREFERENCES',
    menu[menu.index('  const auto requiresForcing'):menu.index('  const auto saved')])
        run(self, {'test.cpp': program})

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
  assert(!dvbridge_lldv_422_12(sink));
  cta[9] |= 1;
  assert(dvbridge_lldv_422_12(caps()));
  cta[9] &= ~1;
  assert(dvbridge_lldv_444_bits(sink) == 0);
  assert(LldvFormatReason(sink, LldvFormat::Y422_10, 0, true) == LldvReason::Driver);
  assert(LldvFormatReason(sink, LldvFormat::Rgb10, LLDV_422, true) == LldvReason::Display);
  assert(LldvFormatReason(sink, LldvFormat::Y422_12, LLDV_422, false) == LldvReason::Timing);
  assert(ChooseLldvFormat(sink, LLDV_422, true) == LldvFormat::Y422_10);
  assert(ChooseLldvFormat(sink, 0, true) == LldvFormat::Auto);
  assert(LldvFormatReason(sink, LldvFormat::Y422_10, 0, true, true) == LldvReason::Ready);
  assert(LldvFormatReason(sink, LldvFormat::Y422_10, 0, false, true) == LldvReason::Timing);
  assert(LldvFormatReason(sink, LldvFormat::Y422_12, 0, true, true) == LldvReason::Driver);
  assert(ChooseLldvFormat(sink, LldvBit(LldvFormat::Y422_12), true) == LldvFormat::Y422_12);
  assert(ChooseLldvFormat(sink, LldvBit(LldvFormat::Y422_12), false) == LldvFormat::Auto);
  assert(LldvRequiresForcing(LldvFormat::Y422_10, 0, true));
  assert(!LldvRequiresForcing(LldvFormat::Y422_10, LLDV_422, true));
  assert(ChooseLldvFormat(sink, LLDV_422, true) == LldvFormat::Y422_10);
  LldvConnectorStatus forcedOnly{};
  forcedOnly.connectorId = 1;
  forcedOnly.sink = sink;
  forcedOnly.currentTiming = true;
  forcedOnly.display.status = LldvEdidStatus::Ready;
  forcedOnly.forced42210 = true;
  assert(!SelectLldvTransport(forcedOnly, 0).connectorId);
  assert(!SelectLldvTransport(forcedOnly, int(LldvFormat::Y422_10)).connectorId);
  auto selected = SelectLldvTransport(forcedOnly, LLDV_FORCE_422_10);
  assert(selected.connectorId && selected.format == LldvFormat::Y422_10 && selected.forced);
  auto native12 = forcedOnly;
  native12.driverFormats = LldvBit(LldvFormat::Y422_12);
  assert(SelectLldvTransport(native12, 0).format == LldvFormat::Y422_12);
  auto packed12 = native12;
  packed12.packed42212 = true;
  assert(LldvUnavailableLabel(packed12, int(LldvFormat::Y422_12), false) == 41210);
  assert(!SelectLldvTransport(packed12, 0).connectorId);
  assert(SelectLldvTransport(packed12, LLDV_FORCE_422_10).forced);
  cta[9] |= 1;
  packed12.sink = caps();
  assert(!SelectLldvTransport(packed12, 0).connectorId);
  assert(!SelectLldvTransport(packed12, int(LldvFormat::Y422_12)).connectorId);
  assert(LldvCanChooseFormat(packed12, false));
  selected = SelectLldvTransport(packed12, LLDV_PACKED_422_12);
  assert(selected.connectorId && selected.format == LldvFormat::Y422_12 && !selected.forced);
  packed12.driverFormats = LLDV_422;
  assert(SelectLldvTransport(packed12, 0).format == LldvFormat::Y422_10);
  cta[9] &= ~1;
  auto native10 = forcedOnly;
  native10.driverFormats = LLDV_422;
  selected = SelectLldvTransport(native10, LLDV_FORCE_422_10);
  assert(selected.connectorId && !selected.forced);
  forcedOnly.currentTiming = false;
  assert(!SelectLldvTransport(forcedOnly, LLDV_FORCE_422_10, true).connectorId);
  forcedOnly.availableTiming = true;
  assert(SelectLldvTransport(forcedOnly, LLDV_FORCE_422_10, true).forced);
  forcedOnly.display.status = LldvEdidStatus::Incomplete;
  assert(!SelectLldvTransport(forcedOnly, LLDV_FORCE_422_10, true).connectorId);


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

  // A failed 4:2:2 carrier must leave the two full-chroma formats available.
  auto multiple = native12;
  multiple.sink = sink;
  multiple.driverFormats = LldvBit(LldvFormat::Y422_12) |
      LldvBit(LldvFormat::Rgb12) | LldvBit(LldvFormat::Y444_12);
  auto transport = SelectLldvTransport(multiple, 0);
  assert(transport.format == LldvFormat::Y422_12);
  multiple.currentRejected |= LldvTransportBit(transport);
  transport = SelectLldvTransport(multiple, 0);
  assert(transport.format == LldvFormat::Rgb12 && transport.rgbScanoutBits == 16);
  multiple.currentRejected |= LldvTransportBit(transport);
  assert(SelectLldvTransport(multiple, 0).format == LldvFormat::Y444_12);
  assert(LldvTransportBit({7,LldvFormat::Y422_12,false,3,8}) !=
         LldvTransportBit({7,LldvFormat::Y422_12,false,3,8,true}));
  assert(!(LldvTransport{7,LldvFormat::Y422_12,false,3,8,true} ==
           LldvTransport{7,LldvFormat::Y422_12,false,3,16,false}));
  assert(!(LldvTransport{7,LldvFormat::Y422_10,false,3,8,false} ==
           LldvTransport{7,LldvFormat::Y422_10,false,3,10,false}));
  packed12.driverFormats = LldvBit(LldvFormat::Y422_12);
  packed12.currentRejected = LldvTransportBit(SelectLldvTransport(packed12, LLDV_PACKED_422_12));
  assert(LldvUnavailableLabel(packed12, LLDV_PACKED_422_12, false) == LLDV_DRIVER_REJECTED_LABEL);
  assert(!SelectLldvTransport(packed12, 0).connectorId);
  cta[12] &= ~1;
  cta[9] = 0x20; // Short V1 with the LL bit clear, then set.
  sink = caps();
  assert(!dvbridge_lldv_422(sink));
  assert(LldvFormatReason(sink, LldvFormat::Y422_10, 0, true, true) == LldvReason::Display);
  assert(ChooseLldvFormat(sink, 0, true) == LldvFormat::Auto);
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
