"""Resolve independent rendering controls through the fully patched Kodi catalog."""
import re
import unittest
import xml.etree.ElementTree as ET
from test_native_video_source import TREE


class RenderingLabelsTests(unittest.TestCase):
    def test_master_safety_and_hdr10plus_resolve_independent_labels(self):
        catalog=(TREE/'addons/resource.language.en_gb/resources/strings.po').read_text()
        entries=re.findall(r'msgctxt "#(\d+)"\s+msgid "([^"\n]*)"',catalog)
        labels={}
        for key,value in entries:
            if 40800<=int(key)<41000:
                self.assertNotIn(key,labels,'Ambiguous rendering control label '+key)
                labels[key]=value
        settings=ET.parse(TREE/'system/settings/settings.xml')
        safety=settings.find(".//setting[@id='dvbridge.masterfallback']")
        self.assertEqual(labels[safety.get('label')],
                         'Allow Master Reference to switch to Standard')
        self.assertEqual(labels[safety.get('help')],
                         'Switch when sustained rendering headroom is insufficient. Off keeps Master Reference strict.')
        method=settings.find(".//setting[@id='dvbridge.hdr10method']")
        dynamic=next(option for option in method.findall('./constraints/options/option')
                     if option.text=='2')
        self.assertEqual(labels[dynamic.get('label')],'HDR10+ conversion (experimental)')


if __name__=='__main__':unittest.main()
