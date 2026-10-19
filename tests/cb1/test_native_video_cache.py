"""Run shipped native cache methods with only platform locks/service isolated."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import body, TREE

class CacheTests(unittest.TestCase):
    def test_reset_rejects_delayed_and_regressive_publication(self):
        header=TREE/'xbmc/cores/VideoProcessingInfo.h'
        self.assertTrue(header.exists(), 'native cache contract is missing')
        text=(TREE/'xbmc/cores/DataCacheCore.cpp').read_text()
        methods='\n'.join(signature+body(text, signature) for signature in (
            'uint64_t CDataCacheCore::ResetVideoProcessingInfo()',
            'uint64_t CDataCacheCore::GetVideoProcessingGeneration()',
            'bool CDataCacheCore::SetVideoProcessingInfo(uint64_t generation, const VideoProcessingInfo& info)',
            'VideoProcessingInfo CDataCacheCore::GetVideoProcessingInfo()'))
        program=r'''
#include "VideoProcessingInfo.h"
#include <cassert>
#include <mutex>
#include <memory>
struct CDataCacheCore {
 std::mutex m_videoPlayerSection; VideoProcessingInfo m_videoProcessingInfo;
 std::shared_ptr<void> m_videoSourceSideData;
 uint64_t m_videoProcessingGeneration{}; bool m_hasAVInfoChanges{};
 uint64_t ResetVideoProcessingInfo(); uint64_t GetVideoProcessingGeneration();
 bool SetVideoProcessingInfo(uint64_t generation, const VideoProcessingInfo& info);
 VideoProcessingInfo GetVideoProcessingInfo();
};
METHODS
int main() {
 CDataCacheCore cache;
 assert(!cache.GetVideoProcessingInfo().outputType.has_value());
 const auto old=cache.ResetVideoProcessingInfo();
 VideoProcessingInfo first; first.informationGeneration=old; first.outputType=VideoOutputType::HDR10;
 first.output.stream=7; first.output.picture=8; first.output.revision=3;
 first.profile=7; first.metadata=true; first.blocks[1]=true;
 assert(cache.SetVideoProcessingInfo(old,first));
 auto result=cache.GetVideoProcessingInfo();
 assert(result.profile==7 && result.outputType==VideoOutputType::HDR10 && result.blocks[1]);
 auto stale=first; stale.output.revision=2; stale.output.picture=7;
 assert(!cache.SetVideoProcessingInfo(old,stale));
 assert(cache.GetVideoProcessingInfo().output.picture==8);
 auto next=first; next.output.revision=4; next.output.picture=9;
 assert(cache.SetVideoProcessingInfo(old,next));
 const auto current=cache.ResetVideoProcessingInfo(); assert(current!=old);
 assert(!cache.GetVideoProcessingInfo().outputType.has_value());
 assert(!cache.SetVideoProcessingInfo(old,first));
 VideoProcessingInfo sdr; sdr.informationGeneration=current; sdr.outputType=VideoOutputType::SDR;
 assert(cache.SetVideoProcessingInfo(current,sdr));
 assert(cache.GetVideoProcessingInfo().profile==0 && !cache.GetVideoProcessingInfo().metadata);
}
'''.replace('METHODS',methods)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); (root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20','-I'+str(header.parent),str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

if __name__=='__main__': unittest.main()
