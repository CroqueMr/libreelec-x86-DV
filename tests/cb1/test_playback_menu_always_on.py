"""Saved preferences cannot disable the rendering selector."""
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from test_native_video_source import TREE, body


class PlaybackMenuTests(unittest.TestCase):
    def test_saved_false_does_not_disable_selector(self):
        source = (TREE / 'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVOutputSettings.h').read_text()
        implementation = body(source, 'inline bool PlaybackMenuEnabled()')
        program = r'''
#include <cassert>
#include <memory>
struct Settings { bool GetBool(const char*) const { return false; } };
struct Component { std::shared_ptr<Settings> GetSettings() { return std::make_shared<Settings>(); } };
struct CServiceBroker { static std::shared_ptr<Component> GetSettingsComponent() { return std::make_shared<Component>(); } };
bool PlaybackMenuEnabled() BODY
int main() { assert(PlaybackMenuEnabled()); }
'''.replace('BODY', implementation)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'check.cpp').write_text(program)
            subprocess.run(['c++', '-std=c++20', str(root / 'check.cpp'), '-o', str(root / 'check')], check=True)
            result = subprocess.run([str(root / 'check')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_no_user_toggle_in_settings(self):
        settings = ET.parse(TREE / 'system/settings/settings.xml')
        self.assertIsNone(settings.find(".//setting[@id='dvbridge.playbackmenu']"))


if __name__ == '__main__':
    unittest.main()
