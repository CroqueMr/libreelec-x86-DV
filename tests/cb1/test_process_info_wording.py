"""The native label controls retain long values and all processing fields."""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


class ProcessInfoWordingTests(unittest.TestCase):
    def test_compact_labels_keep_all_fields_and_native_overflow_scrolling(self):
        panel=ET.parse(Path(__file__).resolve().parents[2]/
            'projects/Generic/filesystem/usr/share/kodi/media/cb1/IncludesDVProcessInfo.xml')
        rows=panel.findall('.//include[@content="DVInfoRow"]')
        self.assertEqual(len(rows),68)
        self.assertIsNone(panel.find('./variable[@name="DVAudioOutput"]'))
        self.assertTrue(any(r.find('./param[@name="value"]').get('value') ==
                            '$INFO[Player.Process(audiooutputtransport)]' for r in rows))
        expected={'DV.ParsedBlocks':'Source blocks','DV.AppliedBlocks':'Applied blocks',
                  'DV.UnappliedBlocks':'Unused blocks','DV.MinimumLinkBits':'$LOCALIZE[40848]',
                  'DV.Fallback':'Fallback'}
        for prop,label in expected.items():
            row=next(r for r in rows if r.find('./param[@name="value"]').get('value')==
                     '$INFO[Window(playerprocessinfo).Property('+prop+')]')
            self.assertEqual(row.find('./param[@name="label"]').get('value'),label)
        controls=panel.findall('./include[@name="DVInfoRow"]/definition/control/control')
        self.assertEqual(len(controls),2)
        self.assertEqual(controls[0].get('type'),'label')
        self.assertEqual(controls[1].get('type'),'fadelabel')
        self.assertEqual(controls[1].findtext('scroll'),'true')
        self.assertEqual(controls[1].findtext('resetonlabelchange'),'false')
