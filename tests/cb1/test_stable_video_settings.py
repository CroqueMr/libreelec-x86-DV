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
        self.assertEqual(ids[:7], [f"dvbridge.{name}" for name in
                         ("playback", "masteroutput", "hdr10source", "hdr10plussource", "hlgsource",
                          "sdrpreset", "sdrgamut")])
        for name in ("sdrpreset", "sdrgamut", "sdrpeak", "sdrgamma", "sdrblack"):
            conditions = group.findall(f"setting[@id='dvbridge.{name}']/dependencies/dependency/or/condition")
            self.assertEqual({(c.get("setting"), c.text) for c in conditions},
                             {("dvbridge.outputmode", "6"), ("dvbridge.hdr10source", "4"),
                              ("dvbridge.hdr10plussource", "4"), ("dvbridge.hlgsource", "2")})

    def test_master_reference_output_is_expert_and_defaults_to_ycbcr(self):
        master = self.video.find(".//setting[@id='dvbridge.masteroutput']")
        self.assertEqual(master.findtext("level"), "3")
        default = master.findtext("default")
        option = master.find("constraints/options/option[@label='40918']")
        self.assertEqual(default, option.text)
        visible, = master.findall("dependencies/dependency[@type='visible']")
        self.assertEqual(visible.get("setting"), "dvbridge.outputmode")
        self.assertEqual(visible.text, "4")

    def test_tv_peak_visibility_excludes_cm4_auto2(self):
        visible = self.video.find(".//setting[@id='dvbridge.tvpeak']/dependencies/dependency[@type='visible']")
        self.assertEqual([condition.text for condition in visible.findall(".//condition[@setting='dvbridge.cmv40']")],
                         ["3"])
        self.assertEqual(visible.findtext(".//condition[@setting='dvbridge.cmv40trigger']"), "0")
        self.assertEqual({(condition.get("setting"), condition.text) for condition in visible.findall("or/condition")},
                         {("dvbridge.outputmode", "3"), ("dvbridge.outputmode", "5"),
                          ("dvbridge.hdr10source", "2")})

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
        menu = source[source.index("bool ShowLldvFormatMenu(bool forCircuit)\n"):source.index("std::string CDVPlaybackModes::LldvPreferenceLabel()")]
        self.assertNotIn("firstFormat", menu)
        self.assertIn("CB1.LldvStatus", menu)
        self.assertEqual(menu.count("dialog->Add(item)"), 1)
        skin = ET.parse(TREE / "addons/skin.estuary/xml/Includes_DialogSelect.xml")
        self.assertIn("$INFO[Window.Property(CB1.LldvStatus)]", list(skin.getroot().itertext()))

    def test_lldv_selector_uses_one_page_with_a_short_status_in_estuary(self):
        source = (TREE / "xbmc/dialogs/DVPlaybackModes.cpp").read_text(encoding="utf-8")
        menu = source[source.index("bool ShowLldvFormatMenu(bool forCircuit)\n"):source.index("std::string CDVPlaybackModes::LldvPreferenceLabel()")]
        self.assertIn('dialog->SetUseDetails(!estuary);', menu)
        self.assertIn("summary && LldvCanChooseFormat(status)", menu)
        self.assertNotIn("strings.Get(41296)", menu)
        skin = ET.parse(TREE / "addons/skin.estuary/xml/Includes_DialogSelect.xml")
        native = skin.find(".//include[@name='DefaultDialogSelectLayout']/control")
        self.assertNotIn("$INFO[Container(3).ListItem.Label2]", list(native.itertext()))
        self.assertEqual(native.find(".//include/param[@name='id'][@value='9']").get("value"), "9")
        side = native.find("control[@id='9001']")
        status = side.find("control[@type='textbox']")
        self.assertEqual(status.findtext("label"), "$INFO[Window.Property(CB1.LldvStatus)]")
        self.assertGreater(int(status.get("id", "0")), 0)
        controls = list(side)
        cancel = next(control for control in controls if control.find("param[@name='id'][@value='7']") is not None)
        details = next(control for control in controls if control.find("param[@name='id'][@value='9']") is not None)
        self.assertEqual(controls[controls.index(cancel) + 1:controls.index(cancel) + 3], [details, status])
        row = ET.parse(TREE / "addons/skin.estuary/xml/Includes.xml").find(
            ".//include[@name='DefaultSimpleListLayout']/definition/itemlayout")
        self.assertTrue(any("CB1.LldvFocusNote" in text for text in row.itertext()))
        lang = (TREE / "addons/resource.language.en_gb/resources/strings.po").read_text(encoding="utf-8")
        self.assertIn('msgctxt "#41203"\nmsgid "YCbCr 4:2:2 · 10 bits"', lang)
        nav = native.findall("control[@id='3']/onright")
        self.assertTrue(any(link.text == "9001" and "CB1.LldvStatus" in link.get("condition", "")
                            for link in nav))

    def test_lldv_preference_label_does_not_use_the_active_format(self):
        source = (TREE / "xbmc/dialogs/DVPlaybackModes.cpp").read_text(encoding="utf-8")
        preference = source.split("std::string CDVPlaybackModes::LldvPreferenceLabel()", 1)[1]
        preference = preference.split("std::string CDVPlaybackModes::SDRGamutLabel()", 1)[0]
        self.assertNotIn("status.active", preference)


    def test_lldv_display_details_use_a_nested_native_viewer(self):
        menu = (TREE / "xbmc/dialogs/DVPlaybackModes.cpp").read_text(encoding="utf-8")
        menu = menu[menu.index("bool ShowLldvFormatMenu(bool forCircuit)\n"):
                    menu.index("std::string CDVPlaybackModes::LldvPreferenceLabel()")]
        self.assertNotIn("41297", menu)
        self.assertIn('dialog->EnableButton(!estuary, 41320);', menu)
        for field in ("LldvDetails", "LldvDetailLabels", "LldvDetailValues"):
            self.assertIn(f'CB1.{field}', menu)
        select = (TREE / "xbmc/dialogs/GUIDialogSelect.cpp").read_text(encoding="utf-8")
        self.assertIn("GetWindow<CGUIDialogTextViewer>(WINDOW_DIALOG_TEXT_VIEWER)", select)
        viewer = ET.parse(TREE / "addons/skin.estuary/xml/DialogTextViewer.xml")
        self.assertIn("$INFO[Window.Property(CB1.LldvDetailValues)]", list(viewer.getroot().itertext()))
        close = next(include for include in viewer.findall(".//include[@content='DefaultDialogButton']")
                     if include.find("param[@name='id'][@value='9901']") is not None)
        self.assertIsNone(close.find("param[@name='height']"))


if __name__ == "__main__":
    unittest.main()
