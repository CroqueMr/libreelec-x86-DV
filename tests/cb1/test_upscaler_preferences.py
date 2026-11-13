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

    def test_fsr1_is_opt_in_for_sdr_and_uses_kodi_multipass(self):
        settings = ET.parse(TREE / "system/settings/settings.xml")
        for output, available in (("sdr", True), ("hdr", False)):
            preset = settings.find(f".//setting[@id='videoplayer.{output}upscaler']"
                                   "/constraints/options/option[@label='41230']")
            self.assertEqual(preset is not None, available)
        renderer = TREE / "xbmc/cores/VideoPlayer/VideoRenderers/LinuxRendererGLES.cpp"
        self.assertIn("new FSR1FilterShader", renderer.read_text())
        shader = TREE / "system/shaders/GLES/2.0/gles_fsr1_easu.frag"
        self.assertIn("FsrEasuTap", shader.read_text())

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
