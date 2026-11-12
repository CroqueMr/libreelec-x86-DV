"""CM4 UI and frame settings must stay independent of L2 removal and AI modes."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET


@unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'), 'Set patched Kodi source tree')
class CMv40Tests(unittest.TestCase):
    def test_display_separates_original_cm_from_committed_cm4_addition(self):
        from test_native_video_source import body
        tree=Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        code=body((tree/'xbmc/guilib/guiinfo/VideoProcessingInfoGUI.h').read_text(),
                  'static std::string CMVersion(')
        program=r'''
#include "cores/VideoProcessingInfo.h"
#include <cassert>
struct CDVPlaybackInfo {enum {HDMI=1,CM4=2};};
std::string label(const VideoProcessingInfo& info) BODY
int main(){
 VideoProcessingInfo s;assert(label(s).empty());s.metadata=true;
 assert(label(s)=="CM2.9");
 s.output.flags=CDVPlaybackInfo::HDMI;s.output.effective=1;
 assert(label(s)=="CM2.9 (CM4 not added)");
 s.output.flags|=CDVPlaybackInfo::CM4;
 assert(label(s)=="CM2.9 (CM4 added)");
 s.output.effective=5;assert(label(s)=="CM2.9 (CM4 added)");
 s.cm4=true;assert(label(s)=="CM4.0 (original)");
 s.cm4=false;s.output.hdr10AI=true;assert(label(s)=="CM2.9");
 s.output.hdr10AI=false;s.output.authoredLegacy=true;assert(label(s)=="CM2.9");
 s.output.authoredLegacy=false;s.output.effective=3;assert(label(s)=="CM2.9");
 s.output.effective=1;s.output.flags=CDVPlaybackInfo::HDMI;
 assert(label(s)=="CM2.9 (CM4 not added)");
}
'''.replace('BODY',code)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'test.cpp').write_text(program)
            built=subprocess.run(['c++','-std=c++20','-I'+str(tree/'xbmc'),str(root/'test.cpp'),
                                  '-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(ran.returncode,0,ran.stderr)

    def test_all_five_choices_are_user_selectable_with_conditional_controls(self):
        tree=Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        settings=ET.parse(tree/'system/settings/settings.xml')
        append=settings.find(".//setting[@id='dvbridge.cmv40']")
        self.assertIsNotNone(append)
        self.assertEqual(append.findtext('default'),'0')
        self.assertEqual(append.findtext('level'),'2')
        self.assertNotEqual(append.findtext('visible'),'false')
        self.assertEqual([x.text for x in append.findall('constraints/options/option')],['0','1','2','3','4'])
        trigger=settings.find(".//setting[@id='dvbridge.cmv40trigger']")
        margin=settings.find(".//setting[@id='dvbridge.cmv40headroom']")
        self.assertEqual(trigger.findtext("dependencies/dependency[@setting='dvbridge.cmv40']"),'3')
        self.assertEqual(margin.findtext("dependencies/dependency[@setting='dvbridge.cmv40']"),'4')
        self.assertEqual((margin.findtext('default'),margin.findtext('constraints/minimum'),margin.findtext('constraints/maximum')),('20','0','50'))

    def test_frame_preferences_exclude_non_authored_modes_and_track_revisions(self):
        from test_native_video_source import body
        repo=Path(__file__).resolve().parents[2]
        tree=Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        s=(tree/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVOutputSettings.h').read_text()
        enums='\n'.join(re.findall(r'enum class (?:OutputMode|HDR10SourceMode|HLGSourceMode)[^;]+;',s))
        preferences=s.split('struct OutputPreferences',1)[1].split('inline std::mutex&',1)[0]
        render=(tree/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        prepare=body(render,'CDVBridgeGLES::FrameStatus CDVBridgeGLES::PrepareFrame(')
        selection=re.search(r'  auto policy = selected \?[^;]+;',prepare).group()
        rejection=prepare[prepare.index('  if (!selected &&'):prepare.index('  // Capture the proven observation key')]
        admission=re.search(r'const auto cmv40 = ([^;]+);',render).group(1)
        program='''
#include "cb1_cmv40.h"
#include "dvbridge_policy.h"
#include <cassert>
#include <bit>
#include <cmath>
#include <cstdint>
#include <initializer_list>
namespace DVBRIDGE { ENUMS struct OutputPreferences PREFERENCES }
int main(){
 using namespace DVBRIDGE;
 OutputPreferences p;
 assert(p.CMv40Options(DVBRIDGE_MODE_STANDARD).mode==CB1_CMV40_DISABLED);
 p.cmv40Mode=4;p.cmv40Headroom=20;p.peak=1234;p.disableL2Trims=true;
 enum class FrameStatus{Ready,Unsupported};
 cb1_cmv40_options prepared{};unsigned preparations=0;
 auto prepareOptions=[&](const dvbridge_policy* selected){auto preferences=p;
  SELECTION
  REJECTION
  prepared=ADMISSION;++preparations;return FrameStatus::Ready;
 };
 assert(prepareOptions(nullptr)==FrameStatus::Ready && prepared.mode==CB1_CMV40_AUTO2);
 const auto authored=p;
 p.output=OutputMode::HDR10;p.method=1; // Unconfigured Expert is refused before CM4 preparation.
 assert(!p.ProfileValid(DVBRIDGE_MODE_HDR10_EXPERT));
 assert(prepareOptions(nullptr)==FrameStatus::Unsupported && preparations==1);
 p.output=OutputMode::AdaptiveB;p.peak=0;
 assert(prepareOptions(nullptr)==FrameStatus::Unsupported && preparations==1);
 p=authored;
 for(auto mode:{DVBRIDGE_MODE_STANDARD,DVBRIDGE_MODE_MASTER_REFERENCE}){
  auto o=p.CMv40Options(mode);
  assert(o.mode==CB1_CMV40_AUTO2 && o.headroom==20 && o.tv_peak==1234);
  assert(p.CMv40Options(mode,true).mode==CB1_CMV40_DISABLED);
  assert(p.L2TrimsDisabled(mode) && !p.L2TrimsDisabled(mode,true));
 }
 for(auto mode:{DVBRIDGE_MODE_DISABLED,DVBRIDGE_MODE_ENHANCED_DV,DVBRIDGE_MODE_HDR10_BASIC,DVBRIDGE_MODE_HDR10_EXPERT,DVBRIDGE_MODE_HDR10PLUS,DVBRIDGE_MODE_SDR})
  assert(p.CMv40Options(mode).mode==CB1_CMV40_DISABLED);
 auto other=p;assert(p.SameValues(other));
 other.cmv40Mode=0;assert(!p.SameValues(other));other=p;
 other.cmv40Trigger=4000;assert(!p.SameValues(other));other=p;
 other.cmv40Headroom=30;assert(!p.SameValues(other));
}
'''.replace('ENUMS',enums).replace('PREFERENCES',preferences).replace('SELECTION',selection).replace('REJECTION',rejection).replace('ADMISSION',admission)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'test.cpp').write_text(program)
            prefix=Path(os.environ['FFMPEG_TEST_PREFIX'])
            cmd=['c++','-std=c++20','-DHAVE_DVBRIDGE','-I'+str(repo/'CB1/src'),'-I'+str(prefix/'include'),str(root/'test.cpp'),'-o',str(root/'test')]
            built=subprocess.run(cmd,text=True,capture_output=True)
            self.assertEqual(built.returncode,0,built.stderr)
            result=subprocess.run([str(root/'test')],text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_transmitted_blocks_describe_committed_append_not_source_cm(self):
        tree=Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        source=(tree/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVStreamTelemetry.h').read_text()
        from test_native_video_source import body
        method=body(source,'std::bitset<256> TransmittedBlocks() const')
        program='''
#include <bitset>
#include <cassert>
struct CDVPlaybackInfo {enum {HDMI=1};};
struct S {
 struct {unsigned flags=1;bool authoredLegacy=false,l2TrimsDisabled=false,cmv40Appended=false,lldv=false;} output;
 bool metadata=true;std::bitset<256> blocks;
 std::bitset<256> TransmittedBlocks()const BODY
};
int main(){
 S s;s.blocks[1]=s.blocks[2]=true;
 assert(!s.TransmittedBlocks()[254]);
 s.output.cmv40Appended=true;
 auto sent=s.TransmittedBlocks();assert(sent[1] && sent[2] && sent[3] && sent[9] && sent[11] && sent[254]);
 assert(!s.blocks[254]);
 s.output.l2TrimsDisabled=true;assert(!s.TransmittedBlocks()[2]);
 s.output.lldv=true;assert(s.TransmittedBlocks().none());
 s.output.lldv=false;
 s.output.flags=0;assert(s.TransmittedBlocks().none());
}
'''.replace('BODY',method)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'test.cpp').write_text(program)
            built=subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-o',str(root/'test')],text=True,capture_output=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran=subprocess.run([str(root/'test')],text=True,capture_output=True)
            self.assertEqual(ran.returncode,0,ran.stderr)

if __name__=='__main__':unittest.main()
