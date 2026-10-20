"""Enhanced information must not reuse another skin's cached vanilla dialog."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'), 'Set patched Kodi source tree')
class ProcessInfoSkinRecoveryTests(unittest.TestCase):
    def test_each_open_loads_the_selected_information_panel(self):
        tree = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        source = (tree / 'xbmc/dialogs/GUIDialogPlayerProcessInfo.cpp').read_text()
        start = source.index('{', source.index('bool CGUIDialogPlayerProcessInfo::OnMessage('))
        depth, end = 1, start + 1
        while depth:
            depth += (source[end] == '{') - (source[end] == '}')
            end += 1
        program = r'''
#include <cassert>
#include <string>
#define HAVE_DVBRIDGE
constexpr int GUI_MSG_WINDOW_INIT=1;
namespace DVBRIDGE {bool enabled=true;bool EnhancedInfoEnabled() {return enabled;}}
struct RESOLUTION_INFO {int width,height;RESOLUTION_INFO(int w,int h):width(w),height(h){}};
struct CGUIMessage {int type;int GetMessage() const {return type;}};
struct FontManager {
 int loads=0;
 void LoadTTF(const char*, const char* file, unsigned, unsigned, int, int,
              bool, float, float, const RESOLUTION_INFO*) {
  assert(std::string(file)=="special://xbmc/media/Fonts/arial.ttf"); ++loads;
 }
} g_fontManager;
struct Value {std::string value;std::string asString() const {return value;}};
// Only resource I/O is replaced; the production message handler is executed below.
struct CGUIDialog {
 Value xml{"DialogPlayerProcessInfo.xml"};std::string loaded;bool cached=false;
 RESOLUTION_INFO resolution{1280,720};
 Value GetProperty(const char*) const {return xml;}
 void SetProperty(const char*,const std::string& file) {xml.value=file;}
 void FreeResources(bool) {cached=false;}
 void SetCoordsRes(RESOLUTION_INFO value) {resolution=value;}
 bool OnMessage(CGUIMessage& message) {
  if(message.type==GUI_MSG_WINDOW_INIT && !cached) {loaded=xml.value;cached=true;}
  return true;
 }
};
struct CGUIDialogPlayerProcessInfo : CGUIDialog {bool OnMessage(CGUIMessage& message) BODY};
int main() {
 CGUIDialogPlayerProcessInfo dialog;CGUIMessage open{GUI_MSG_WINDOW_INIT};
 dialog.loaded="foreign-skin-vanilla.xml";dialog.cached=true;
 dialog.OnMessage(open);
 assert(dialog.loaded=="special://xbmc/media/cb1/DialogPlayerProcessInfo.xml");
 assert(g_fontManager.loads==3);
 assert(dialog.resolution.width==1920 && dialog.resolution.height==1080);
 DVBRIDGE::enabled=false;dialog.OnMessage(open);
 assert(dialog.loaded=="DialogPlayerProcessInfo.xml");
 DVBRIDGE::enabled=true;dialog.OnMessage(open);
 assert(dialog.loaded=="special://xbmc/media/cb1/DialogPlayerProcessInfo.xml");
 CGUIMessage other{42};dialog.OnMessage(other);
 assert(dialog.loaded=="special://xbmc/media/cb1/DialogPlayerProcessInfo.xml");
}
'''.replace('BODY', source[start:end])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'test.cpp').write_text(program)
            built = subprocess.run(['c++', '-std=c++20', str(root / 'test.cpp'), '-o', str(root / 'test')],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            ran = subprocess.run([str(root / 'test')], capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0, ran.stderr)


if __name__ == '__main__':
    unittest.main()
