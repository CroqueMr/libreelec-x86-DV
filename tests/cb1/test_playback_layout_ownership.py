"""The active skin owns rendering-selection layout and descriptions."""
import os
import subprocess
import tempfile
from pathlib import Path
import tarfile
import unittest
import xml.etree.ElementTree as ET


@unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'), 'Set patched Kodi source tree')
class PlaybackLayoutOwnership(unittest.TestCase):
    def test_quick_switch_resizes_without_changing_native_lists(self):
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
#include <string>
#include <vector>
struct Control {
 float x=1220,y=2,h=9;
 float GetXPosition()const{return x;} float GetYPosition()const{return y;}
 void SetPosition(float a,float b){x=a;y=b;} void SetHeight(float v){h=v;}
};
struct Property {bool value;bool asBoolean()const{return value;}};
struct Item {
 std::string label2;
 const std::string& GetLabel2() const {return label2;}
};
struct List {
 explicit List(int count): items(count, &plain) {}
 Item plain, withHelp{"Unavailable reason"};
 std::vector<const Item*> items;
 int Size()const{return items.size();}
 auto begin()const{return items.begin();}
 auto end()const{return items.end();}
};
constexpr int CONTROL_SIMPLE_LIST=3,CONTROL_DETAILED_LIST=6;
struct Dialog {
 bool playback;List rows;List* m_vecList=&rows;Control group,image,simple,detailed,footer;
 Property GetProperty(const char*)const{return {playback};}
 Control* GetControl(int id){
  switch(id){
   case 9100:return &group;
   case 9101:return &image;
   case 9103:return &footer;
   case CONTROL_SIMPLE_LIST:return &simple;
   case CONTROL_DETAILED_LIST:return &detailed;
   default:assert(false);return nullptr;
  }
 }
 struct Resolution{int iHeight=1080;};Resolution GetCoordsRes()const{return {};}
 void apply(){GEOMETRY}
};
int main(){
 for(int count : {0, 1, 3, 9, 40}){
  Dialog native{false,List(count)};native.apply();
  assert(native.group.h==9 && native.simple.h==9 && native.detailed.h==9);
  for(bool hasFooter : {false, true}){
   if(hasFooter && count==0) continue;
   Dialog d{true,List(count)};
   if(hasFooter) d.rows.items.back()=&d.rows.withHelp;
   d.apply();
   const int expectedRows=count==0?1:std::min(count, hasFooter?21:22);
   const int rowsHeight=38*expectedRows;
   assert(d.simple.h==rowsHeight && d.detailed.h==rowsHeight);
   assert(d.group.x==1220 && d.group.y+d.group.h==1040 && d.group.y>=40);
   assert(d.image.h==d.group.h);
   if(hasFooter){
    assert(d.footer.y==104+rowsHeight+10);
    assert(d.footer.y+36+24==d.group.h);
   }else{
    assert(104+rowsHeight+24==d.group.h);
   }
  }
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
        self.assertEqual((group.findtext('right'),group.findtext('bottom'),group.findtext('width')),('42','40','608'))
        for ident in ('3', '6'):
            node=group.find("control[@id='"+ident+"']")
            self.assertEqual(tuple(node.findtext(tag) for tag in ('left','top','width')), ('24','104','560'))
        rows=layout.find(".//include[@name='CB1PlaybackModeRows']")
        for kind in ('itemlayout','focusedlayout'):
            self.assertEqual(rows.find(kind).attrib, {'width':'560','height':'38'})

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
        self.assertIsNone(fallback, 'Master circuit switching is no longer a control')
        for node in (output,):
            self.assertEqual(node.findtext("dependencies/dependency[@setting='dvbridge.outputmode']"), '4')

    def test_l2_trim_override_is_expert_opt_in_for_the_supported_dv_circuits(self):
        tree = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        settings = ET.parse(tree / 'system/settings/settings.xml')
        option = settings.find(".//setting[@id='dvbridge.disablel2']")
        self.assertIsNotNone(option)
        self.assertEqual(option.findtext('default'), 'false')
        self.assertEqual(option.findtext('level'), '3')
        self.assertEqual([item.text for item in option.findall('dependencies/dependency/or/condition')], ['0', '4', '7'])


if __name__ == '__main__':
    unittest.main()
