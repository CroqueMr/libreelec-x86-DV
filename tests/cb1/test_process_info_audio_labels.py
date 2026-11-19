"""Check the compact panel consumes native source/output information."""
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET
from test_native_video_source import TREE

PANEL = Path(__file__).resolve().parents[2] / 'projects/Generic/filesystem/usr/share/kodi/media/cb1/IncludesDVProcessInfo.xml'


class AudioLabelsTests(unittest.TestCase):
    def setUp(self):
        self.panel = ET.parse(PANEL)
        # Source audio sits in the Input column, Kodi's audio output in the Output column.
        self.audio = [self.panel.find('./include[@name="'+name+'"]/definition')
                      for name in ('DVInputFields', 'DVOutputFields')]

    def test_source_and_output_have_distinct_native_labels(self):
        rows = {r.find('./param[@name="value"]').get('value'): r
                for column in self.audio for r in column.findall('./include[@content="DVInfoRow"]')}
        # Source channels and format share the Format row; both guard it.
        audio_format = ET.tostring(self.panel.find('./variable[@name="DVAudioFormat"]'), encoding='unicode')
        format_row = rows['$VAR[DVAudioFormat]'].find('./param[@name="visible"]').get('value')
        for name in ('audiosourceformat', 'audiosourcechannels'):
            self.assertIn('$INFO[Player.Process('+name+')]', audio_format)
            self.assertIn('!String.IsEmpty(Player.Process('+name+'))', format_row)
        for name in ('audiobedobjects',
                     'audiodialnorm',
                     'audiosourcebitrate', 'audiooutputtransport', 'audiooutputdata',
                     'audiooutputchannels', 'audiooutputcodec'):
            value = '$INFO[Player.Process('+name+')]'
            self.assertIn(value, rows)
            self.assertIn('!String.IsEmpty(Player.Process('+name+'))',
                          rows[value].find('./param[@name="visible"]').get('value'))
        self.assertNotIn('DVAudioChannels', PANEL.read_text())
        self.assertNotIn('Player.Passthrough', PANEL.read_text())
        video = {r.find('./param[@name="value"]').get('value'): r for r in
                 self.panel.findall('./include[@name="DVOutputFields"]/definition/include[@content="DVInfoRow"]')}
        self.assertNotIn('$VAR[DVSubtitleLanguage]',video)

    def test_formats_are_in_headings_without_duplicate_time_rows(self):
        headings = {h.find('./param[@name="title"]').get('value'): h
                    for h in self.panel.findall('.//include[@content="DVColumnHeading"]')}
        self.assertEqual(headings['Input'].find('./param[@name="primary"]').get('value'), '$VAR[DVSourceFormat]')
        self.assertEqual(headings['Input'].find('./param[@name="secondary"]').get('value'), '$VAR[DVInputAudio]')
        self.assertEqual(headings['Output'].find('./param[@name="secondary"]').get('value'), '$VAR[DVOutputAudio]')
        self.assertIn('$INFO[Player.Process(audiosourcetitle)]',
                      ET.tostring(self.panel.find('./variable[@name="DVInputAudio"]'), encoding='unicode'))
        self.assertIn('$INFO[Player.Process(audiooutputtransport)]',
                      ET.tostring(self.panel.find('./variable[@name="DVOutputAudio"]'), encoding='unicode'))
        labels = [p.get('value') for p in self.panel.findall('.//include[@content="DVInfoRow"]/param[@name="label"]')]
        self.assertNotIn('Playback time', labels)
        self.assertNotIn('Source codec', labels)
        self.assertNotIn('$VAR[DVSourceFormat]', [p.get('value') for p in
                         self.panel.findall('.//include[@content="DVInfoRow"]/param[@name="value"]')])
        self.assertIn('$INFO[Player.Process(audiobedobjectslabel)]', labels)

    def test_every_audio_label_is_registered_and_rows_are_static(self):
        manager = (TREE/'xbmc/GUIInfoManager.cpp').read_text()
        ids = (TREE/'xbmc/guilib/guiinfo/GUIInfoLabels.h').read_text()
        names = set(re.findall(r'Player.Process\((audio\w+)\)', PANEL.read_text()))
        for name in names:
            self.assertRegex(manager, r'\{"'+name+r'",\s*PLAYER_PROCESS_\w+\}')
        allocations = re.findall(r'PLAYER_PROCESS_\w+\s*= PLAYER_PROCESS_START \+ (\d+)', ids)
        self.assertEqual(len(allocations), len(set(allocations)))
        row = self.panel.find('./include[@name="DVInfoRow"]')
        for label in row.findall('.//control[@type="fadelabel"]'):
            self.assertEqual(label.findtext('scroll'), 'true')
        # The overlay retains the old O handler and adds no focus, paging or popup action.
        source=(TREE/'xbmc/dialogs/GUIDialogPlayerProcessInfo.cpp').read_text()
        for action in ('ACTION_PAGE_DOWN','ACTION_MOVE_DOWN','ACTION_SELECT_ITEM','SetScrollOffset'):
            self.assertNotIn(action,source)
        for value in row.findall('./definition/control[@type="label"]'):
            self.assertEqual(value.findtext('scroll'),'false')
            self.assertEqual(value.findtext('wrapmultiline'),'false')
