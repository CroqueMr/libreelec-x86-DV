"""The GUI switch changes only the frame preference, not the movie policy."""
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

from test_native_video_source import TREE


class OptionalGUITests(unittest.TestCase):
    def test_native_setting_defaults_off_and_toggle_invalidates_frame_preferences(self):
        source=(TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVOutputSettings.h').read_text()
        preferences=source.split('struct OutputPreferences',1)[1].split('inline std::mutex&',1)[0]
        enums=source.split('enum class OutputMode',1)[1].split('// Decoder ingress',1)[0]
        program=r'''
#include <atomic>
#include <bit>
#include <cmath>
#include <cstdint>
enum class OutputMode ENUMS
struct OutputPreferences PREFS
#include <cassert>
int main(){
 OutputPreferences a,b;assert(!a.optimizedGUI && a.SameValues(b));
 a.optimizedGUI=true;assert(!a.SameValues(b));
 assert(a.output==b.output && a.method==b.method && a.masterIPT==b.masterIPT);
 b.optimizedGUI=true;assert(a.SameValues(b));
 a.optimizedGUI=false;assert(!a.SameValues(b));
}
'''.replace('ENUMS',enums).replace('PREFS',preferences)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'check.cpp').write_text(program)
            built=subprocess.run(['c++','-std=c++20',str(root/'check.cpp'),'-o',str(root/'check')],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran=subprocess.run([str(root/'check')],capture_output=True,text=True)
            self.assertEqual(ran.returncode,0,ran.stderr)
        settings=ET.parse(TREE/'system/settings/settings.xml').getroot()
        option=settings.find(".//setting[@id='dvbridge.optimizedgui']")
        self.assertIsNotNone(option)
        self.assertEqual(option.findtext('default'),'false')
        self.assertEqual(option.find('control').get('type'),'toggle')

if __name__=='__main__':unittest.main()
