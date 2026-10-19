"""Execute the registered native processing-label getter with controlled cache facts."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE

class LabelTests(unittest.TestCase):
    def test_processing_labels_preserve_unknown_and_source_semantics(self):
        helper=TREE/'xbmc/guilib/guiinfo/VideoProcessingInfoGUI.h'
        self.assertTrue(helper.exists(), 'native label provider is missing')
        code='\n'.join(line for line in helper.read_text().splitlines() if not line.startswith('#include'))
        ids=(TREE/'xbmc/guilib/guiinfo/GUIInfoLabels.h').read_text()
        ids=ids.split('constexpr uint32_t PLAYER_PROCESS_START',1)[1].split('constexpr uint32_t ADDON_INFOS_START',1)[0]
        playback=(TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVPlaybackInfo.h').read_text()
        manager=(TREE/'xbmc/GUIInfoManager.cpp').read_text()
        registration=manager.split('constexpr std::array<InfoMap, 38> player_process',1)[1].split('// clang-format on',1)[0]
        program=r'''
#include "VideoProcessingInfo.h"
#include <cassert>
#include <string>
#include <map>
#include <sstream>
#include <array>
struct Localizer { std::string Get(int id) const {return std::to_string(id);} };
struct Resources { Localizer GetLocalizeStrings() const {return {};} };
struct CServiceBroker { static Resources GetResourcesComponent() {return {};} };
PLAYBACK
constexpr uint32_t PLAYER_PROCESS_START IDS
struct InfoMap { const char* str; uint32_t val; };
constexpr std::array<InfoMap,38> player_process REGISTRATION
HELPER
bool registeredLabel(const char* key, const VideoProcessingInfo& info, std::string& value) {
 for (const auto& item : player_process)
   if (std::string(item.str)==key) return VideoProcessingInfoGUI::GetLabel(item.val,info,value);
 return false;
}
int main() {
 assert(CDVPlaybackInfo::Transport(0x30334241)=="RGB 4:4:4 / 10-bit");
 assert(CDVPlaybackInfo::Transport(0x48344241)=="RGB 4:4:4 / 16-bit float");
 VideoProcessingInfo info; std::string value;
 assert(registeredLabel("videooutputhdrtype",info,value) && value.empty());
 info.outputType=VideoOutputType::HDR10; info.output.flags=8; info.output.effective=3;
 info.profile=7; info.metadata=true; info.cm4=true; info.blocks[1]=true; info.appliedBlocks[1]=true;
 assert(registeredLabel("videooutputhdrtype",info,value) && value=="hdr10");
 assert(VideoProcessingInfoGUI::GetLabel(PLAYER_PROCESS_VIDEODVCMVERSION,info,value) && value=="CM4 source");
 assert(VideoProcessingInfoGUI::GetLabel(PLAYER_PROCESS_VIDEODVPARSEDBLOCKS,info,value) && value=="L1");
 info.profile=0; info.metadata=false; info.output.hdr10AI=true; info.outputType=VideoOutputType::DolbyVision;
 assert(VideoProcessingInfoGUI::GetLabel(PLAYER_PROCESS_VIDEOOUTPUTHDRTYPE,info,value) && value=="dolbyvision");
 assert(VideoProcessingInfoGUI::GetLabel(PLAYER_PROCESS_VIDEODVCMVERSION,info,value) && value.empty());
 assert(VideoProcessingInfoGUI::GetLabel(PLAYER_PROCESS_VIDEODVPARSEDBLOCKS,info,value) && value.empty());
 info.output.effective=1;
 assert(registeredLabel("videoprocessingmode",info,value) && value=="40867");
 info.output.effective=4;
 assert(registeredLabel("videoprocessingmode",info,value) && value=="40868");
 assert(!VideoProcessingInfoGUI::GetLabel(PLAYER_PROCESS_PIXELFORMAT,info,value));
}
'''.replace('PLAYBACK',playback).replace('IDS',ids).replace('HELPER',code).replace('REGISTRATION',registration)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); (root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20','-I'+str(TREE/'xbmc/cores'),str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

if __name__=='__main__': unittest.main()
