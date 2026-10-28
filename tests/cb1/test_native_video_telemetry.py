"""Exercise real adapter telemetry across DV -> software SDR and old callbacks."""
from pathlib import Path
import subprocess
import tempfile
import unittest
import os
from test_native_video_source import TREE,body

class TelemetryLifecycleTests(unittest.TestCase):
    def test_old_dv_summary_cannot_be_retagged_as_software_sdr(self):
        codec=(TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodec.h').read_text()
        self.assertTrue('SetVideoProcessingGeneration' in codec,'decoder epoch binding is missing')
        failure_tree=Path(__file__).parent/'before' if os.environ.get('TEST_OLD_FAILURE_PATHS') else TREE
        render=(failure_tree/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        present=body(render,'bool CDVBridgeGLES::Presented(bool success, const Submission& submission)')
        failed=body(present,'if (!committed)')
        win=(failure_tree/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        if os.environ.get('TEST_OLD_RESTORE_PATH'):
            win=(Path(__file__).parent/'before/xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        restore=body(win,'if (m_dvRollbackFailed || !RecoverDVActivation())')
        deferred=''
        if 'const auto deferred =' in win:
            start=win.index('const auto deferred =')
            deferred=win[start:win.index('{',start)]+body(win,'const auto deferred =')+';'
        methods=(TREE/'xbmc/cores/DataCacheCore.cpp').read_text()
        implementations='\n'.join(signature+body(methods,signature) for signature in (
            'uint64_t CDataCacheCore::ResetVideoProcessingInfo()',
            'uint64_t CDataCacheCore::GetVideoProcessingGeneration()',
            'bool CDataCacheCore::SetVideoProcessingInfo(uint64_t generation, const VideoProcessingInfo& info)',
            'VideoProcessingInfo CDataCacheCore::GetVideoProcessingInfo()'))
        cache_header=r'''
#pragma once
#include "cores/VideoProcessingInfo.h"
#include <mutex>
#include <memory>
class CDataCacheCore {
public:
 uint64_t ResetVideoProcessingInfo(); uint64_t GetVideoProcessingGeneration();
 bool SetVideoProcessingInfo(uint64_t generation,const VideoProcessingInfo& info);
 VideoProcessingInfo GetVideoProcessingInfo();
 std::mutex m_videoPlayerSection; VideoProcessingInfo m_videoProcessingInfo;
 std::shared_ptr<void> m_videoSourceSideData;
 uint64_t m_videoProcessingGeneration{}; bool m_hasAVInfoChanges{};
};
'''
        broker=r'''
#pragma once
#include "cores/DataCacheCore.h"
class CServiceBroker {public: static CDataCacheCore& GetDataCacheCore() {static CDataCacheCore cache; return cache;}};
'''
        program=r'''
#include "cores/VideoPlayer/DVDCodecs/Video/DVStreamTelemetry.h"
#include <cassert>
#include <memory>
IMPLEMENTATIONS
struct Submission {DVBRIDGE::SourceBinding identity; uint64_t informationGeneration;};
DVBRIDGE::SourceBinding m_failedIdentity;
void Failure(const char*) {}
void Cancel() {}
bool failedCommit(const Submission& submission) { FAILED return true; }
struct DRMBase {virtual ~DRMBase()=default;};
struct CDRMAtomic : DRMBase {unsigned DVActivationFailures() const {return 1;}};
std::shared_ptr<DRMBase> m_DRM=std::make_shared<CDRMAtomic>();
bool m_dvRollbackFailed=true,m_dvFatalConsumed=false;
DVBRIDGE::OutputReason m_dvFatalReason=DVBRIDGE::OutputReason::None;
std::mutex m_dvCapabilityMutex;
bool RecoverDVActivation() {return false;}
struct VideoPicture {DVBRIDGE::SourceInfo doviSourceInfo;};
namespace DVBRIDGE {void DiagnosticStage(const char*){}}
DEFERRED
bool failedRestore(const VideoPicture& picture) { RESTORE return true; }
int main() {
 auto& cache=CServiceBroker::GetDataCacheCore();
 const auto old=cache.ResetVideoProcessingInfo();
 DVBRIDGE::SourceInfo dv; dv.profile=7; dv.bits=10; dv.format=AV_PIX_FMT_YUV420P10LE;
 dv.informationGeneration=old; dv.bl=dv.el=dv.rpu=true;
 DVBRIDGE::StreamSnapshot::Output output; output.flags=CDVPlaybackInfo::HDMI;
 output.stream=3; output.picture=8; output.revision=4;
 CDVMetadataBuffer metadata;
 DVBRIDGE::StreamTelemetry::NativePresented(dv,metadata,output);
 DVBRIDGE::StreamTelemetry::PublishNativeInfo(old);
 assert(cache.GetVideoProcessingInfo().profile==7);
 const auto current=cache.ResetVideoProcessingInfo();
 DVBRIDGE::SourceInfo sdr; sdr.bits=8; sdr.format=AV_PIX_FMT_YUV420P;
 sdr.informationGeneration=current;
 DVBRIDGE::StreamTelemetry::SourceBits(8,AV_PIX_FMT_YUV420P,sdr);
 auto info=DVBRIDGE::NativeProcessingInfo(DVBRIDGE::StreamTelemetry::Read());
 info.output={}; info.outputType.reset();
 assert(info.profile==0 && !info.metadata && info.informationGeneration==current);
 assert(cache.SetVideoProcessingInfo(info.informationGeneration,info));
 DVBRIDGE::StreamTelemetry::NativePresented(dv,metadata,output);
 info=DVBRIDGE::NativeProcessingInfo(DVBRIDGE::StreamTelemetry::Read());
 info.output={}; info.outputType.reset();
 assert(info.informationGeneration==old);
 assert(!cache.SetVideoProcessingInfo(info.informationGeneration,info));
 assert(cache.GetVideoProcessingInfo().profile==0 && cache.GetVideoProcessingInfo().sourceBits==8);
 DVBRIDGE::StreamTelemetry::SourceBits(8,AV_PIX_FMT_YUV420P,sdr);
 info=DVBRIDGE::NativeProcessingInfo(DVBRIDGE::StreamTelemetry::Read());
 assert(info.profile==0 && info.informationGeneration==current);
 dv.informationGeneration=current;
 const DVBRIDGE::SourceBinding id{output.stream,output.picture,output.revision};
 DVBRIDGE::StreamTelemetry::NativeSelection(id,{},1,1,DVBRIDGE::OutputReason::None);
 DVBRIDGE::StreamTelemetry::NativePresented(dv,metadata,output);
 DVBRIDGE::StreamTelemetry::PublishNativeInfo(current);
 assert(!failedCommit({id,current}));
 assert(cache.GetVideoProcessingInfo().transaction.stage=="Failed commit");
 assert(cache.GetVideoProcessingInfo().output.flags==CDVPlaybackInfo::HDMI);
 assert(!failedRestore({dv}));
 assert(cache.GetVideoProcessingInfo().transaction.reason==VideoProcessingReason::RestoreFailed);
 assert(cache.GetVideoProcessingInfo().output.flags==CDVPlaybackInfo::HDMI);
 // Admitted Basic is usable for rendering while still explaining HDR10+ compatibility.
 output.flags=CDVPlaybackInfo::HDR10;output.effective=2;output.requested=6;
 DVBRIDGE::StreamTelemetry::NativeSelection(id,{},6,2,DVBRIDGE::OutputReason::NoHDR10PlusTransport);
 DVBRIDGE::StreamTelemetry::NativePresented(dv,metadata,output);
 auto compatibility=DVBRIDGE::StreamTelemetry::Read();
 assert(compatibility.output.fallback);
 assert(compatibility.output.reason==DVBRIDGE::OutputReason::NoHDR10PlusTransport);
 // An unrelated presentation cannot inherit an old transaction's explanation.
 ++output.picture;DVBRIDGE::StreamTelemetry::NativePresented(dv,metadata,output);
 compatibility=DVBRIDGE::StreamTelemetry::Read();
 assert(!compatibility.output.fallback && compatibility.output.reason==DVBRIDGE::OutputReason::None);
}
'''.replace('IMPLEMENTATIONS',implementations).replace('FAILED',failed).replace('RESTORE',restore).replace('DEFERRED',deferred)
        if not os.environ.get('FFMPEG_TEST_PREFIX'):
            self.skipTest('Set FFMPEG_TEST_PREFIX to the sanitizer-built FFmpeg prefix')
        prefix=Path(os.environ['FFMPEG_TEST_PREFIX'])
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); (root/'cores').mkdir()
            (root/'cores/DataCacheCore.h').write_text(cache_header)
            (root/'ServiceBroker.h').write_text(broker)
            (root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20','-fsanitize=address,undefined',
                '-I'+str(root),'-I'+str(TREE/'xbmc'),'-I'+str(prefix/'include'),str(root/'test.cpp'),
                '-L'+str(prefix/'lib'),'-lavutil','-lm','-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr[-3000:])
            run=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

if __name__=='__main__': unittest.main()
