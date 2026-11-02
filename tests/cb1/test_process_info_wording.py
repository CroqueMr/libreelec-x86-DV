"""The native label controls retain long values and all processing fields."""
from pathlib import Path
import os
import re
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET


class ProcessInfoWordingTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'), 'Set patched Kodi source tree')
    def test_unused_blocks_exclude_locally_applied_and_forwarded_metadata(self):
        from test_native_video_source import body
        tree = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        dialog = (tree/'xbmc/dialogs/GUIDialogPlayerProcessInfo.cpp').read_text()
        statement = re.search(r'^\s*SetProperty\("DV.UnappliedBlocks",[^\n]+', dialog, re.M).group()
        header = (tree/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVPlaybackInfo.h').read_text()
        formatter = body(header, 'static std::string Blocks(')
        program = r'''
#include "cores/VideoProcessingInfo.h"
#include <cassert>
struct CDVPlaybackInfo { static std::string Blocks(const std::bitset<256>& blocks) FORMATTER };
int main() {
  VideoProcessingInfo data;
  bool metadata = true;
  auto displayed = [&] {
    std::string result;
    auto SetProperty = [&](const char*, const std::string& value) { result = value; };
    const auto applied = data.AppliedBlocks();
    STATEMENT
    return result;
  };
  // TV-Led Master: L1/L4 are forwarded, L5 is geometry, L6 stays local/unused.
  for (unsigned level : {1u, 4u, 5u, 6u}) data.blocks[level] = true;
  data.appliedBlocks[5] = true;
  for (unsigned level : {1u, 3u, 4u, 5u, 9u, 11u, 254u}) data.transmittedBlocks[level] = true;
  assert(displayed() == "L6" && "Forwarded L1/L4 must not be reported unused");
  // Suppressed L2 remains unused unless a local conversion consumed it.
  data.blocks[2] = true;
  assert(displayed() == "L2 L6");
  data.appliedBlocks[2] = true;
  assert(displayed() == "L6");
  // HDR10 conversion has no DV-forwarding exemption.
  data.blocks[2] = false;
  data.transmittedBlocks.reset();
  data.appliedBlocks[1] = data.appliedBlocks[6] = true;
  assert(displayed() == "L4");
  data.appliedBlocks[4] = true;
  assert(displayed().empty());
  metadata = false;
  data.appliedBlocks.reset();
  assert(displayed().empty());
}
'''.replace('FORMATTER', formatter).replace('STATEMENT', statement)
        with tempfile.TemporaryDirectory(prefix='cb1-metadata-use-') as temp:
            root = Path(temp)
            (root/'test.cpp').write_text(program)
            built = subprocess.run(['c++', '-std=c++20', '-I'+str(tree/'xbmc'),
                                    str(root/'test.cpp'), '-o', str(root/'test')],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            ran = subprocess.run([str(root/'test')], capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0, ran.stderr)

    def test_compact_labels_keep_all_fields_and_native_overflow_scrolling(self):
        panel=ET.parse(Path(__file__).resolve().parents[2]/
            'projects/Generic/filesystem/usr/share/kodi/media/cb1/IncludesDVProcessInfo.xml')
        rows=panel.findall('.//include[@content="DVInfoRow"]')
        self.assertEqual(len(rows),68)
        self.assertIsNone(panel.find('./variable[@name="DVAudioOutput"]'))
        self.assertTrue(any(r.find('./param[@name="value"]').get('value') ==
                            '$INFO[Player.Process(audiooutputtransport)]' for r in rows))
        expected={'DV.ParsedBlocks':'Source blocks','DV.AppliedBlocks':'Applied blocks',
                  'DV.UnappliedBlocks':'Unused blocks','DV.MinimumLinkBits':'$LOCALIZE[40848]',
                  'DV.Fallback':'Fallback'}
        for prop,label in expected.items():
            row=next(r for r in rows if r.find('./param[@name="value"]').get('value')==
                     '$INFO[Window(playerprocessinfo).Property('+prop+')]')
            self.assertEqual(row.find('./param[@name="label"]').get('value'),label)
        controls=panel.findall('./include[@name="DVInfoRow"]/definition/control/control')
        self.assertEqual(len(controls),2)
        self.assertEqual(controls[0].get('type'),'label')
        self.assertEqual(controls[1].get('type'),'fadelabel')
        self.assertEqual(controls[1].findtext('scroll'),'true')
        self.assertEqual(controls[1].findtext('resetonlabelchange'),'false')
