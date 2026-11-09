from pathlib import Path
import unittest
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[2]
PANEL=ROOT/'projects/Generic/filesystem/usr/share/kodi/media/cb1/IncludesDVProcessInfo.xml'
PATCH=ROOT/'projects/Generic/patches/kodi/kodi-9999-zzzzzzzzz-player-information-layout.patch'
class PlayerColumns(unittest.TestCase):
 def test_fields_are_single_line_and_scroll(self):
  panel=ET.parse(PANEL)
  for name in ('DVInfoRow','DVStackedRow'):
   row=panel.find(f'./include[@name="{name}"]')
   values=[x for x in row.iter('control') if x.findtext('label')=='$PARAM[value]']
   self.assertTrue(values)
   for value in values:
    self.assertEqual(value.get('type'),'label')
    self.assertEqual(value.findtext('wrapmultiline'),'false')
    self.assertEqual(value.findtext('scroll'),'true')
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
