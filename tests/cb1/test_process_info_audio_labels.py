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
        self.audio = self.panel.find('./include[@name="DVAudioFields"]/definition')

    def test_source_and_output_have_distinct_native_labels(self):
        rows = {r.find('./param[@name="value"]').get('value'): r
                for r in self.audio.findall('./include[@content="DVInfoRow"]')}
        for name in ('audiosourceformat', 'audiosourcechannels', 'audiobedobjects',
                     'audiopresentation', 'audiodialnorm', 'audiosourcelanguage',
                     'audiosourcebitrate', 'audiooutputtransport', 'audiooutputdata',
                     'audiooutputchannels', 'audiooutputcodec'):
            value = '$INFO[Player.Process('+name+')]'
            self.assertIn(value, rows)
            self.assertIn('!String.IsEmpty(Player.Process('+name+'))',
                          rows[value].find('./param[@name="visible"]').get('value'))
        self.assertNotIn('DVAudioChannels', PANEL.read_text())
        self.assertNotIn('Player.Passthrough', ET.tostring(self.audio, encoding='unicode'))
        self.assertEqual(rows['$VAR[DVSubtitleLanguage]'].find('./param[@name="visible"]').get('value'), 'true')

    def test_formats_are_in_headings_without_duplicate_time_rows(self):
        titles = [p.get('value') for p in self.panel.findall('.//include[@content="DVSection"]/param[@name="label"]')]
        self.assertIn('VIDEO : $VAR[DVSourceFormat]', titles)
        self.assertIn('AUDIO : $INFO[Player.Process(audiosourcetitle)]', titles)
        labels = [p.get('value') for p in self.panel.findall('.//include[@content="DVInfoRow"]/param[@name="label"]')]
        self.assertNotIn('Playback time', labels)
        self.assertNotIn('Source codec', labels)
        video = self.panel.find('./include[@name="DVVideoFields"]')
        self.assertNotIn('Source format', [p.get('value') for p in video.findall('.//param[@name="label"]')])
        self.assertIn('$INFO[Player.Process(audiobedobjectslabel)]', labels)

    def test_every_audio_label_is_registered_and_rows_do_not_ellipsize(self):
        manager = (TREE/'xbmc/GUIInfoManager.cpp').read_text()
        ids = (TREE/'xbmc/guilib/guiinfo/GUIInfoLabels.h').read_text()
        names = set(re.findall(r'Player.Process\((audio\w+)\)', ET.tostring(self.audio, encoding='unicode')))
        for name in names:
            self.assertRegex(manager, r'\{"'+name+r'",\s*PLAYER_PROCESS_\w+\}')
        allocations = re.findall(r'PLAYER_PROCESS_\w+\s*= PLAYER_PROCESS_START \+ (\d+)', ids)
        self.assertEqual(len(allocations), len(set(allocations)))
        row = self.panel.find('./include[@name="DVInfoRow"]')
        for label in row.findall('.//control[@type="fadelabel"]'):
            self.assertEqual(label.findtext('scroll'), 'true')
        video_rows = len(self.panel.findall('./include[@name="DVVideoFields"]/definition/include[@content="DVInfoRow"]'))
        audio_rows = len(self.audio.findall('./include[@content="DVInfoRow"]'))
        maximum = 42 + video_rows * 30 + 24 + 84 + audio_rows * 30
        self.assertLessEqual(108 + maximum + 16 + 24, 1080)
        for col in self.panel.findall('.//control[@type="grouplist"]'):
            self.assertGreaterEqual(int(col.findtext('height')), maximum)
