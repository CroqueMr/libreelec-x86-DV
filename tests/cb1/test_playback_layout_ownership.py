"""The active skin owns rendering-selection layout and descriptions."""
import os
from pathlib import Path
import tarfile
import unittest
import xml.etree.ElementTree as ET


@unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'), 'Set patched Kodi source tree')
class PlaybackLayoutOwnership(unittest.TestCase):
    def test_native_skin_selection_layout_is_not_replaced(self):
        tree = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        archive = Path(os.environ.get('KODI_UPSTREAM_ARCHIVE',
            '/home/dvbuild/beta5-gpl2-image-20261022/sources/kodi/'
            'kodi-28ea2eac1eb7af8fdcbd2672d933ce87f594be79.tar.gz'))
        names = ('DialogSelect.xml', 'Includes_DialogSelect.xml', 'Variables.xml')
        with tarfile.open(archive) as source:
            for name in names:
                relative = 'addons/skin.estuary/xml/' + name
                member = next(item for item in source.getmembers()
                              if item.name.endswith('/' + relative))
                with self.subTest(name=name):
                    self.assertEqual((tree / relative).read_bytes(),
                                     source.extractfile(member).read())

    def test_master_settings_are_fixed_and_intrinsic_fast_has_no_saved_control(self):
        tree = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        settings = ET.parse(tree / 'system/settings/settings.xml')
        self.assertIsNone(settings.find(".//setting[@id='dvbridge.fastchroma']"))
        output = settings.find(".//setting[@id='dvbridge.masteroutput']")
        fallback = settings.find(".//setting[@id='dvbridge.masterfallback']")
        self.assertEqual(output.findtext('default'), '0')
        self.assertEqual(output.findtext('level'), '3')
        self.assertEqual([o.text for o in output.findall('constraints/options/option')], ['0', '1'])
        self.assertEqual(fallback.findtext('default'), 'false')
        for node in (output, fallback):
            self.assertEqual(node.findtext("dependencies/dependency[@setting='dvbridge.outputmode']"), '4')

    def test_l2_trim_override_is_expert_opt_in_for_standard_and_master(self):
        tree = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        settings = ET.parse(tree / 'system/settings/settings.xml')
        option = settings.find(".//setting[@id='dvbridge.disablel2']")
        self.assertIsNotNone(option)
        self.assertEqual(option.findtext('default'), 'false')
        self.assertEqual(option.findtext('level'), '3')
        self.assertEqual([item.text for item in option.findall('dependencies/dependency/or/condition')], ['0', '4'])


if __name__ == '__main__':
    unittest.main()
