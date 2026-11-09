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
 def test_fields_are_static_single_line_without_new_interactions(self):
  panel=ET.parse(PANEL)
  row=panel.find('./include[@name="DVInfoRow"]')
  value=next(x for x in row.iter('control') if x.findtext('label')=='$PARAM[value]')
  self.assertEqual(value.get('type'),'label')
  self.assertEqual(value.findtext('wrapmultiline'),'false')
  self.assertEqual(value.findtext('scroll'),'false')
  text=PANEL.read_text(encoding='utf-8')
  for unwanted in ('type="fadelabel"','<scroll>true</scroll>','OK: details','Up/Down: more','9690'):
   self.assertNotIn(unwanted,text)
  patch=PATCH.read_text(encoding='utf-8')
  for unwanted in ('ACTION_SELECT_ITEM','ACTION_MOVE_UP','ACTION_PAGE_DOWN','SetScrollOffset','GUIDialogTextViewer','FitPanel'):
   self.assertNotIn(unwanted,patch)
 def test_native_o_handler_keeps_the_old_behavior(self):
  source=(TREE/'xbmc/dialogs/GUIDialogPlayerProcessInfo.cpp').read_text()
  start=source.index('bool CGUIDialogPlayerProcessInfo::OnAction(')
  body=source[source.index('{',start):].strip()
  for unwanted in ('ACTION_SELECT_ITEM','ACTION_MOVE_UP','ACTION_MOVE_DOWN','ACTION_PAGE_UP','ACTION_PAGE_DOWN'):
   self.assertNotIn(unwanted,body)
  program=r'''
#include <cassert>
#include <initializer_list>
constexpr int ACTION_PLAYER_PROCESS_INFO=7;
struct CAction {int id;int GetID()const{return id;}};
struct CGUIDialog {virtual ~CGUIDialog()=default;virtual bool OnAction(const CAction&){return false;}};
struct CDVPlaybackModes {static inline bool enabled=false;static inline int shown=0;
 static bool MenuEnabled(){return enabled;}static void ShowMenu(){++shown;}};
struct CGUIDialogPlayerProcessInfo:CGUIDialog {
 int closed=0;bool force=false;
 void Close(bool f=false){++closed;force=f;}
 bool OnAction(const CAction& action) override BODY
};
int main(){
 CGUIDialogPlayerProcessInfo dialog;
 for(int action:{1,2,3,4,5})assert(!dialog.OnAction({action}));
 assert(dialog.closed==0&&CDVPlaybackModes::shown==0);
 assert(dialog.OnAction({7})&&dialog.closed==1&&!dialog.force);
 CDVPlaybackModes::enabled=true;
 assert(dialog.OnAction({7})&&dialog.closed==2&&dialog.force&&CDVPlaybackModes::shown==1);
}
'''.replace('BODY',body).replace('\\n#include','\n#include')
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary);(root/'check.cpp').write_text(program)
   build=subprocess.run(['c++','-std=c++20','-DHAVE_DVBRIDGE','-Wall','-Wextra','-Werror',str(root/'check.cpp'),'-o',str(root/'check')],capture_output=True,text=True)
   self.assertEqual(build.returncode,0,build.stderr)
   run=subprocess.run([str(root/'check')],capture_output=True,text=True)
   self.assertEqual(run.returncode,0,run.stderr)
 def test_layout_preserves_pr92_geometry_and_has_no_scroller(self):
  panel=ET.parse(PANEL)
  columns=panel.findall('./include[@name="DVProcessLayout"]/definition/control/control[@type="grouplist"]')
  self.assertEqual([x.findtext('left') for x in columns],['40','654','1268'])
  for column in columns:
   self.assertEqual(column.findtext('width'),'548')
   self.assertEqual(column.findtext('top'),'108')
   self.assertIsNone(column.find('onup'))
   self.assertIsNone(column.find('pagecontrol'))
  row=panel.find('./include[@name="DVInfoRow"]')
  dimensions={p.get('name'):p.get('default') for p in row.findall('param')}
  self.assertEqual(dimensions['labelwidth'],'252')
  self.assertEqual(dimensions['valueleft'],'264')
  source=(TREE/'xbmc/dialogs/GUIDialogPlayerProcessInfo.cpp').read_text()
  self.assertIn('const float height = 108.0f + content + 16.0f;',source)
  self.assertIn('0, 20, FONT_STYLE_NORMAL',source)
  self.assertNotIn('list->SetHeight',source)
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
 def test_pr92_grouping_distinguishes_source_facts_from_applied_values(self):
  panel=ET.parse(PANEL)
  columns=panel.findall('./include[@name="DVProcessLayout"]/definition/control/control[@type="grouplist"]')
  self.assertIn('DVSourceMetadataFields',[i.text for i in columns[1].findall('include')])
  for name in ('DVStaticMetadataFields','DVHDR10PlusFields'):
   self.assertIn(name,[i.text for i in columns[0].findall('include')])
   self.assertNotIn(name,[i.text for i in columns[1].findall('include')])
  applied=ET.tostring(panel.find('./include[@name="DVSourceMetadataFields"]'),encoding='unicode')
  self.assertIn('DV.AppliedBlocks',applied)
  self.assertNotIn('DV.L2Targets',applied)
  self.assertNotIn('DV.L8Targets',applied)
 def test_output_handles_native_and_sdr_without_inventing_unknown_signal(self):
  values=ET.parse(PANEL).find('./variable[@name="DVOutputFormat"]').findall('value')
  for signal in ('sdr','hlg','hdr10','hdr10plus','dolbyvision'):
   self.assertTrue(any('videooutputhdrtype),'+signal+')' in v.get('condition','') for v in values))
  self.assertEqual(values[-1].text,'Kodi output')
if __name__=='__main__': unittest.main()
