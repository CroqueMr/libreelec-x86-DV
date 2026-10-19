# SPDX-License-Identifier: MIT
"""Execute the shipped stereo selector and original kernel mode-table patch."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
KODI_PATCH = ROOT / "projects/Generic/patches/kodi/kodi-9999-zz-beta3.patch"
EDID_PATCH = ROOT / "projects/Generic/patches/linux/0101-drm-edid-add-half-sbs-1080p-stereo-modes.patch"


def added_source():
    section = KODI_PATCH.read_text().split("+++ b/xbmc/windowing/Resolution.cpp\n", 1)[1]
    section = section.split("\n--- a/", 1)[0]
    return "\n".join(line[1:] for line in section.splitlines()
                     if line.startswith("+") and not line.startswith("+++")) + "\n"


def function(source, signature):
    start = source.index(signature)
    end = source.index("\n}\n", start) + 3
    return source[start:end]


STUBS = r'''
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <ranges>
#include <string>
#include <utility>
#include <vector>
using RESOLUTION = int;
constexpr int RES_INVALID = -1, LOGDEBUG = 0;
constexpr uint32_t D3DPRESENTFLAG_MODE3DSBS = 1, D3DPRESENTFLAG_MODE3DTB = 2;
constexpr uint32_t D3DPRESENTFLAG_INTERLACED = 4;
constexpr float STEREO_FULL_SBS_MIN_ASPECT = 2.4f, STEREO_FULL_TAB_MAX_ASPECT = 1.3f;
enum class RenderStereoMode { MONO, SPLIT_VERTICAL, SPLIT_HORIZONTAL };
struct RESOLUTION_INFO { int iScreenWidth, iScreenHeight, iBlanking; float fRefreshRate; uint32_t dwFlags; std::string strMode; };
struct CVariant { int id; std::string asString() const { return std::to_string(id); } };
struct CDisplaySettings {
  static inline std::vector<RESOLUTION_INFO> modes;
  static CDisplaySettings& GetInstance() { static CDisplaySettings s; return s; }
  const RESOLUTION_INFO& GetResolutionInfo(int id) const { return modes.at(id); }
  int GetResFromString(const std::string& id) const { return std::stoi(id); }
  int GetCurrentResolution() const { return 0; }
};
struct Context {
  void GetAllowedResolutions(std::vector<int>& out) const {
    for (size_t i = 0; i < CDisplaySettings::modes.size(); ++i) out.push_back(i);
  }
  const RESOLUTION_INFO& GetResInfo(int id) const { return CDisplaySettings::modes.at(id); }
  int GetVideoResolution() const { return 0; }
};
using CGraphicContext = Context;
struct Window { Context context; Context& GetGfxContext() { return context; } };
struct CSettings { static constexpr const char* SETTING_VIDEOSCREEN_WHITELIST = "whitelist"; };
struct Settings {
  std::vector<CVariant> whitelist;
  auto GetList(const char*) const { return whitelist; }
};
struct Advanced { bool m_stereoscopicPreferFramePacking = true; };
struct SettingsComponent {
  Settings settings; Advanced advanced;
  auto* GetSettings() { return &settings; }
  auto* GetAdvancedSettings() { return &advanced; }
};
struct CServiceBroker {
  static inline Window window;
  static inline SettingsComponent settings;
  static auto* GetWinSystem() { return &window; }
  static auto* GetSettingsComponent() { return &settings; }
};
struct MathUtils { static bool FloatEquals(float a, float b, float tolerance) { return std::abs(a - b) <= tolerance; } };
struct CLog { template<class... T> static void Log(T&&...) {} };
class CResolutionUtils {
public:
  static RenderStereoMode ChooseStereoArrangement(RenderStereoMode, float, int, int);
};
'''


class StereoUpstreamTests(unittest.TestCase):
    def test_selector_preserves_upstream_stereo_and_30_to_60_matching(self):
        source = added_source()
        structure = source[source.index("struct StereoMatch\n"):]
        structure = structure[:structure.index("\n};") + 3]
        signatures = ["uint32_t StereoFlagFor(", "void PerEyeSize(",
                      "const RESOLUTION_INFO& NativeModeInfo(",
                      "std::pair<int, int> BaseGeometry(", "bool SameTiming(",
                      "std::vector<RESOLUTION> Find3DCandidates(",
                      "std::vector<float> StereoRefreshTiers(",
                      "const char* StereoTierName(", "bool PreferFramePacking(",
                      "bool BetterMatch(", "StereoMatch FindNative3DMode(",
                      "RenderStereoMode CResolutionUtils::ChooseStereoArrangement("]
        code = STUBS + "\nconstexpr uint32_t STEREO_FLAGS = 3;\n" + structure + "\n"
        code += "\n".join(function(source, signature) for signature in signatures)
        code += r'''
int main() {
  using Mode = RenderStereoMode;
  CDisplaySettings::modes = {{3840,2160,0,30,0}};
  // No native layout must retain the requested stereo arrangement for manual 3D.
  assert(CResolutionUtils::ChooseStereoArrangement(Mode::SPLIT_VERTICAL,30,3840,2160) == Mode::SPLIT_VERTICAL);
  assert(CResolutionUtils::ChooseStereoArrangement(Mode::SPLIT_HORIZONTAL,30,3840,2160) == Mode::SPLIT_HORIZONTAL);
  assert(CResolutionUtils::ChooseStereoArrangement(Mode::MONO,30,3840,2160) == Mode::MONO);
  CDisplaySettings::modes.push_back({1920,2205,45,24,D3DPRESENTFLAG_MODE3DTB});
  CDisplaySettings::modes.push_back({1920,1080,0,60,D3DPRESENTFLAG_MODE3DSBS});
  // A 4K30 half-SBS source may downscale to the display's native 1080p60 3D mode.
  assert(CResolutionUtils::ChooseStereoArrangement(Mode::SPLIT_HORIZONTAL,30,3840,2160) == Mode::SPLIT_VERTICAL);
  auto candidates = Find3DCandidates({},true,3840,2160,CDisplaySettings::modes[0]);
  assert(FindNative3DMode(candidates,D3DPRESENTFLAG_MODE3DSBS,StereoRefreshTiers(30)).resolution == 2);
  // MVC/full-SBS at 24 fps prefers frame packing; its active-space gap is not an eye.
  assert(CResolutionUtils::ChooseStereoArrangement(Mode::SPLIT_VERTICAL,24,3840,1080) == Mode::SPLIT_HORIZONTAL);
  CServiceBroker::settings.settings.whitelist = {{0}};
  assert(CResolutionUtils::ChooseStereoArrangement(Mode::SPLIT_VERTICAL,30,3840,2160) == Mode::SPLIT_VERTICAL);
  CServiceBroker::settings.settings.whitelist = {{2}};
  assert(CResolutionUtils::ChooseStereoArrangement(Mode::SPLIT_HORIZONTAL,30,3840,2160) == Mode::SPLIT_VERTICAL);
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "selector.cpp").write_text(code)
            subprocess.run(["c++", "-std=c++20", str(path / "selector.cpp"),
                            "-o", str(path / "selector")], check=True)
            result = subprocess.run([str(path / "selector")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_original_edid_patch_adds_progressive_1080p_sbs_modes(self):
        self.assertTrue(EDID_PATCH.is_file(), "Original cinemaONE 0101 patch is missing")
        fixture = '''struct stereo_mandatory_mode { int width, height, vrefresh; unsigned flags; };
static const struct stereo_mandatory_mode stereo_mandatory_modes[] = {
\t{ 1920, 1080, 24, DRM_MODE_FLAG_3D_TOP_AND_BOTTOM },
\t{ 1920, 1080, 24, DRM_MODE_FLAG_3D_FRAME_PACKING },
\t{ 1920, 1080, 50,
\t  DRM_MODE_FLAG_INTERLACE | DRM_MODE_FLAG_3D_SIDE_BY_SIDE_HALF },
\t{ 1920, 1080, 60,
\t  DRM_MODE_FLAG_INTERLACE | DRM_MODE_FLAG_3D_SIDE_BY_SIDE_HALF }
};
'''
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            target = path / "drivers/gpu/drm/drm_edid.c"
            target.parent.mkdir(parents=True)
            target.write_text(fixture)
            subprocess.run(["patch", "--batch", "--fuzz=0", "-p1", "-i", str(EDID_PATCH)],
                           cwd=path, check=True, capture_output=True)
            code = '''#include <assert.h>
#define DRM_MODE_FLAG_INTERLACE 16
#define DRM_MODE_FLAG_3D_TOP_AND_BOTTOM (7 << 14)
#define DRM_MODE_FLAG_3D_FRAME_PACKING (1 << 14)
#define DRM_MODE_FLAG_3D_SIDE_BY_SIDE_HALF (8 << 14)
#include "drivers/gpu/drm/drm_edid.c"
int main(void) {
  const int rates[] = {24,50,60};
  for (int r=0; r<3; ++r) {
    int matches=0;
    for (unsigned i=0; i<sizeof(stereo_mandatory_modes)/sizeof(*stereo_mandatory_modes); ++i) {
      const struct stereo_mandatory_mode *m=&stereo_mandatory_modes[i];
      matches += m->width==1920 && m->height==1080 && m->vrefresh==rates[r] && m->flags==DRM_MODE_FLAG_3D_SIDE_BY_SIDE_HALF;
    }
    assert(matches==1);
  }
}
'''
            (path / "edid.c").write_text(code)
            subprocess.run(["cc", str(path / "edid.c"), "-o", str(path / "edid")], check=True)
            subprocess.run([str(path / "edid")], check=True)


if __name__ == "__main__":
    unittest.main()
