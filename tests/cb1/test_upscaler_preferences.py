# SPDX-License-Identifier: MIT
"""The two preferences preserve native defaults and report only real enlargement."""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

from test_ai_reentry import execute
from test_native_video_source import TREE

REPO = Path(__file__).resolve().parents[2]


class UpscalerPreferences(unittest.TestCase):
    def test_output_preference_and_geometry(self):
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
  assert(Enlarges(1920,1080,3840,2160));
  assert(!Enlarges(3840,2160,3840,2160));
  assert(!Enlarges(3840,2160,1920,1080));
  assert(!Enlarges(0,0,1920,1080));
  assert(!Enlarges(1920,1080,1920.1f,1080.1f));
}
""")

    def test_fsr1_is_opt_in_and_uses_kodi_multipass(self):
        settings = ET.parse(TREE / "system/settings/settings.xml")
        for output in ("sdr", "hdr"):
            preset = settings.find(f".//setting[@id='videoplayer.{output}upscaler']"
                                   "/constraints/options/option[@label='41230']")
            self.assertIsNotNone(preset)
        renderer = TREE / "xbmc/cores/VideoPlayer/VideoRenderers/LinuxRendererGLES.cpp"
        self.assertIn("new FSR1FilterShader", renderer.read_text())
        shader = TREE / "system/shaders/GLES/2.0/gles_fsr1_easu.frag"
        self.assertIn("FsrEasuTap", shader.read_text())

    def test_cnn_presets_are_offered_for_both_output_preferences(self):
        settings = ET.parse(TREE / "system/settings/settings.xml")
        for output in ("sdr", "hdr"):
            for label in ("41231", "41232"):
                preset = settings.find(f".//setting[@id='videoplayer.{output}upscaler']"
                                       f"/constraints/options/option[@label='{label}']")
                self.assertIsNotNone(preset)
        renderer = (TREE / "xbmc/cores/VideoPlayer/VideoRenderers/LinuxRendererGLES.cpp").read_text()
        self.assertIn("RenderShaderUpscaler(index, preset)", renderer)

    def test_rcas_is_a_separate_preset(self):
        settings = ET.parse(TREE / "system/settings/settings.xml")
        for output in ("sdr", "hdr"):
            preset = settings.find(f".//setting[@id='videoplayer.{output}upscaler']"
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
enum dvbridge_mode { DVBRIDGE_MODE_SDR, DVBRIDGE_MODE_MASTER_REFERENCE };
struct dvbridge_geometry { float crop[4]; float placement[4]; };
struct CDVBridgeGLES { struct Layer { ESCALINGMETHOD scalingMethod, autoScalingMethod; }; };
namespace KODI::VIDEO::UPSCALER
{
int selected;
int Get(bool hdr, ESCALINGMETHOD) { return hdr ? selected : VS_SCALINGMETHOD_FSR1_RCAS; }
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
  dvbridge_geometry scaled{{0,0,1920,1080}, {0,0,3840,2160}};
  dvbridge_geometry unscaled{{0,0,3840,2160}, {0,0,3840,2160}};
  const ESCALINGMETHOD presets[] = {
    VS_SCALINGMETHOD_FSRCNNX, VS_SCALINGMETHOD_ANIME4K, VS_SCALINGMETHOD_FSR1_RCAS
  };
  for (const auto preset : presets)
  {
    selected = preset;
    assert(OutputScalingMethod(layer, scaled, DVBRIDGE_MODE_MASTER_REFERENCE) == preset);
    assert(OutputScalingMethod(layer, unscaled, DVBRIDGE_MODE_MASTER_REFERENCE) ==
           VS_SCALINGMETHOD_LINEAR);
    assert(OutputScalingMethod(layer, scaled, DVBRIDGE_MODE_SDR) == VS_SCALINGMETHOD_LINEAR);
  }
  selected = VS_SCALINGMETHOD_AUTO;
  assert(OutputScalingMethod(layer, scaled, DVBRIDGE_MODE_MASTER_REFERENCE) ==
         VS_SCALINGMETHOD_LANCZOS3);
}
""")

    def test_settings_and_conditional_information_row(self):
        settings = ET.parse(TREE / "system/settings/settings.xml")
        for setting in ("videoplayer.sdrupscaler", "videoplayer.hdrupscaler"):
            self.assertEqual(settings.find(f".//setting[@id='{setting}']/default").text, "-1")
        panel = ET.parse(REPO / "projects/Generic/filesystem/usr/share/kodi/media/cb1/IncludesDVProcessInfo.xml")
        row = next(node for node in panel.iter("include")
                   if any("Property(DV.VideoUpscaler)" in value for item in node.findall("param")
                          for value in item.attrib.values()))
        self.assertEqual(row.find("param[@name='visible']").get("value"),
                         "!String.IsEmpty(Window(playerprocessinfo).Property(DV.VideoUpscaler))")
