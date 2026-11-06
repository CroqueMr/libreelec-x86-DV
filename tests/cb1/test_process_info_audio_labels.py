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
                     'audiopresentation', 'audiodialnorm', 'audiosourcelanguage',
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
        self.assertIsNone(video['$VAR[DVSubtitleLanguage]'].find('./param[@name="visible"]'))

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

    def test_every_audio_label_is_registered_and_rows_do_not_ellipsize(self):
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
        # A column advances by each control's top plus its height (GUIControlGroupList::Size),
        # an auto-height textbox by at least its minimum: a caption row is 28 px, a stacked one 56.
        def advance(name):
            total = 0.0
            for control in self.panel.findall('./include[@name="'+name+'"]/definition/control'):
                height = control.find('height')
                total += float(control.findtext('top') or 0) + float(
                    height.get('min') if height.text == 'auto' else height.text)
            return total
        pitch = {name: advance(name) for name in ('DVInfoRow', 'DVStackedRow', 'DVSection', 'DVBlockChips')}
        pitch['DVUsageChips'] = pitch['DVBlockChips']
        self.assertEqual((pitch['DVInfoRow'], pitch['DVStackedRow']), (28, 56))
        def rows(name):
            return sum(pitch.get(i.get('content') or i.text) or rows(i.get('content') or i.text)
                       for i in self.panel.findall('./include[@name="'+name+'"]/definition/include'))
        frame = advance('DVColumnSpacer') + advance('DVColumnEnd')
        # The dialog keeps a 24 px margin above and below the panel (FitPanel) and cuts a taller
        # column above the meter strip. The Input column, whose rows can all show together,
        # must never be cut.
        room = 1080 - 2 * 24
        self.assertLessEqual(108 + frame + rows('DVInputFields') + rows('DVInputDolbyVisionFields') + 16, room)
        shown = {}
        for row in self.panel.findall('.//include[@content]'):
            label = row.find('./param[@name="label"]')
            if row.get('content') in pitch and label is not None:
                shown.setdefault(label.get('value'), pitch[row.get('content')])
        def height(labels, chips=0):
            return 108 + frame + sum(shown[label] for label in labels) + chips * pitch['DVUsageChips'] + 16
        rendering = ['Rendering', 'Decoded surface', 'Creative trims']
        metadata = ['Source metadata', 'Mastering max / min', 'MaxCLL / MaxFALL', 'RPU max / min',
                    'RPU CLL / FALL', 'L1 PQ min/max/avg', 'L1 nits min/max/avg', 'L2 trim targets',
                    'L3 offset min/max/avg', 'L5 L/R/T/B', 'L8 trim targets', 'L9 source primaries',
                    'L11 content type', 'L254 DM mode / version', 'Used by CB1']
        # Processing for a profile 8.1 CM4.0 file while CB1 renders Dolby Vision: the file's
        # HDR10+ and the FEL row are hidden then, and the column fits uncut too.
        self.assertLessEqual(height(rendering + metadata, chips=1), room)
        # The tallest Processing column: a profile 7 FEL CM4.0 file in HDR10 Rendering Reference,
        # which adds the FEL and the display it maps to. Its link minimum sits under Output.
        self.assertLessEqual(height(rendering + ['FEL / upscaling', 'Display mapping', 'Black level'] +
                                    metadata, chips=1), room)
        self.assertLessEqual(height(['Video', 'Display output', 'Signal intent', 'Scanout container',
                                     '$LOCALIZE[40848]', 'Precision', 'Committed source', 'Subtitles',
                                     'Audio', 'Transport', 'Data', 'Output channels', 'Decoder',
                                     'Buffers', 'Video queue / data', 'Audio queue / data']), room)
