"""A seek must prime AI from the new queue, not the retained scanout image."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class AISeekSelectionTests(unittest.TestCase):
    def test_reset_does_not_prepend_old_selected_picture(self):
        source = (TREE/'xbmc/cores/VideoPlayer/VideoRenderers/RenderManager.cpp').read_text()
        selection = body(source, 'bool CRenderManager::PrepareHDR10AILookahead(').split('  uint64_t deadline =')[0]
        program = r'''
#define CB1_HAS_HDR10_AI 1
#define HAVE_DVBRIDGE 1
#include <cassert>
#include <deque>
#include <mutex>
using CCriticalSection=std::mutex;
constexpr double DVD_NOPTS_VALUE=-1e20;
enum {PRESENT_IDLE,PRESENT_READY,PRESENT_FRAME,PRESENT_FLIP};
struct Renderer {
 bool pending=true;
 bool HDR10AIQueueEligible(){return true;}
 bool HDR10AILookahead(){return true;}
 bool HDR10AIFramePending(){return pending;}
};
struct Clock {bool IsPaused(){return true;}};
struct CRenderManager {
 Renderer renderer; Renderer* m_pRenderer=&renderer; Clock m_dvdClock;
 bool m_aiQueuePreparationStale=false,m_aiQueueReady=true,m_aiGuiReady=false;
 bool m_showVideo=true,m_cb1PresentPending=false;
 double m_aiStartPts=DVD_NOPTS_VALUE;
 int m_presentstep=PRESENT_FRAME,m_presentsource=1;
 std::deque<int> m_queued{2,3},observed;
 void ReleaseDiscardedBuffers(bool){}
 bool PrepareHDR10AILookahead(std::unique_lock<CCriticalSection>& lock);
};
bool CRenderManager::PrepareHDR10AILookahead(std::unique_lock<CCriticalSection>& lock)
SELECTION
 observed=queue; return true;
}
int main() {
 std::mutex mutex;std::unique_lock lock(mutex);CRenderManager manager;
 for(int state : {PRESENT_FRAME,PRESENT_FLIP}) {
   manager.m_presentstep=state;
   assert(manager.PrepareHDR10AILookahead(lock));
   assert((manager.observed==std::deque<int>{2,3}));
 }
 manager.m_aiStartPts=1000;
 assert(manager.PrepareHDR10AILookahead(lock));
 assert((manager.observed==std::deque<int>{1,2,3}));
 manager.m_aiStartPts=DVD_NOPTS_VALUE;manager.m_queued.clear();
 assert(!manager.PrepareHDR10AILookahead(lock));
}
'''.replace('SELECTION',selection)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
