"""Composited native video also publishes source information; idle GUI does not."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE,body

class OrdinaryTests(unittest.TestCase):
    def test_composited_native_video_has_source_bits(self):
        code=(TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        snippet=code.split('DVBRIDGE::PlaybackNotification::OrdinaryOutputAccepted(drm->LastPageAccepted());',1)[1].split('\n    }\n#endif',1)[0]
        methods=(TREE/'xbmc/cores/DataCacheCore.cpp').read_text()
        cache='\n'.join(signature+body(methods, signature) for signature in (
            'uint64_t CDataCacheCore::ResetVideoProcessingInfo()',
            'uint64_t CDataCacheCore::GetVideoProcessingGeneration()',
            'bool CDataCacheCore::SetVideoProcessingInfo(uint64_t generation, const VideoProcessingInfo& info)',
            'VideoProcessingInfo CDataCacheCore::GetVideoProcessingInfo()'))
        program=r'''
#include "VideoProcessingInfo.h"
#include <cassert>
#include <mutex>
#include <memory>
#include <chrono>
struct CDataCacheCore {
 std::mutex m_videoPlayerSection; VideoProcessingInfo m_videoProcessingInfo;
 std::shared_ptr<void> m_videoSourceSideData;
 uint64_t m_videoProcessingGeneration{}; bool m_hasAVInfoChanges{};
 uint64_t ResetVideoProcessingInfo(); uint64_t GetVideoProcessingGeneration();
 bool SetVideoProcessingInfo(uint64_t generation,const VideoProcessingInfo& info);
 VideoProcessingInfo GetVideoProcessingInfo();
};
CACHE
struct CApplicationPlayer { bool IsPlayingVideo() const {return playing;} bool playing=true; };
CDataCacheCore cache; CApplicationPlayer player;
struct Components { template<class T> std::shared_ptr<T> GetComponent() {return std::shared_ptr<T>(&player,[](T*){});} };
struct CServiceBroker { static CDataCacheCore& GetDataCacheCore() {return cache;}
 static Components GetAppComponents() {return {};} };
struct DRM {bool accepted=true,hdr10plus=false; bool LastPageAccepted() const {return accepted;}
 bool HDR10PlusActive() const {return hdr10plus;}};
namespace DVBRIDGE {
 uint64_t decodedGeneration{};
 struct StreamTelemetry {static VideoProcessingInfo Read() {VideoProcessingInfo info; info.informationGeneration=decodedGeneration; info.sourceBits=8; return info;}};
 VideoProcessingInfo NativeProcessingInfo(VideoProcessingInfo info) {return info;}
}
void present(DRM* drm,bool videoLayer) { SNIPPET }
int main() {
 DRM drm; DVBRIDGE::decodedGeneration=cache.ResetVideoProcessingInfo();
 present(&drm,false); assert(cache.GetVideoProcessingInfo().sourceBits==8);
 assert(!cache.GetVideoProcessingInfo().outputType);
 drm.hdr10plus=true; present(&drm,false);
 assert(cache.GetVideoProcessingInfo().outputType==VideoOutputType::HDR10Plus);
 drm.hdr10plus=false; present(&drm,false);
 assert(!cache.GetVideoProcessingInfo().outputType);
 cache.ResetVideoProcessingInfo(); player.playing=false;
 present(&drm,false); assert(cache.GetVideoProcessingInfo().sourceBits==0);
 player.playing=true; drm.accepted=false;
 present(&drm,true); assert(cache.GetVideoProcessingInfo().sourceBits==0);
}
'''.replace('CACHE',cache).replace('SNIPPET',snippet)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); (root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20','-I'+str(TREE/'xbmc/cores'),str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

if __name__=='__main__': unittest.main()
