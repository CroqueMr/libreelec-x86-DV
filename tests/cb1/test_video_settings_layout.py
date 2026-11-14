
"""Check the resolved Kodi settings after applying the Generic patch stack."""
import os
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


@unittest.skipUnless(os.environ.get("KODI_NATIVE_SOURCE_TREE"), "needs patched Kodi")
class VideoSettingsLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kodi = Path(os.environ["KODI_NATIVE_SOURCE_TREE"])
        cls.video = ET.parse(cls.kodi / "system/settings/settings.xml").find(
            "./section[@id='player']/category[@id='videoplayer']")
        cls.strings = (cls.kodi / "addons/resource.language.en_gb/resources/strings.po").read_text(
            encoding="utf-8")

    def test_defaults_and_sdr_controls_are_consecutive(self):
        settings = self.video.find("group[@id='99']").findall("setting")
        ids = [setting.attrib["id"] for setting in settings if setting.findtext("visible") != "false"]
        self.assertEqual(ids[:4], ["dvbridge.playback", "dvbridge.hdr10source",
                                   "dvbridge.hdr10plussource", "dvbridge.hlgsource"])
        self.assertEqual(ids[ids.index("dvbridge.sdrpreset") + 1], "dvbridge.sdrgamut")

    def test_scalers_and_tv_profile_use_the_native_groups(self):
        processing = self.video.find("group[@id='3']")
        for output in ("sdr", "hdr"):
            self.assertIsNotNone(processing.find(f"setting[@id='videoplayer.{output}upscaler']"))
        tv = self.video.find("group[@id='cb1-tv-characteristics']")
        for field in ("tvpeak", "tvgamut", "expertpeak", "expertblack", "expertgamut",
                      "lldvdisplaypeak", "lldvdisplayblack"):
            setting = tv.find(f"setting[@id='dvbridge.{field}']")
            self.assertIsNotNone(setting.find("dependencies/dependency[@type='visible']"))

    def test_output_label_and_native_preference_are_unambiguous(self):
        for label in ("HDR10 : LLDV Reference conversion", "Dolby Vision : LLDV",
                      "HDR10+ : Native", "HDR/DV to SDR conversion target", " - SDR output gamut"):
            self.assertIn(f'msgid "{label}"', self.strings)
        native = self.video.find(".//setting[@id='dvbridge.hdr10plussource']/constraints/options/option[@label='41014']")
        self.assertEqual(native.text, "5")
        kodi = self.video.find(".//setting[@id='dvbridge.hdr10plussource']/constraints/options/option[@label='40866']")
        self.assertEqual(kodi.text, "0")
        options = self.video.find(".//setting[@id='dvbridge.hdr10plussource']/constraints/options")
        self.assertEqual([option.get("label") for option in options], ["40970", "41014", "40866", "41130"])

    def test_lldv_selector_has_no_diagnostic_rows(self):
        dialog = (self.kodi / "xbmc/dialogs/DVPlaybackModes.cpp").read_text(encoding="utf-8")
        selector = dialog.split("void ShowLldvFormatMenu()", 1)[1].split("} // namespace", 1)[0]
        self.assertNotIn("firstFormat", selector)
        self.assertNotIn("addDetail", selector)
        self.assertNotIn("\u00c2\u00b7", dialog)


if __name__ == "__main__":
    unittest.main()

