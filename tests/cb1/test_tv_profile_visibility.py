"""TV calibration controls are offered only to modes that consume them."""
import os
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


@unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'), 'Set patched Kodi source tree')
class TVProfileVisibilityTests(unittest.TestCase):
    def test_profile_controls_follow_selected_rendering_modes(self):
        tree = ET.parse(Path(os.environ['KODI_NATIVE_SOURCE_TREE']) / 'system/settings/settings.xml')
        settings = {s.get('id'): s for s in tree.iter('setting')}

        def evaluate(node, values):
            if node.tag == 'or':
                return any(evaluate(child, values) for child in node)
            if node.tag in ('and', 'dependency') and not node.get('setting'):
                return all(evaluate(child, values) for child in node)
            self.assertEqual(node.get('operator'), 'is')
            return values[node.get('setting')] == int(node.text)

        for output, method, ai, expected in [(0, 0, 0, False), (2, 0, 0, False),
                (1, 0, 0, False), (1, 1, 0, True), (3, 0, 0, True), (5, 0, 0, True),
                (0, 0, 1, False), (0, 0, 2, True)]:
            values = {'dvbridge.outputmode': output, 'dvbridge.hdr10method': method,
                      'dvbridge.hdr10source': ai}
            for key in ('dvbridge.configureprofile', 'dvbridge.tvpeak', 'dvbridge.tvgamut'):
                node = settings[key]
                dependencies = node.findall('./dependencies/dependency[@type="visible"]')
                visible = all(evaluate(d, values) for d in dependencies)
                with self.subTest(values=values, control=key):
                    self.assertEqual(visible, expected)
                    if visible:
                        self.assertEqual(int(node.findtext('level')), 0)


if __name__ == '__main__':
    unittest.main()
