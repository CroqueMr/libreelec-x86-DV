"""HDR10+ requires a dynamic transport, not just static PQ support."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class HDR10PlusSelectionTests(unittest.TestCase):
    def test_dynamic_output_admission_preserves_other_routes(self):
        source=(TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVOutputSelection.h').read_text()
        implementation=body(source,'inline OutputSelection SelectOutput(')
        program=r'''
#include "cores/VideoPlayer/DVDCodecs/Video/DVPlaybackInfo.h"
#include "dvbridge_policy.h"
#include <atomic>
#include <cassert>
namespace DVBRIDGE {
enum class OutputMode {Standard,HDR10,Disabled};
enum class HDR10SourceMode {Native,ReferenceDV};
enum class OutputRoute {Vanilla,NativeDV,HDR10};
struct OutputSelection {OutputRoute route{};dvbridge_policy policy{};OutputReason reason{};};
struct OutputPreferences {
 OutputMode output=OutputMode::HDR10;HDR10SourceMode hdr10Source=HDR10SourceMode::Native;
 bool allowMasterFallback=true;dvbridge_mode mode=DVBRIDGE_MODE_HDR10PLUS;
 bool ProfileValid()const{return true;}
 dvbridge_policy Policy()const{return {.revision=1,.mode=mode};}
 dvbridge_policy HDR10Policy()const{return Policy();}
};
using Caps=OutputCapabilities;
OutputSelection select(const OutputPreferences& preferences,const Caps& caps) BODY
}
int main(){
 using namespace DVBRIDGE;OutputPreferences p;Caps c;
 c.sourceKnown=c.isDV=c.processingKnown=c.hdr10=c.nativeDV=true;
 for(auto& mode:c.processing)mode={true,OutputReason::None};
 auto r=select(p,c);
 assert(r.route==OutputRoute::HDR10 && r.policy.mode==DVBRIDGE_MODE_HDR10_BASIC && r.reason!=OutputReason::None);
 c.hdr10plus=true;r=select(p,c);
 assert(r.route==OutputRoute::HDR10 && r.policy.mode==DVBRIDGE_MODE_HDR10PLUS && r.reason==OutputReason::None);
 c.hdr10=false;r=select(p,c);assert(r.route==OutputRoute::Vanilla);
 c.hdr10=true;p.mode=DVBRIDGE_MODE_HDR10_EXPERT;c.hdr10plus=false;
 r=select(p,c);assert(r.policy.mode==DVBRIDGE_MODE_HDR10_EXPERT && r.reason==OutputReason::None);
 p.output=OutputMode::Standard;p.mode=DVBRIDGE_MODE_MASTER_REFERENCE;
 r=select(p,c);assert(r.route==OutputRoute::NativeDV && r.policy.mode==DVBRIDGE_MODE_MASTER_REFERENCE);
 c.stereoSource=true;assert(select(p,c).route==OutputRoute::Vanilla);
}
'''.replace('BODY',implementation)
        repo=Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);code=root/'check.cpp';binary=root/'check'
            code.write_text(program)
            built=subprocess.run(['c++','-std=c++20','-fsanitize=address,undefined',
                '-I'+str(TREE/'xbmc'),'-I'+str(repo/'CB1/src'),str(code),'-o',str(binary)],
                capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':
    unittest.main()
