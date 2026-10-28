"""The active skin owns rendering-selection layout and descriptions."""
import os
import hashlib
import subprocess
import tempfile
from pathlib import Path
import tarfile
import unittest
import xml.etree.ElementTree as ET


@unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'), 'Set patched Kodi source tree')
class PlaybackLayoutOwnership(unittest.TestCase):
    def test_beta4_selector_keeps_its_layout_and_native_lists_unmodified(self):
        tree = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        from test_native_video_source import body
        source = (tree/'xbmc/dialogs/GUIDialogSelect.cpp').read_text()
        init = body(source, 'void CGUIDialogSelect::OnInitWindow()')
        marker = 'if (GetProperty("CB1.PlaybackModes").asBoolean())'
        self.assertIn(marker, init, 'compact playback geometry is missing')
        geometry = marker + body(init, marker)
        program = r'''
#include <algorithm>
#include <cassert>
struct Control {
 float x=1220,y=2,h=9;
 float GetXPosition()const{return x;} float GetYPosition()const{return y;}
 void SetPosition(float a,float b){x=a;y=b;} void SetHeight(float v){h=v;}
};
struct Property {bool value;bool asBoolean()const{return value;}};
struct List {int count;int Size()const{return count;}};
constexpr int CONTROL_SIMPLE_LIST=3,CONTROL_DETAILED_LIST=6;
struct Dialog {
 bool playback;List rows;List* m_vecList=&rows;Control group,image,list,help;
 Property GetProperty(const char*)const{return {playback};}
 Control* GetControl(int id){return id==9100?&group:id==9101?&image:id==9102?&help:&list;}
 struct Resolution{int iHeight=1080;};Resolution GetCoordsRes()const{return {};}
 void apply(){GEOMETRY}
};
int main(){
 for(auto [count,expected]:{std::pair{0,50}, {1,50}, {3,150}, {6,300}, {7,350}, {20,850}}){
  Dialog native{false,{count}};native.apply();assert(native.group.h==9 && native.list.h==9);
  Dialog d{true,{count}};d.apply();
  assert(d.list.h==expected && d.group.x==1220 && d.group.y+d.group.h==1040);
  assert(d.group.y>=40);
  assert(d.image.h==d.group.h && d.help.y==70+expected);
  assert(d.help.y+38<=d.group.h-4);
 }
}
'''.replace('GEOMETRY', geometry)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'test.cpp').write_text(program)
            built=subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
        repo=Path(__file__).resolve().parents[2]
        layout=ET.parse(repo/'projects/Generic/filesystem/usr/share/kodi/media/cb1/IncludesDVProcessInfo.xml')
        group=layout.find(".//include[@name='CB1PlaybackModeLayout']//control[@id='9100']")
        self.assertIsNotNone(group)
        self.assertEqual((group.findtext('right'),group.findtext('bottom'),group.findtext('width')),('40','40','660'))
        # Published Beta4 build 45b07c9: canonical XML of the two app-owned includes.
        for name,expected in (
            ('CB1PlaybackModeLayout','19376914c906de94b827e883e99fe2a29df717113b03a9b084713b08cc309beb'),
            ('CB1PlaybackModeRows','bd2f02179872d443a0fdfccfcaba3bf45b915174549ce02cb2c3e6181f3d307b')):
            node=layout.find(".//include[@name='"+name+"']")
            canonical=ET.canonicalize(ET.tostring(node,encoding='unicode'),strip_text=True)
            self.assertEqual(hashlib.sha256(canonical.encode()).hexdigest(),expected,name)

    def test_native_skin_selection_layout_is_not_replaced(self):
        tree = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        archive = Path(os.environ['KODI_UPSTREAM_ARCHIVE'])
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
