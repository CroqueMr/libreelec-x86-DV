# SPDX-License-Identifier: MIT
"""The two preferences preserve native defaults and report only real enlargement."""
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

from test_ai_reentry import execute
from test_native_video_source import TREE

REPO = Path(__file__).resolve().parents[2]
SETTING_IDS = ("videoplayer.upscaler1080pandabove", "videoplayer.upscalerbelow1080p")


class UpscalerPreferences(unittest.TestCase):
    def test_source_resolution_and_geometry(self):
        header = TREE / "xbmc/cores/VideoPlayer/VideoRenderers/UpscalerSettings.h"
        self.assertTrue(header.is_file())
        source = header.read_text()
        policy = source[source.index("constexpr int Select("):source.index("int Get(")]
        execute("""
#include <cassert>
""" + policy + """
int main()
{
  assert(Select(-1, 1) == 1);
  assert(Select(-1, 8) == 8);
  assert(Select(1, 0) == 1);
  assert(Select(8, 0) == 8);
  assert(IsAtLeast1080p(1920,1080));
  assert(IsAtLeast1080p(1920,800));
  assert(IsAtLeast1080p(1440,1080));
  assert(IsAtLeast1080p(3840,2160));
  assert(!IsAtLeast1080p(1280,720));
  assert(!IsAtLeast1080p(720,576));
  assert(!IsAtLeast1080p(1919,1079));
  assert(Enlarges(1920,1080,3840,2160));
  assert(!Enlarges(3840,2160,3840,2160));
  assert(!Enlarges(3840,2160,1920,1080));
  assert(!Enlarges(0,0,1920,1080));
  assert(!Enlarges(1920,1080,1920.1f,1080.1f));
}
""")

    def test_fsr1_is_opt_in_and_uses_kodi_multipass(self):
        settings = ET.parse(TREE / "system/settings/settings.xml")
        for setting in SETTING_IDS:
            preset = settings.find(f".//setting[@id='{setting}']"
                                   "/constraints/options/option[@label='41230']")
            self.assertIsNotNone(preset)
        renderer = TREE / "xbmc/cores/VideoPlayer/VideoRenderers/LinuxRendererGLES.cpp"
        self.assertIn("new FSR1FilterShader", renderer.read_text())
        shader = TREE / "system/shaders/GLES/2.0/gles_fsr1_easu.frag"
        self.assertIn("FsrEasuTap", shader.read_text())

    def test_cnn_presets_are_offered_for_both_resolution_preferences(self):
        settings = ET.parse(TREE / "system/settings/settings.xml")
        for setting in SETTING_IDS:
            for label in ("41231", "41232"):
                preset = settings.find(f".//setting[@id='{setting}']"
                                       f"/constraints/options/option[@label='{label}']")
                self.assertIsNotNone(preset)
        renderer = (TREE / "xbmc/cores/VideoPlayer/VideoRenderers/LinuxRendererGLES.cpp").read_text()
        self.assertIn("RenderShaderUpscaler(index, preset)", renderer)
        self.assertEqual(len(re.findall(r"UPSCALER::Get\(\s*m_sourceWidth, m_sourceHeight,", renderer)), 2)
        auto_override = renderer.split("CLinuxRendererGLES::AutoUpscalingOverride() const", 1)[1]
        self.assertIn("Get(m_sourceWidth, m_sourceHeight, KODI_DEFAULT)", auto_override.split("}", 1)[0])

    def test_rcas_is_a_separate_preset(self):
        settings = ET.parse(TREE / "system/settings/settings.xml")
        for setting in SETTING_IDS:
            preset = settings.find(f".//setting[@id='{setting}']"
                                   "/constraints/options/option[@label='41233']")
            self.assertIsNotNone(preset)
        shader = TREE / "system/shaders/GLES/2.0/gles_fsr1_rcas.frag"
        self.assertIn("FsrRcas", shader.read_text())

    def test_master_reference_keeps_requested_shader_filter(self):
        renderer = (TREE / "xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp").read_text()
        start = renderer.index("ESCALINGMETHOD OutputScalingMethod(")
        end = renderer.index("} // namespace", start)
        execute("""
#include <cassert>

enum ESCALINGMETHOD
{
  VS_SCALINGMETHOD_AUTO, VS_SCALINGMETHOD_LINEAR, VS_SCALINGMETHOD_LANCZOS3,
  VS_SCALINGMETHOD_FSRCNNX, VS_SCALINGMETHOD_ANIME4K, VS_SCALINGMETHOD_FSR1_RCAS
};
enum dvbridge_mode { DVBRIDGE_MODE_SDR, DVBRIDGE_MODE_HDR10, DVBRIDGE_MODE_MASTER_REFERENCE };
struct dvbridge_geometry { unsigned source_width, source_height; float crop[4], placement[4]; };
struct CDVBridgeGLES { struct Layer { ESCALINGMETHOD scalingMethod, autoScalingMethod; }; };
namespace KODI::VIDEO::UPSCALER
{
int selected;
int Get(unsigned width, unsigned height, ESCALINGMETHOD)
{
  return width >= 1920 || height >= 1080 ? selected : VS_SCALINGMETHOD_LANCZOS3;
}
bool Enlarges(float fromW, float fromH, float toW, float toH)
{
  return toW > fromW || toH > fromH;
}
bool UsesShaderHooks(int method)
{
  return method == VS_SCALINGMETHOD_FSRCNNX || method == VS_SCALINGMETHOD_ANIME4K;
}
}
""" + renderer[start:end] + """
int main()
{
  using KODI::VIDEO::UPSCALER::selected;
  CDVBridgeGLES::Layer layer{VS_SCALINGMETHOD_LINEAR, VS_SCALINGMETHOD_LANCZOS3};
  dvbridge_geometry scaled{1920,800,{0,0,1920,800}, {0,0,3840,1600}};
  dvbridge_geometry lowResolution{1280,720,{0,0,1280,720}, {0,0,3840,2160}};
  dvbridge_geometry unscaled{3840,2160,{0,0,3840,2160}, {0,0,3840,2160}};
  const ESCALINGMETHOD presets[] = {
    VS_SCALINGMETHOD_FSRCNNX, VS_SCALINGMETHOD_ANIME4K, VS_SCALINGMETHOD_FSR1_RCAS
  };
  const dvbridge_mode modes[] = {DVBRIDGE_MODE_SDR, DVBRIDGE_MODE_HDR10, DVBRIDGE_MODE_MASTER_REFERENCE};
  for (const auto preset : presets)
  {
    selected = preset;
    assert(OutputScalingMethod(layer, scaled, DVBRIDGE_MODE_MASTER_REFERENCE) == preset);
    assert(OutputScalingMethod(layer, unscaled, DVBRIDGE_MODE_MASTER_REFERENCE) ==
           VS_SCALINGMETHOD_LINEAR);
    assert(OutputScalingMethod(layer, scaled, DVBRIDGE_MODE_SDR) == VS_SCALINGMETHOD_LINEAR);
  }
  for (const auto mode : modes)
    assert(OutputScalingMethod(layer, lowResolution, mode) == VS_SCALINGMETHOD_LANCZOS3);
  selected = VS_SCALINGMETHOD_AUTO;
  assert(OutputScalingMethod(layer, scaled, DVBRIDGE_MODE_MASTER_REFERENCE) ==
         VS_SCALINGMETHOD_LANCZOS3);
}
""")

    def test_settings_and_conditional_information_row(self):
        settings = ET.parse(TREE / "system/settings/settings.xml")
        above, below = [settings.find(f".//setting[@id='{setting}']") for setting in SETTING_IDS]
        for setting in (above, below):
            self.assertIsNotNone(setting)
            self.assertEqual(setting.findtext("default"), "-1")
        self.assertEqual(ET.tostring(above.find("constraints")), ET.tostring(below.find("constraints")))
        strings = (TREE / "addons/resource.language.en_gb/resources/strings.po").read_text()
        self.assertIn(f'msgctxt "#{above.get("label")}"\nmsgid "Upscaler – 1080p and above"', strings)
        self.assertIn(f'msgctxt "#{below.get("label")}"\nmsgid "Upscaler – Below 1080p"', strings)
        panel = ET.parse(REPO / "projects/Generic/filesystem/usr/share/kodi/media/cb1/IncludesDVProcessInfo.xml")
        row = next(node for node in panel.iter("include")
                   if any("Property(DV.VideoUpscaler)" in value for item in node.findall("param")
                          for value in item.attrib.values()))
        self.assertEqual(row.find("param[@name='visible']").get("value"),
                         "!String.IsEmpty(Window(playerprocessinfo).Property(DV.VideoUpscaler))")
