"""A discarded RGB preparation must stop owning later prediction wait time."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class AbandonedPreparationTests(unittest.TestCase):
    def test_discarded_preparation_preserves_only_time_actually_waited(self):
        source = (TREE/'xbmc/cores/VideoPlayer/VideoRenderers/HDR10AISource.cpp').read_text()
        discard = body(source, 'void HDR10AISource::DiscardBefore')
        program = r'''
#include "cores/VideoPlayer/DVDCodecs/Video/HDR10AIActivation.h"
#include <cassert>
#include <optional>
using Activation=DVBRIDGE::HDR10AIActivation;
using Decision=Activation::Decision;
struct Binding {uint64_t stream,picture,revision;};
struct Result {cb1_ai_identity id;};
struct Source {
 Activation m_activation;
 std::optional<Result> m_prepared,m_committed;
 Binding m_preparedBinding{};
 bool m_fallback{};
 bool Matches(Binding b) const {return b.stream==7 && b.revision==8;}
 bool AwaitingPresentation() const {return m_prepared && (!m_committed || m_prepared->id.picture!=m_committed->id.picture);}
 void DiscardBefore(Binding binding,uint64_t now) DISCARD
};
int main() {
 Source s;
 cb1_ai_identity first{7,1,9}, next{7,2,9}, future{7,3,9};
 s.m_activation.Begin(7,9,0);
 assert(s.m_activation.Observe(CB1_AI_READY,first,400)==Decision::Prepare);
 assert(s.m_activation.Presented(first,true));s.m_committed=Result{first};
 assert(s.m_activation.Observe(CB1_AI_READY,next,800)==Decision::Prepare);
 s.m_prepared=Result{next};s.m_preparedBinding={7,2,8};
 s.m_activation.SetPresentationDeadline(1000);
 assert(s.m_activation.Observe(CB1_AI_PENDING,next,900)==Decision::Wait);
 s.DiscardBefore({7,3,8},950);
 assert(!s.m_prepared && !s.m_fallback);
 assert(!s.m_activation.Presented(next,true));
 assert(s.m_committed->id.picture==1);
 s.m_activation.SetPresentationDeadline(2000);
 assert(s.m_activation.Observe(CB1_AI_PENDING,future,1700,false)==Decision::Wait);
 assert(s.m_activation.Observe(CB1_AI_READY,future,1800,false)==Decision::Prepare);
 assert(s.m_activation.Presented(future,true));
 // Cancellation must not refund real waiting or reset the cumulative budget.
 for(unsigned i=4;i<=9;++i) {
   cb1_ai_identity id{7,i,9};const uint64_t due=2000+i*1000;
   assert(s.m_activation.Observe(CB1_AI_READY,id,due-200)==Decision::Prepare);
   s.m_prepared=Result{id};s.m_preparedBinding={7,i,8};
   s.m_activation.SetPresentationDeadline(due);
   assert(s.m_activation.Observe(CB1_AI_PENDING,id,due-100)==Decision::Wait);
   s.DiscardBefore({7,i+1,8},due+100);
   assert(s.m_fallback==(i==9));
 }
 assert(s.m_activation.TakeFallbackEvent());
 assert(!s.m_activation.TakeFallbackEvent());
 assert(s.m_activation.Observe(CB1_AI_READY,{7,10,9},20000)==Decision::Native);
 Activation a;cb1_ai_identity id{7,1,9};
 a.Begin(7,9,0);assert(a.Observe(CB1_AI_READY,id,100)==Decision::Prepare);
 assert(a.Presented(id,true));++id.picture;
 assert(a.Observe(CB1_AI_READY,id,200)==Decision::Prepare);
 a.SetPresentationDeadline(1000);
 assert(a.Observe(CB1_AI_PENDING,id,900)==Decision::Wait);
 assert(a.CancelPrepared({8,2,9},1500)==Decision::Ignore);
 assert(a.CancelPrepared({7,2,10},1500)==Decision::Ignore);
 assert(a.CancelPrepared({7,3,9},1500)==Decision::Ignore);
 assert(a.Observe(CB1_AI_READY,id,950)==Decision::Prepare);
 assert(a.Presented(id,true));++id.picture;
 assert(a.Observe(CB1_AI_READY,id,960)==Decision::Prepare);
 assert(a.CancelPrepared(id,5000)==Decision::Wait); // No open wait to charge.
 assert(!a.Presented(id,true));++id.picture;
 assert(a.Observe(CB1_AI_READY,id,5100)==Decision::Prepare);
 assert(a.Presented(id,true));++id.picture;a.SetPresentationDeadline(6000);
 assert(a.Observe(CB1_AI_PENDING,id,6000)==Decision::Wait);
 assert(a.Observe(CB1_AI_PENDING,id,6899)==Decision::Wait);
 assert(a.Observe(CB1_AI_PENDING,id,6900)==Decision::Native);
 // Cancelling during pause charges only the overdue time before the pause.
 a.Begin(7,9,0);id={7,1,9};assert(a.Observe(CB1_AI_READY,id,100)==Decision::Prepare);
 assert(a.Presented(id,true));++id.picture;
 assert(a.Observe(CB1_AI_READY,id,200)==Decision::Prepare);
 a.SetPresentationDeadline(1000);assert(a.Observe(CB1_AI_PENDING,id,900)==Decision::Wait);
 a.SetPaused(true,1100);assert(a.CancelPrepared(id,10000)==Decision::Wait);
 a.SetPaused(false,10001);++id.picture;
 assert(a.Observe(CB1_AI_READY,id,10100)==Decision::Prepare);assert(a.Presented(id,true));
 ++id.picture;a.SetPresentationDeadline(11000);
 assert(a.Observe(CB1_AI_PENDING,id,11000)==Decision::Wait);
 assert(a.Observe(CB1_AI_PENDING,id,11799)==Decision::Wait);
 assert(a.Observe(CB1_AI_PENDING,id,11800)==Decision::Native);
}
'''.replace('DISCARD', discard)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'test.cpp').write_text(program)
            core = Path(__file__).resolve().parents[2]/'CB1/src'
            build = subprocess.run(['c++', '-std=c++20', '-fsanitize=address,undefined',
                '-I'+str(TREE/'xbmc'), '-I'+str(core), str(root/'test.cpp'), '-o', str(root/'test')],
                text=True, capture_output=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(root/'test')], text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)
