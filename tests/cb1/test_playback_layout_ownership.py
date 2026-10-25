"""A foreign skin's reused control IDs must not resize its native dialog."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import struct
import xml.etree.ElementTree as ET


@unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'), 'Set patched Kodi source tree')
class PlaybackLayoutOwnership(unittest.TestCase):
    def test_owned_panel_keeps_fixed_corners_for_every_row_count(self):
        tree=Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        layout=ET.parse(tree/'addons/skin.estuary/xml/Includes_DialogSelect.xml')
        texture=layout.find(".//include[@name='CB1PlaybackModeLayout']//control[@id='9101']/texture")
        self.assertIsNotNone(texture)
        self.assertEqual(texture.text,'special://xbmc/media/cb1-panel.png')
        repo=Path(__file__).resolve().parents[2]
        png=(repo/'projects/Generic/filesystem/usr/share/kodi/media/cb1-panel.png').read_bytes()
        width,height=struct.unpack('>II',png[16:24])
        border=int(texture.get('border','0'))
        self.assertEqual((width,height,border),(120,120,60))
        # Native nine-slice keeps source corners square while the centre grows.
        for count in range(1,7):
            self.assertGreater(112+50*count,2*border)
            self.assertGreater(660,2*border)

    def test_master_settings_are_fixed_and_intrinsic_fast_has_no_saved_control(self):
        tree=Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        settings=ET.parse(tree/'system/settings/settings.xml')
        self.assertIsNone(settings.find(".//setting[@id='dvbridge.fastchroma']"))
        output=settings.find(".//setting[@id='dvbridge.masteroutput']")
        fallback=settings.find(".//setting[@id='dvbridge.masterfallback']")
        self.assertEqual(output.findtext('default'),'0')
        self.assertEqual(output.findtext('level'),'3')
        self.assertEqual([o.text for o in output.findall('constraints/options/option')],['0','1'])
        self.assertEqual(fallback.findtext('default'),'true')
        for node in (output,fallback):
            self.assertEqual(node.findtext("dependencies/dependency[@setting='dvbridge.outputmode']"),'4')

    def test_foreign_control_ids_keep_their_geometry(self):
        source = (Path(os.environ['KODI_NATIVE_SOURCE_TREE']) /
                  'xbmc/dialogs/GUIDialogSelect.cpp').read_text()
        start = source.index('#ifdef HAVE_DVBRIDGE', source.index('void CGUIDialogSelect::OnInitWindow()'))
        stop = source.index('#endif', start)
        body = source[start:stop] + '\n#endif\n'
        program = r'''
#include <cassert>
#include <string>
#define HAVE_DVBRIDGE
constexpr int CONTROL_SIMPLE_LIST=3, CONTROL_DETAILED_LIST=6;
namespace DVBRIDGE {float PlaybackMenuRowsHeight(int n){return n*50;}}
struct CGUIControl {
 float x=1,y=2,h=9; virtual ~CGUIControl()=default;
 float GetXPosition(){return x;} float GetYPosition(){return y;}
 void SetPosition(float a,float b){x=a;y=b;} void SetHeight(float v){h=v;}
};
struct CGUIImage:CGUIControl {std::string file; std::string GetFileName(){return file;}};
struct Property {bool asBoolean(){return true;}};
struct List {int Size(){return 4;}};
struct Dialog {
 CGUIControl group,list,help; CGUIImage image; List rows; List* m_vecList=&rows;
 Property GetProperty(const char*){return {};}
 CGUIControl* GetControl(int id){return id==9100?&group:id==9101?&image:id==9102?&help:&list;}
 struct Resolution{int iHeight=1080;}; Resolution GetCoordsRes(){return {};}
 void prepare(){
 BODY
 }
};
int main(){
 Dialog foreign;foreign.image.file="foreign-dialog.png";foreign.prepare();
 assert(foreign.group.h==9 && foreign.group.y==2 && foreign.list.h==9);
 Dialog owned;owned.image.file="special://xbmc/media/cb1-panel.png";owned.prepare();
 assert(owned.group.h==312 && owned.group.y==728 && owned.list.h==200);
}
'''.replace('BODY', body)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'test.cpp').write_text(program)
            built = subprocess.run(['c++', '-std=c++20', str(root/'test.cpp'), '-o', str(root/'test')],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            result = subprocess.run([str(root/'test')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
