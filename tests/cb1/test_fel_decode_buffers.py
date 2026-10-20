"""Run native VAAPI allocation and pool consumers with delayed exact FEL pairing.

Removing the FEL-only reserve must strand BL eight before its EL can arrive;
native playback and the existing AI allocation must keep their original budgets.
Only VA/FFmpeg allocation and refcount APIs are replaced: pool decisions run as
shipped, without a display, decoder device, or playback settings.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_native_video_source import TREE, body


class FELDecodeBufferTests(unittest.TestCase):
    def test_delayed_el_does_not_starve_native_render_pool(self):
        base = TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video'
        source = (base/'VAAPI.cpp').read_text()
        allocation = source.split('  // add an extra surface for safety,', 1)[1]
        allocation = allocation[allocation.index('  m_vaapiConfig.maxReferences += 6;'):]
        allocation = allocation.split('  if (!ConfigVAAPI())', 1)[0]
        budget = body((base/'HDR10AIBuffers.h').read_text(), 'struct HDR10AIBuffers')
        limit = re.search(r'static constexpr unsigned DVEnhancementPendingPictures\s*=\s*\d+;',
            (base/'DVDVideoCodecFFmpeg.h').read_text()).group()
        methods = '\n'.join(signature+body(source, signature) for signature in (
            'CVideoBuffer* CVaapiBufferPool::Get()',
            'bool CVaapiBufferPool::HasFree()',
            'void CVaapiBufferPool::Init(unsigned count)',
            'void CVaapiBufferPool::QueueReturnPicture(CVaapiRenderPicture *pic)',
            'CVaapiRenderPicture* CVaapiBufferPool::ProcessSyncPicture()'))
        work = 'bool COutput::HasWork()'+body(source, 'bool COutput::HasWork()')
        program = r'''
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <deque>
#include <vector>
#define HAVE_DVBRIDGE 1
AI_DEFINE
#define NUM_RENDER_PICS 7
namespace DVBRIDGE {
 enum class HDR10SourceMode {Native,ReferenceDV,EnhancedDV};
 struct HDR10AIActivation {static unsigned BufferCount(double) {return 24;}};
 struct HDR10AIBuffers BUDGET;
}
struct ICallbackHWAccel {
 virtual ~ICallbackHWAccel()=default;
 unsigned ai=6;
 unsigned GetHDR10AIBufferCount() const {return ai;}
};
struct CDVDVideoCodecFFmpeg : ICallbackHWAccel {
 LIMIT
 bool fel=false;
 bool NeedsDVEnhancement() const {return fel;}
};
struct AVCodecContext {void* opaque;};
struct Config {unsigned maxReferences=16,renderPictures=7;};
Config configure(CDVDVideoCodecFFmpeg& decoder) {
 AVCodecContext context{static_cast<ICallbackHWAccel*>(&decoder)};
 auto* avctx=&context;
 Config m_vaapiConfig;
 unsigned m_hdr10AIBuffers=6;
 ALLOCATION
 return m_vaapiConfig;
}
constexpr int LOGWARNING=0,LOGERROR=1,LOGDEBUG=2,LOGVIDEO=0;
struct CLog {template<class... T> static void Log(T...) {}};
struct CVideoBuffer {virtual ~CVideoBuffer()=default;void Acquire(void*) {}};
struct CVaapiRenderPicture : CVideoBuffer {
 explicit CVaapiRenderPicture(unsigned) {}
 void* avFrame=nullptr;
 unsigned renderBufferCount=6;
 bool valid=false;
};
void* av_frame_alloc() {static int allocation;return &allocation;}
struct Decoder {void Acquire() {}};
struct CVaapiBufferPool {
 Decoder m_vaapi;
 std::vector<CVaapiRenderPicture*> allRenderPics;
 std::deque<int> usedRenderPics,freeRenderPics,syncRenderPics;
 std::deque<int> processedPics,decodedPics;
 int procPicId=0;
 void* GetPtr() {return this;}
 CVideoBuffer* Get();bool HasFree();void Init(unsigned count);
 void QueueReturnPicture(CVaapiRenderPicture* pic);
 CVaapiRenderPicture* ProcessSyncPicture();
 ~CVaapiBufferPool() {for(auto* p:allRenderPics) delete p;}
};
METHODS
struct Postproc {bool WantsPic() {return true;}};
struct COutput {
 CVaapiBufferPool* m_bufferPool;Postproc* m_pp=nullptr;
 bool HasWork();
};
WORK
int main() {
 CDVDVideoCodecFFmpeg decoder;
 auto ordinary=configure(decoder);
 assert(ordinary.maxReferences==22 && ordinary.renderPictures==7);
 decoder.ai=24;
 auto ai=configure(decoder);
#ifdef CB1_HAS_HDR10_AI
 assert(ai.maxReferences==40 && ai.renderPictures==25);
#else
 assert(ai.maxReferences==22 && ai.renderPictures==7);
#endif
 decoder.ai=6;decoder.fel=true;
 auto fel=configure(decoder);
 CVaapiBufferPool pool;pool.Init(fel.renderPictures);
 pool.processedPics={1,2,3};
 COutput output{&pool};
 std::vector<CVaapiRenderPicture*> held;
 // No EL exists for the first BL until input eight. Each BL owns the actual
 // native output-pool slot while pairing waits, not a fictitious decode slot.
 for(unsigned i=0;i<8;++i) {
   auto* pic=dynamic_cast<CVaapiRenderPicture*>(pool.Get());
   if(!pic) {fprintf(stderr,"FEL starved at BL %u before delayed EL arrived\n",i+1);return 1;}
   pic->valid=true;held.push_back(pic);
 }
 assert(output.HasWork()); // proc=3 can progress; EL input is not blocked.
 // Release exactly the paired BL and verify the real native return queue
 // makes its slot available. No EL substitution or increased timeout.
 pool.QueueReturnPicture(held.front());
 assert(pool.ProcessSyncPicture()==held.front());
 held.erase(held.begin());
 // Worst bounded lookahead: sixteen unmatched BL plus seven unchanged native
 // downstream slots. Three already processed frames need an output slot to
 // progress, and must not block ingress before the pairing bound is reached.
 while(held.size()<22) {
   auto* pic=dynamic_cast<CVaapiRenderPicture*>(pool.Get());
   if(!pic) {fprintf(stderr,"FEL reserve exhausted at %zu held BL/render slots\n",held.size());return 2;}
   pic->valid=true;held.push_back(pic);
 }
 assert(output.HasWork()); // 16 pending + 6 downstream, one output slot left.
 auto* last=dynamic_cast<CVaapiRenderPicture*>(pool.Get());
 assert(last);last->valid=true;held.push_back(last);
 assert(!pool.HasFree());
 assert(!output.HasWork()); // Only normal downstream backpressure remains.
 pool.QueueReturnPicture(held.front());
 assert(pool.ProcessSyncPicture()==held.front() && pool.HasFree() && output.HasWork());
 assert(fel.maxReferences==38); // 16 HEVC + 6 native safety + 16 retained BL.
 puts("PASS: delayed EL at BL8; 16 pending BL + 7 native slots; native/AI unchanged");
}
'''.replace('BUDGET', budget).replace('ALLOCATION', allocation).replace('METHODS', methods)
        program = program.replace('LIMIT', limit).replace('WORK', work)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for ai_enabled in (False, True):
                with self.subTest(ai_enabled=ai_enabled):
                    (root/'test.cpp').write_text(program.replace('AI_DEFINE',
                        '#define CB1_HAS_HDR10_AI 1' if ai_enabled else ''))
                    built = subprocess.run(['c++', '-std=c++20', '-Wall', '-Wextra',
                        str(root/'test.cpp'), '-o', str(root/'test')], capture_output=True, text=True)
                    self.assertEqual(built.returncode, 0, built.stderr)
                    ran = subprocess.run([str(root/'test')], capture_output=True, text=True)
                    self.assertEqual(ran.returncode, 0, ran.stderr)


if __name__ == '__main__':
    unittest.main()
