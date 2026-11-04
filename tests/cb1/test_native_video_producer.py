"""Adapter summary cannot claim generated metadata as original source metadata."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE

class ProducerTests(unittest.TestCase):
    def test_accepted_summary_separates_source_and_ai_output(self):
        helper=TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVProcessingInfo.h'
        self.assertTrue(helper.exists(), 'native accepted-summary producer is missing')
        snapshot=(TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVStreamTelemetry.h').read_text()
        snapshot=snapshot.split('struct StreamSnapshot',1)[1].split('class StreamTelemetry',1)[0]
        program=r'''
#define CB1_HAS_HDR10_AI
#include "VideoProcessingInfo.h"
#include "cb1_circuit.h"
#include <cassert>
#include <string>
#include <bitset>
enum AVPixelFormat { AV_PIX_FMT_NONE=-1 };
struct SourceBinding { uint64_t stream{}, picture{}, revision{}; bool Valid() const {return stream && picture && revision;} };
struct OutputCapabilities { bool isHDR10{},isDV{}; };
using OutputReason=VideoProcessingReason;
struct CDVPlaybackInfo { enum {HDMI=1,FEL=2,CM4=4,HDR10=8,HDR10PLUS=16}; };
namespace DVBRIDGE { using ::SourceBinding; using ::OutputCapabilities; using ::OutputReason; struct StreamSnapshot SNAPSHOT }
#include "DVProcessingInfo.h"
int main() {
 DVBRIDGE::StreamSnapshot::Output basic{1,8,1000,false};
 assert(basic.aiModel.empty());
 DVBRIDGE::StreamSnapshot s; s.profile=7; s.metadata=true; s.l1=true; s.blocks[1]=true; s.blocks[5]=true;
 s.output.flags=CDVPlaybackInfo::HDR10|CDVPlaybackInfo::FEL; s.output.effective=3;
 s.output.felUpscaling=1;
 s.pq={12,4095,3079}; s.output.creativeApplied=1<<2;
 auto info=DVBRIDGE::NativeProcessingInfo(s);
 assert(info.outputType==VideoOutputType::HDR10 && info.profile==7 && info.blocks[1]);
 assert(info.output.felUpscaling==1);
 assert(!info.transaction.hdr10AI);
 s.transaction.capabilities.isHDR10=true;
 assert(DVBRIDGE::NativeProcessingInfo(s).transaction.hdr10AI);
 s.transaction.capabilities.isDV=true;
 assert(!DVBRIDGE::NativeProcessingInfo(s).transaction.hdr10AI);
 assert(info.appliedBlocks[1] && info.transmittedBlocks.none());
 s.output.flags|=CDVPlaybackInfo::HDR10PLUS; s.output.effective=7;
 assert(DVBRIDGE::NativeProcessingInfo(s).outputType==VideoOutputType::HDR10Plus);
 s.profile=0; s.output.flags=CDVPlaybackInfo::HDMI; s.output.effective=1;
 s.output.hdr10AI=true; s.output.aiL1L3={1,2000,1000,2,3,4};
 s.output.aiModel="CB1-L1L3 0.1";s.output.aiBaseline={0,1900,900};
 info=DVBRIDGE::NativeProcessingInfo(s);
 assert(info.outputType==VideoOutputType::DolbyVision && !info.metadata && info.blocks.none());
 assert(info.appliedBlocks.none() && info.profile==0 && info.output.hdr10AI);
 assert(info.transmittedBlocks[1] && info.transmittedBlocks[5]);
 assert(info.output.aiL1L3[1]==2000 && !info.output.engine.empty());
 assert(info.output.aiModel=="CB1-L1L3 0.1" && info.output.aiBaseline[1]==1900);
 assert(info.output.circuit=="CB1-HDR10DVR.0.1.3" && info.output.engine=="CB1 0.5");
 s.output.hdr10PlusDV=true;s.output.guidedSourceFields=2;s.output.guidedEstimatedFields=5;
 info=DVBRIDGE::NativeProcessingInfo(s);
 assert(!info.metadata && info.output.circuit=="CB1-HDR10PDVR.0.2");
 assert(info.output.guidedSourceFields==2 && info.output.guidedEstimatedFields==5);
 s={}; info=DVBRIDGE::NativeProcessingInfo(s);
 assert(!info.outputType.has_value() && info.output.engine.empty());
 assert(info.output.aiModel.empty() && info.output.aiBaseline[1]==0);
 assert(info.output.felUpscaling==-1);
 s.profile=7;s.metadata=true;s.blocks[2]=true;s.blocks[8]=true;
 s.output.flags=CDVPlaybackInfo::HDMI;
 assert(DVBRIDGE::NativeProcessingInfo(s).transmittedBlocks[2]);
 s.output.l2TrimsDisabled=true;
 info=DVBRIDGE::NativeProcessingInfo(s);
 assert(info.blocks[2] && !info.transmittedBlocks[2] && info.transmittedBlocks[8]);
 s.output.l2TrimsDisabled=false;
 assert(DVBRIDGE::NativeProcessingInfo(s).transmittedBlocks[2]);
 s.output.flags=CDVPlaybackInfo::HDMI;s.output.effective=5;s.output.iptTransport=true;
 assert(DVBRIDGE::NativeProcessingInfo(s).output.iptTransport);
}
'''.replace('SNAPSHOT',snapshot)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); (root/'test.cpp').write_text(program)
            core=Path(__file__).resolve().parents[2]/'CB1/src'
            circuit=root/'circuit.o'
            compiled=subprocess.run(['cc','-std=c11','-I'+str(core),'-c',str(core/'cb1_circuit.c'),
                '-o',str(circuit)],capture_output=True,text=True)
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            build=subprocess.run(['c++','-std=c++20','-Werror=missing-field-initializers','-I'+str(TREE/'xbmc'),'-I'+str(TREE/'xbmc/cores'),
                '-I'+str(helper.parent),'-I'+str(core),str(root/'test.cpp'),str(circuit),'-o',str(root/'test')],
                capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

if __name__=='__main__': unittest.main()
