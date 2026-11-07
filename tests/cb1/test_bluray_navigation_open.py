"""Execute the shipped ownership gate before default-stream selection.

The renderer/default selector is a sentinel after the real production prefix;
this checks ordering/ownership, not a replacement subtitle implementation.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class BlurayNavigationOpen(unittest.TestCase):
    def test_live_navigation_owns_selected_streams_before_state_publication(self):
        source = (TREE / 'xbmc/cores/VideoPlayer/VideoPlayer.cpp').read_text()
        opening = body(source, 'void CVideoPlayer::OpenDefaultStreams(bool reset)')
        self.assertEqual(opening.count('  bool valid;'), 1)
        prefix = opening.split('  bool valid;', 1)[0]
        program = r'''
#include <cassert>
#include <memory>
enum class MenuType { NONE, NATIVE };
enum { DVDSTREAM_TYPE_BLURAY, OTHER_INPUT };
struct CDVDInputStream {
 struct IMenus {
  virtual ~IMenus()=default;
  virtual MenuType GetSupportedMenuType()=0;
 };
 virtual ~CDVDInputStream()=default;
 int kind=DVDSTREAM_TYPE_BLURAY;
 bool IsStreamType(int t) const { return kind==t; }
};
struct Input : CDVDInputStream, CDVDInputStream::IMenus {
 MenuType type=MenuType::NATIVE;
 MenuType GetSupportedMenuType() override { return type; }
};
struct CVideoPlayer {
 std::shared_ptr<CDVDInputStream> m_pInputStream=std::make_shared<Input>();
 struct { MenuType menuType=MenuType::NONE; } m_State;
 struct { int iSelectedAudioStream=-1, iSelectedSPUStream=-1; } m_dvd;
 bool visible=false, preference=false;
 int automaticSelections=0;
 void OpenDefaultStreams(bool reset=false);
};
void CVideoPlayer::OpenDefaultStreams(bool reset) PREFIX
 // Sentinel for the real automatic-selection path following this gate.
 ++automaticSelections; visible=preference;
}
int main() {
 // Prepare has cleared the published state. Disc events already own tracks/PG.
 CVideoPlayer early;early.m_dvd.iSelectedAudioStream=0x1104;
 early.m_dvd.iSelectedSPUStream=0x12a2;early.visible=true;
 early.OpenDefaultStreams();
 assert(early.visible && early.automaticSelections==0 &&
        "early disc PG=on must survive default preferences");
 CVideoPlayer spuOnly;spuOnly.m_dvd.iSelectedSPUStream=0x12a2;
 spuOnly.visible=true;spuOnly.OpenDefaultStreams();
 assert(spuOnly.visible && spuOnly.automaticSelections==0);
 CVideoPlayer authorOff;authorOff.preference=true;
 authorOff.m_dvd.iSelectedAudioStream=0x1104;
 authorOff.OpenDefaultStreams();
 assert(!authorOff.visible && authorOff.automaticSelections==0);
 // Direct MPLS still uses ordinary defaults, regardless of a stale UI cache.
 for (bool exposesMenus : {false,true}) {
  for (auto cache : {MenuType::NONE,MenuType::NATIVE}) {
   CVideoPlayer direct;
   if (exposesMenus) {
    auto input=std::make_shared<Input>();input->type=MenuType::NONE;
    direct.m_pInputStream=input;
   } else direct.m_pInputStream=std::make_shared<CDVDInputStream>();
   direct.m_State.menuType=cache;direct.m_dvd.iSelectedSPUStream=0x12a2;
   direct.visible=true;direct.OpenDefaultStreams();
   assert(!direct.visible && direct.automaticSelections==1);
  }
 }
 // With no disc stream selected yet, defaults remain available. A later event
 // owns subsequent openings even if published playback state is still NONE.
 CVideoPlayer late;late.OpenDefaultStreams();
 assert(late.automaticSelections==1 && !late.visible);
 late.m_dvd.iSelectedAudioStream=0x1102;late.visible=true;
 late.OpenDefaultStreams();
 assert(late.visible && late.automaticSelections==1);
 // Preserve the existing non-Blu-ray navigator rule.
 CVideoPlayer dvd;dvd.m_pInputStream->kind=OTHER_INPUT;
 dvd.m_dvd.iSelectedSPUStream=2;dvd.visible=true;dvd.OpenDefaultStreams();
 assert(dvd.visible && dvd.automaticSelections==0);
}
'''.replace('PREFIX', prefix)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test.cpp').write_text(program)
            built = subprocess.run(['c++', '-std=c++20', '-fsanitize=address,undefined',
                                    str(root / 'test.cpp'), '-o', str(root / 'test')],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            result = subprocess.run([str(root / 'test')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
