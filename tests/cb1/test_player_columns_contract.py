from pathlib import Path
import unittest
import subprocess
import tempfile
from test_native_video_source import TREE
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[2]
PANEL=ROOT/'projects/Generic/filesystem/usr/share/kodi/media/cb1/IncludesDVProcessInfo.xml'
PATCH=ROOT/'projects/Generic/patches/kodi/kodi-9999-zzzzzzzzz-player-information-layout.patch'
class PlayerColumns(unittest.TestCase):
 def test_fields_are_static_single_line_and_offer_full_details(self):
  panel=ET.parse(PANEL)
  for name in ('DVInfoRow','DVStackedRow'):
   row=panel.find(f'./include[@name="{name}"]')
   values=[x for x in row.iter('control') if x.findtext('label')=='$PARAM[value]']
   self.assertTrue(values)
   for value in values:
    self.assertEqual(value.get('type'),'label')
    self.assertEqual(value.findtext('wrapmultiline'),'false')
    self.assertEqual(value.findtext('scroll'),'false')
  before_menu=PANEL.read_text().split('<include name="CB1PlaybackModeRows">')[0]
  self.assertNotIn('type="fadelabel"',before_menu)
  self.assertNotIn('<scroll>true</scroll>',before_menu)
  self.assertIn('OK: details',before_menu)
  self.assertIn('ACTION_SELECT_ITEM',PATCH.read_text())
 def test_details_are_a_frozen_untruncated_visible_snapshot(self):
  source=(TREE/'xbmc/dialogs/GUIDialogPlayerProcessInfo.cpp').read_text()
  start=source.index('  if (DVBRIDGE::EnhancedInfoEnabled() && action.GetID() == ACTION_SELECT_ITEM)')
  end=source.index('\n  if (DVBRIDGE::EnhancedInfoEnabled() &&',start+3)
  body=source[start:end]
  program=r'''
#include <cassert>
#include <map>
#include <string>
#include <utility>
constexpr int ACTION_SELECT_ITEM=7, WINDOW_DIALOG_TEXT_VIEWER=10;
struct Action { int id; int GetID() const { return id; } };
struct Control {
 int id; bool visible; Control* parent; std::string text;
 bool IsVisible()const{return visible;} int GetID()const{return id;}
 Control* GetParentControl()const{return parent;} std::string GetDescription()const{return text;}
};
namespace DVBRIDGE { bool enhanced=true; bool EnhancedInfoEnabled(){return enhanced;} }
struct CGUIDialogTextViewer {
 std::string heading,text; int opens=0;
 void SetHeading(const std::string& s){heading=s;} void SetText(const std::string& s){text=s;}
 void Open(){++opens;}
};
struct Manager {
 CGUIDialogTextViewer viewer; bool available=true;
 template<class T> T* GetWindow(int){return available? &viewer:nullptr;}
};
struct GUI { Manager manager; Manager& GetWindowManager(){return manager;} };
struct CServiceBroker {static GUI* GetGUI(){static GUI gui;return &gui;}};
struct Dialog {
 std::multimap<int,Control*> lookup;
 auto GetLookupControls(int id)const{return lookup.equal_range(id);}
 bool OnAction(const Action& action){ BODY return false; }
};
int main(){
 Control input{9620,true,nullptr,""},processing{9621,true,nullptr,""},output{9622,true,nullptr,""};
 Control hiddenLayout{9501,false,nullptr,""},hiddenColumn{9630,true,&hiddenLayout,""};
 Control heading{9640,true,nullptr,""};
 Control title{9690,true,&heading,"Input"};
 Control caption{9690,true,&input,"L2 targets"};
 Control value{9690,true,&input,"48 · 100 · 300 · 600 · 1000 · 2000 · 4000 · 10000 nits"};
 Control hidden{9690,false,&processing,"UNUSED METADATA"};
 Control hiddenAncestor{9690,true,&hiddenColumn,"HIDDEN LAYOUT"};
 Control signal{9690,true,&output,"SDR"};
 Dialog dialog;for(auto* c:{&title,&caption,&value,&hidden,&hiddenAncestor,&signal})dialog.lookup.emplace(9690,c);
 auto& manager=CServiceBroker::GetGUI()->manager;
 assert(!dialog.OnAction({1})&&manager.viewer.opens==0);
 DVBRIDGE::enhanced=false;assert(!dialog.OnAction({7})&&manager.viewer.opens==0);
 DVBRIDGE::enhanced=true;assert(dialog.OnAction({7})&&manager.viewer.opens==1);
 assert(manager.viewer.text.find(value.text)!=std::string::npos);
 assert(manager.viewer.text.find("UNUSED")==std::string::npos&&manager.viewer.text.find("HIDDEN")==std::string::npos);
 assert(manager.viewer.text.find("Input\nL2 targets\n")!=std::string::npos);
 assert(manager.viewer.text.find("SDR")!=std::string::npos);
 const auto frozen=manager.viewer.text;value.text="new frame";assert(manager.viewer.text==frozen);
 manager.available=false;assert(dialog.OnAction({7})&&manager.viewer.opens==1);
}
'''.replace('BODY',body)
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary);(root/'check.cpp').write_text(program)
   build=subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror',str(root/'check.cpp'),'-o',str(root/'check')],capture_output=True,text=True)
   self.assertEqual(build.returncode,0,build.stderr)
   run=subprocess.run([str(root/'check')],capture_output=True,text=True)
   self.assertEqual(run.returncode,0,run.stderr)
 def test_processing_contains_only_applied_levels_in_numeric_order(self):
  panel=ET.parse(PANEL)
  row=panel.find('./include[@name="DVUsageChips"]')
  self.assertNotIn('DV.UnappliedBlocks',ET.tostring(row,encoding='unicode'))
  levels=[int(x.get('value')[1:]) for x in row.findall('.//param[@name="level"]')]
  self.assertEqual(levels,sorted(set(levels)))
 def test_source_hdr10plus_survives_dv_processing(self):
  patch=PATCH.read_text()
  self.assertNotIn('+    if (!(active && data.profile && !data.output.hdr10AI))',patch)
 def test_forwarded_trims_have_dedicated_output_properties(self):
  panel=PANEL.read_text(encoding="utf8");patch=PATCH.read_text(encoding="utf8")
  for level in (2,8):
   self.assertIn(f'DV.OutputL{level}Targets',panel)
   self.assertIn(f'SetProperty("DV.OutputL{level}Targets"',patch)
 def test_source_details_are_owned_by_input_only(self):
  panel=ET.parse(PANEL)
  columns=panel.findall('./include[@name="DVProcessLayout"]/definition/control/control[@type="grouplist"]')
  source=('DVSourceMetadataFields','DVStaticMetadataFields','DVHDR10PlusFields')
  for name in source:
   self.assertIn(name,[i.text for i in columns[0].findall('include')])
   self.assertNotIn(name,[i.text for i in columns[1].findall('include')])
 def test_output_handles_native_and_sdr_without_inventing_unknown_signal(self):
  values=ET.parse(PANEL).find('./variable[@name="DVOutputFormat"]').findall('value')
  for signal in ('sdr','hlg','hdr10','hdr10plus','dolbyvision'):
   self.assertTrue(any('videooutputhdrtype),'+signal+')' in v.get('condition','') for v in values))
  self.assertEqual(values[-1].text,'Kodi output')
 def test_complete_inventory_can_be_scrolled(self):
  patch=PATCH.read_text(encoding='utf8')
  self.assertIn('ACTION_PAGE_DOWN',patch)
  self.assertIn('list->SetScrollOffset(std::clamp(',patch)
if __name__=='__main__': unittest.main()
