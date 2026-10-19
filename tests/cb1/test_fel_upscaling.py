"""Exercise the persisted FEL choice through native settings and frame revisions."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET


@unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'), 'Set patched Kodi source tree')
class FELSettingsTests(unittest.TestCase):
    def test_raw_fel_uses_nearest_when_vpp_did_not_supply_a_scaled_surface(self):
        tree = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        source = (tree / 'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        setter = next(line.strip() for line in source.splitlines()
                      if 'dvbridge_renderer_set_fel_nearest(m_renderer,' in line)
        program = r'''
#include <cassert>
enum { DVBRIDGE_P010, DVBRIDGE_Y416 };
struct Layer { int layout; };
bool usedNearest;
void dvbridge_renderer_set_fel_nearest(void*, bool enabled) { usedNearest=enabled; }
void prepare(int requested, const Layer* enhancement) {
  void* m_renderer=nullptr;
  struct {int felUpscaling;} preferences{requested};
  SETTER
}
int main() {
  Layer raw{DVBRIDGE_P010}, scaled{DVBRIDGE_Y416};
  prepare(0,&scaled); assert(!usedNearest);
  prepare(0,&raw); assert(usedNearest); // VPP failure, busy pool or unsupported format.
  prepare(1,&raw); assert(usedNearest);
  prepare(0,nullptr); assert(!usedNearest); // No FEL must reset the previous selection.
}
'''.replace('SETTER', setter)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test.cpp').write_text(program)
            built = subprocess.run(['c++', '-std=c++20', str(root / 'test.cpp'), '-o', str(root / 'test')],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            ran = subprocess.run([str(root / 'test')], capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0, ran.stderr)

    def test_default_and_nearest_are_expert_persisted_frame_preferences(self):
        tree = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        settings = ET.parse(tree / 'system/settings/settings.xml')
        setting = settings.find(".//setting[@id='dvbridge.felupscaling']")
        self.assertIsNotNone(setting, 'Native FEL choice is missing')
        self.assertEqual(setting.findtext('level'), '3')
        self.assertEqual(setting.findtext('default'), '0')
        self.assertEqual([node.text for node in setting.findall('constraints/options/option')], ['0', '1'])
        code = (tree / 'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVOutputSettings.h').read_text()
        code = '\n'.join(line for line in code.splitlines() if not line.startswith('#include'))
        program = r'''
#include <atomic>
#include <bit>
#include <cmath>
#include <cstdint>
#include <memory>
#include <mutex>
#include <string>
#include <map>
#include <cassert>
#include "utils/DVBridgeFastRendering.h"
struct Settings {
  std::map<std::string,int> ints;
  int GetInt(const char* key) { return ints[key]; }
  double GetNumber(const char*) { return 0; }
  bool GetBool(const char*) { return true; }
};
auto stored=std::make_shared<Settings>();
struct Component { auto GetSettings() { return stored; } } component;
struct CServiceBroker { static auto GetSettingsComponent() { return &component; } };
namespace DVBRIDGE { uint64_t NextRevision() { static uint64_t id=1;return ++id; } }
CODE
int main() {
  auto old=DVBRIDGE::FrameOutputSettings();
  assert(old.felUpscaling==0);
  assert(DVBRIDGE::FrameOutputSettings().revision==old.revision);
  stored->ints["dvbridge.felupscaling"]=1;
  auto nearest=DVBRIDGE::FrameOutputSettings();
  assert(nearest.felUpscaling==1 && nearest.revision!=old.revision);
  assert(DVBRIDGE::FrameOutputSettings().revision==nearest.revision);
  assert(nearest.output==old.output && nearest.fastChroma==old.fastChroma);
  stored->ints["dvbridge.felupscaling"]=0;
  auto reset=DVBRIDGE::FrameOutputSettings();
  assert(reset.felUpscaling==0 && reset.revision!=nearest.revision);
  stored->ints["dvbridge.felupscaling"]=99;
  auto invalid=DVBRIDGE::FrameOutputSettings();
  assert(invalid.felUpscaling==0 && invalid.revision==reset.revision);
}
'''.replace('CODE', code)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test.cpp').write_text(program)
            result = subprocess.run(['c++', '-std=c++20', '-I' + str(tree / 'xbmc'),
                                     str(root / 'test.cpp'), '-o', str(root / 'test')],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(root / 'test')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
