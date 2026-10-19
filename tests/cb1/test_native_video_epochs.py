"""Run the native epoch hooks at the actual flush/reset/open boundaries."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE,body

class EpochBoundaryTests(unittest.TestCase):
    def test_decoder_internal_flush_and_reopen_invalidate_native_source(self):
        video=(TREE/'xbmc/cores/VideoPlayer/VideoPlayerVideo.cpp').read_text()
        for status,operation in (('VC_FLUSHED','Reset'),('VC_REOPEN','Reopen')):
            section=body(video,'if (decoderState == CDVDVideoCodec::'+status+')')
            boundary=section.split('m_pVideoCodec->'+operation+'();',1)[0]
            self.assertTrue('SetVideoProcessingGeneration(' in boundary,
                            status+' must invalidate source before replaying decoder input')

    def test_decoder_tags_are_bound_before_output_and_invalidated_on_flush(self):
        video=(TREE/'xbmc/cores/VideoPlayer/VideoPlayerVideo.cpp').read_text()
        snippets=[]
        for marker in ('else if (pMsg->IsType(CDVDMsg::GENERAL_RESET))',
                       'else if (pMsg->IsType(CDVDMsg::GENERAL_FLUSH))'):
            section=video.split(marker,1)[1]
            snippet=section.split('const auto generation=',1)[1].split(';',1)[0]
            snippet='const auto generation='+snippet+';\n'+section.split('if (m_pVideoCodec)',1)[1].split(';',1)[0]+';'
            snippet=snippet.replace(' m_pVideoCodec->',' if (m_pVideoCodec) m_pVideoCodec->')
            snippets.append(snippet)
        open_hook=video.split('m_pVideoCodec = std::move(codec);',1)[1].split('m_hints = hint;',1)[0]
        setter=body((TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodec.h').read_text(),'void SetVideoProcessingGeneration')
        decoder=(TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodecFFmpeg.cpp').read_text()
        assignment=next(line for line in decoder.splitlines() if 'sourceInfo.informationGeneration =' in line)
        program=r'''
#include <cassert>
#include <cstdint>
struct Cache {uint64_t gen{}; uint64_t ResetVideoProcessingInfo() {return ++gen;} uint64_t GetVideoProcessingGeneration() {return gen;}} cache;
struct CServiceBroker {static Cache& GetDataCacheCore() {return cache;}};
struct Decoder {
 uint64_t m_videoProcessingGeneration{};
 uint64_t m_videoSourceSerial{};
 void SetVideoProcessingGeneration(uint64_t generation) SETTER
 uint64_t PictureTag() {struct {uint64_t informationGeneration;} sourceInfo; ASSIGNMENT return sourceInfo.informationGeneration;}
} decoder;
Decoder* m_pVideoCodec=&decoder;
void open() { OPEN }
void flush() { FLUSH }
void reset() { RESET }
int main() {
 open(); const auto old=decoder.PictureTag(); assert(old==cache.gen && old>0);
 const auto preparedTag=old;
 flush(); assert(decoder.PictureTag()==cache.gen && decoder.PictureTag()!=preparedTag);
 const auto postSeek=decoder.PictureTag(); reset(); assert(decoder.PictureTag()!=postSeek);
 open(); assert(decoder.PictureTag()==cache.gen && decoder.PictureTag()>postSeek);
}
'''.replace('SETTER',setter).replace('ASSIGNMENT',assignment).replace('OPEN',open_hook).replace('FLUSH',snippets[1]).replace('RESET',snippets[0])
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); (root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr[-3000:])
            run=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

if __name__=='__main__': unittest.main()
