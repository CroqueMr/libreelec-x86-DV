"""Decoded HDR10+ augments only the native current stream, within its epoch."""
import os
from pathlib import Path
import resource
import subprocess
import tempfile
import unittest
from test_native_video_source import body


@unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'), 'Set patched Kodi tree')
class NativeHDR10PlusClassification(unittest.TestCase):
    def test_accepted_metadata_promotes_only_current_hdr10_and_expires_on_reset(self):
        tree = Path(os.environ['KODI_NATIVE_SOURCE_TREE']) / 'xbmc'
        cache = (tree / 'cores/DataCacheCore.cpp').read_text()
        signature = 'bool CDataCacheCore::HasVideoHDR10PlusSource()'
        getter = body(cache, signature) if signature in cache else '{return false;}'
        reset = body(cache, 'uint64_t CDataCacheCore::ResetVideoProcessingInfo()')
        player = (tree / 'cores/VideoPlayer/VideoPlayer.cpp').read_text()
        method = body(player, 'void CVideoPlayer::GetVideoStreamInfo(')
        begin = method.index('  info.hdrType = s.hdrType;')
        end = method.index('  if (info.hdrType == StreamHdrType::HDR_TYPE_DOLBYVISION)', begin)
        expose = method[begin:end]
        code = r'''
#include <cassert>
#include <cstdint>
#include <memory>
#include <mutex>
enum class StreamHdrType {HDR_TYPE_NONE,HDR_TYPE_HDR10,HDR_TYPE_DOLBYVISION,HDR_TYPE_HLG,HDR_TYPE_HDR10PLUS};
struct VideoSourceSideData {
 uint64_t generation;bool plus;
 uint64_t Generation()const{return generation;}
 const void* HDR10Plus()const{return plus?this:nullptr;}
};
struct CDataCacheCore {
 std::mutex m_videoPlayerSection;uint64_t m_videoProcessingGeneration=7;
 bool m_hasAVInfoChanges=false;
 struct {uint64_t informationGeneration{};} m_videoProcessingInfo;
 std::shared_ptr<const VideoSourceSideData> m_videoSourceSideData;
 bool HasVideoHDR10PlusSource() GETTER
 uint64_t ResetVideoProcessingInfo() RESET
};
CDataCacheCore cache;
struct CServiceBroker {static CDataCacheCore& GetDataCacheCore(){return cache;}};
struct Player {
 struct{int m_videoIndex=0;}m_content;
 StreamHdrType expose(int streamId,StreamHdrType input){
  struct {StreamHdrType hdrType;}s{input},info{};
  EXPOSE
  return info.hdrType;
 }
};
int main(){
 using H=StreamHdrType;Player p;
 cache.m_videoSourceSideData=std::make_shared<VideoSourceSideData>(7,true);
 assert(p.expose(0,H::HDR_TYPE_HDR10)==H::HDR_TYPE_HDR10PLUS);
 assert(cache.HasVideoHDR10PlusSource());
 assert(p.expose(1,H::HDR_TYPE_HDR10)==H::HDR_TYPE_HDR10);
 for(auto type:{H::HDR_TYPE_NONE,H::HDR_TYPE_HLG,H::HDR_TYPE_DOLBYVISION})
  assert(p.expose(0,type)==type);
 cache.m_videoSourceSideData=std::make_shared<VideoSourceSideData>(6,true);
 assert(!cache.HasVideoHDR10PlusSource());assert(p.expose(0,H::HDR_TYPE_HDR10)==H::HDR_TYPE_HDR10);
 cache.m_videoSourceSideData=std::make_shared<VideoSourceSideData>(7,false);
 assert(!cache.HasVideoHDR10PlusSource());
 cache.m_videoSourceSideData=std::make_shared<VideoSourceSideData>(7,true);
 cache.ResetVideoProcessingInfo();assert(!cache.HasVideoHDR10PlusSource());
 assert(p.expose(0,H::HDR_TYPE_HDR10)==H::HDR_TYPE_HDR10);
}
'''.replace('GETTER', getter).replace('RESET', reset).replace('EXPOSE', expose)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / 'test.cpp').write_text(code)
            built = subprocess.run(['c++', '-std=c++20', str(path / 'test.cpp'), '-o', str(path / 'test')],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            ran = subprocess.run([str(path / 'test')], capture_output=True, text=True,
                                 preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)))
            self.assertEqual(ran.returncode, 0, ran.stderr)


if __name__ == '__main__':
    unittest.main()
