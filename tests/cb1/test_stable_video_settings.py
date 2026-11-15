#!/usr/bin/env python3
import xml.etree.ElementTree as ET
import unittest

from test_native_video_source import TREE


class StableVideoSettings(unittest.TestCase):
    def setUp(self):
        self.settings = ET.parse(TREE / "system/settings/settings.xml")
        self.video = self.settings.find(".//section[@id='player']/category[@id='videoplayer']")

    def test_playback_controls_and_sdr_dependencies(self):
        group = self.video.find("group[@id='99']")
        ids = [setting.get("id") for setting in group]
        self.assertEqual(ids[:6], [f"dvbridge.{name}" for name in
                         ("playback", "hdr10source", "hdr10plussource", "hlgsource", "sdrpreset", "sdrgamut")])
        for name in ("sdrpreset", "sdrgamut", "sdrpeak", "sdrgamma", "sdrblack"):
            conditions = group.findall(f"setting[@id='dvbridge.{name}']/dependencies/dependency/or/condition")
            self.assertEqual({(c.get("setting"), c.text) for c in conditions},
                             {("dvbridge.outputmode", "6"), ("dvbridge.hdr10source", "4"),
                              ("dvbridge.hdr10plussource", "4"), ("dvbridge.hlgsource", "2")})

    def test_upscalers_live_with_kodi_processing(self):
        group = self.video.find("group[@id='3']")
        ids = [setting.get("id") for setting in group]
        scaler = ids.index("videoplayer.hqscalerprecision")
        self.assertEqual(ids[scaler + 1:scaler + 3],
                         ["videoplayer.upscaler1080pandabove", "videoplayer.upscalerbelow1080p"])

    def test_async_is_not_a_setting(self):
        self.assertIsNone(self.settings.find(".//setting[@id='dvbridge.asyncpreparation']"))
        policy = (TREE / "xbmc/cores/VideoPlayer/DVDCodecs/Video/DVOutputSettings.h").read_text()
        self.assertNotIn("dvbridge.asyncpreparation", policy)

    def test_lldv_host_rows_remain_in_scanout_order(self):
        render = (TREE / "xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp").read_text()
        self.assertIn("10u : 12u, true, false,", render)

    def test_lldv_output_uses_one_pair_and_dialog_separates_edid(self):
        info = (TREE / "xbmc/dialogs/GUIDialogPlayerProcessInfo.cpp").read_text(encoding="utf-8")
        self.assertNotIn("reportedPrimaries[j]", info)
        self.assertIn('SetProperty("DV.HdmiFormat"', info)
        source = (TREE / "xbmc/dialogs/DVPlaybackModes.cpp").read_text(encoding="utf-8")
        menu = source[source.index("void ShowLldvFormatMenu()"):source.index("std::string CDVPlaybackModes::LldvPreferenceLabel()")]
        self.assertNotIn("firstFormat", menu)
        self.assertIn("CB1.LldvEdid", menu)
        self.assertEqual(menu.count("dialog->Add(item)"), 1)
        skin = ET.parse(TREE / "addons/skin.estuary/xml/Includes_DialogSelect.xml")
        self.assertIn("$INFO[Window.Property(CB1.LldvEdid)]", list(skin.getroot().itertext()))

    def test_lldv_selector_uses_one_page_with_a_short_status_in_estuary(self):
        source = (TREE / "xbmc/dialogs/DVPlaybackModes.cpp").read_text(encoding="utf-8")
        menu = source[source.index("void ShowLldvFormatMenu()"):source.index("std::string CDVPlaybackModes::LldvPreferenceLabel()")]
        self.assertIn('dialog->SetUseDetails(!estuary);', menu)
        self.assertIn("LldvUnavailableLabel(status, 0, true)", menu)
        self.assertNotIn("strings.Get(41296)", menu)
        skin = ET.parse(TREE / "addons/skin.estuary/xml/Includes_DialogSelect.xml")
        native = skin.find(".//include[@name='DefaultDialogSelectLayout']/control")
        self.assertIn("$INFO[Container(3).ListItem.Label2]", list(native.itertext()))
        nav = native.findall("control[@id='3']/onright")
        self.assertTrue(any(link.text == "9001" and "CB1.LldvEdid" in link.get("condition", "")
                            for link in nav))


if __name__ == "__main__":
    unittest.main()
