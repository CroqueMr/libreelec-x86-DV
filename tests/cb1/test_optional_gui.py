"""GUI optimization is automatic; obsolete saved switches cannot change policy."""
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

from test_native_video_source import TREE


class OptionalGUITests(unittest.TestCase):
    def test_no_gui_preference_or_revision_state_remains(self):
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
 OutputPreferences a,b;assert(a.SameValues(b));
 a.optimizedDV=false;assert(!a.SameValues(b));
 assert(a.output==b.output && a.method==b.method && a.masterIPT==b.masterIPT);
 b.optimizedDV=false;assert(a.SameValues(b));
 a.optimizedDV=true;assert(!a.SameValues(b));
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
        self.assertIsNone(option)
        self.assertNotIn('optimizedGUI',source)
        self.assertNotIn('encodedActiveArea',source)
        self.assertNotIn('GetBool("dvbridge.optimizedgui")',source)
        self.assertNotIn('GetBool("dvbridge.encodedactivearea")',source)
        native=(TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        self.assertIn('importGeometry.ignore_l5=false;',native)
        self.assertIn('geometry.ignore_l5=false;',native)
        # C geometry retains its field/ABI; authored margins are not overwritten.
        self.assertNotIn('preferences.encodedActiveArea',native)

if __name__=='__main__':unittest.main()
