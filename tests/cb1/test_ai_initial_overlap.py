"""Initial analysis overlaps queue filling without presenting a partial horizon."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class InitialOverlapTests(unittest.TestCase):
    def test_buffered_reset_arms_budget_even_while_old_gpu_job_is_pending(self):
        code=body((TREE/'xbmc/cores/VideoPlayer/VideoRenderers/HDR10AISource.cpp').read_text(),
                  'cb1_ai_status HDR10AISource::Begin(')
        program=r'''
#include "cores/VideoPlayer/DVDCodecs/Video/HDR10AIActivation.h"
#include <algorithm>
#include <cassert>
#include <optional>
using pl_gpu=void*;
namespace DVBRIDGE {
struct SourceBinding {uint64_t stream=7,picture=1,revision=1;bool Valid(){return stream && revision;}};
enum class HDR10SourceMode {Native,ReferenceDV};
struct OutputPreferences {uint64_t revision=9;HDR10SourceMode hdr10Source=HDR10SourceMode::ReferenceDV;};
uint64_t NextRevisionAfter(uint64_t value){return value+1;}
}
void cb1_hdr10_ai_destroy(void**){assert(false);}
cb1_ai_status cb1_hdr10_ai_create(pl_gpu,const char*,void**){assert(false);return CB1_AI_INVALID;}
void cb1_hdr10_ai_reset(void*,uint64_t,uint64_t){assert(false);}
bool cb1_hdr10_ai_set_coalesced_bounds(void*,bool){assert(false);return false;}
struct HDR10AISource {
 using Decision=DVBRIDGE::HDR10AIActivation::Decision;
 bool m_resetPending=false,m_fallback=false,m_active=false,m_job=true,m_paused=false;
 pl_gpu m_gpu=nullptr;void* m_context=nullptr;uint64_t m_revision=0,m_lastSubmitted=0;
 DVBRIDGE::SourceBinding m_binding{},m_preparedBinding{};DVBRIDGE::OutputPreferences m_preferences;
 double m_origin=0;std::optional<int> m_prepared,m_committed;
 const char* m_diagnosticStage="none";cb1_ai_status m_diagnosticStatus=CB1_AI_READY;bool m_diagnosticFailure=false;
 DVBRIDGE::HDR10AIActivation m_activation;
 bool Current(DVBRIDGE::SourceBinding,const DVBRIDGE::OutputPreferences&){return m_resetPending;}
 cb1_ai_identity Identity(DVBRIDGE::SourceBinding b){return {b.stream,b.picture,m_revision};}
 cb1_ai_status Collect(){return CB1_AI_PENDING;}
 cb1_ai_status RecordStatus(const char*,cb1_ai_status status){return status;}
 cb1_ai_status Begin(pl_gpu,const char*,const DVBRIDGE::OutputPreferences&,DVBRIDGE::SourceBinding,double,uint64_t,bool);
};
cb1_ai_status HDR10AISource::Begin(pl_gpu gpu,const char* bundle,
 const DVBRIDGE::OutputPreferences& preferences,DVBRIDGE::SourceBinding binding,
 double pts,uint64_t now,bool buffered) FUNCTION
int main(){
 HDR10AISource s;DVBRIDGE::SourceBinding b;DVBRIDGE::OutputPreferences p;
 assert(s.Begin(&s,"bundle",p,b,0,0,false)==CB1_AI_PENDING);
 assert(s.Begin(&s,"bundle",p,b,0,100,true)==CB1_AI_PENDING);
 assert(s.Begin(&s,"bundle",p,b,0,1099,true)==CB1_AI_PENDING);
 assert(s.Begin(&s,"bundle",p,b,0,1100,true)==CB1_AI_INCOMPATIBLE);
 assert(s.m_fallback);
}
'''.replace('FUNCTION',code)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            core=Path(__file__).resolve().parents[2]/'CB1/src'
            built=subprocess.run(['c++','-std=c++20','-I'+str(TREE/'xbmc'),'-I'+str(core),
                                  str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(ran.returncode,0,ran.stderr)

    def test_input_buffering_does_not_extend_the_required_wait_budget(self):
        program = r'''
#include "cores/VideoPlayer/DVDCodecs/Video/HDR10AIActivation.h"
#include <cassert>
int main(){
 using Activation=DVBRIDGE::HDR10AIActivation;using Decision=Activation::Decision;
 Activation a;cb1_ai_identity id{7,1,9};a.Begin(7,9,0);a.WaitForInput();
 assert(a.Observe(CB1_AI_PENDING,id,10000,false)==Decision::Wait);
 assert(a.Observe(CB1_AI_READY,id,10000,false)==Decision::Wait);
 a.InputReady(10000);
 assert(a.Observe(CB1_AI_PENDING,id,10999)==Decision::Wait);
 a.InputReady(10999); // Repeated readiness must not reset the budget.
 assert(a.Observe(CB1_AI_PENDING,id,11000)==Decision::Native);
 a.Begin(7,9,0);a.WaitForInput();a.SetPaused(true,20);a.InputReady(10000);
 assert(a.Observe(CB1_AI_PENDING,id,10000)==Decision::Wait);
 a.SetPaused(false,10000);
 assert(a.Observe(CB1_AI_PENDING,id,10999)==Decision::Wait);
 assert(a.Observe(CB1_AI_PENDING,id,11000)==Decision::Native);
 a.Begin(7,9,0);a.WaitForInput();
 assert(a.Observe(CB1_AI_INCOMPATIBLE,id,5)==Decision::Native);
 a.Begin(7,9,0);a.WaitForInput();a.Stop();a.InputReady(5000);
 assert(a.Observe(CB1_AI_READY,id,5000)==Decision::Ignore);
 a.Begin(7,9,0);assert(a.Observe(CB1_AI_PENDING,id,1000)==Decision::Native);
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            core=Path(__file__).resolve().parents[2]/'CB1/src'
            built=subprocess.run(['c++','-std=c++20','-I'+str(TREE/'xbmc'),'-I'+str(core),
                                  str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(ran.returncode,0,ran.stderr)

    def test_partial_input_is_analysed_before_the_complete_horizon(self):
        code = body((TREE/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text(),
                    'HDR10AISource::Decision CDVBridgeGLES::Context::PrepareHDR10AIQueue(')
        program = r'''
#include <cassert>
#include <chrono>
#include <cstdint>
#include <optional>
#include <span>
#include <thread>
#include <vector>
enum cb1_ai_status {CB1_AI_READY,CB1_AI_PENDING,CB1_AI_INVALID,CB1_AI_INCOMPATIBLE};
struct cb1_ai_result{};
namespace DVBRIDGE {
enum class HDR10SourceMode {Native,ReferenceDV,EnhancedDV};
struct OutputPreferences {HDR10SourceMode hdr10Source=HDR10SourceMode::ReferenceDV;};
}
enum {DVBRIDGE_DV_FAILED=-1};
struct Binding {uint64_t picture;};
struct HDR10AISource {
 enum class Decision {Wait,Ignore,Native,Prepare};
 bool active=false,covered=false;unsigned analysed=0,armed=0;uint64_t last=0;
 bool Current(Binding,const DVBRIDGE::OutputPreferences&){return active;}
 bool ResetPending(){return false;}
 void SetPaused(bool,uint64_t){} void DiscardBefore(Binding,uint64_t){}
 void SetPresentationDeadline(uint64_t){} void InputReady(uint64_t){++armed;}
 bool AwaitingPresentation(){return false;} cb1_ai_status Collect(){return CB1_AI_READY;}
 uint64_t LastSubmitted(){return last;}
 cb1_ai_status Seal(double){covered=true;return CB1_AI_READY;} void End(){covered=true;}
 void RecordStatus(const char*,cb1_ai_status){}
 Decision Prediction(Binding,const DVBRIDGE::OutputPreferences&,uint64_t,cb1_ai_result*,bool){
  return covered?Decision::Prepare:Decision::Wait;
 }
};
struct CDVBridgeGLES {
 struct Layer {Binding binding;double pts;};
 struct Context {
  struct State {bool aiStopping=false,aiNextFailed=false,attached=false;
   struct NextHDR10AI {Layer layer;Binding binding;double pts;DVBRIDGE::OutputPreferences preferences;};
   std::optional<NextHDR10AI> aiNext;
  } state,*m_state=&state;
  HDR10AISource source;bool beganBuffered=true;
  void ClearNextHDR10AI(){state.aiNext.reset();}
  bool StopHDR10AI(){return true;} int Poll(){return 0;}
  HDR10AISource& HDR10AI(){return source;} bool FenceLastUse(){return true;}
  bool FenceHDR10AIUse(){return true;}
  cb1_ai_status BeginHDR10AI(const char*,const DVBRIDGE::OutputPreferences&,Binding,double,uint64_t,bool buffered=true){
   source.active=true;beganBuffered=buffered;return CB1_AI_READY;
  }
  cb1_ai_status AnalyseHDR10AI(const Layer& layer,double){++source.analysed;source.last=layer.binding.picture;return CB1_AI_READY;}
  HDR10AISource::Decision PrepareHDR10AIQueue(std::span<const Layer>,const DVBRIDGE::OutputPreferences&,
   const char*,uint64_t,bool,cb1_ai_result*,bool,uint64_t);
 };
};
HDR10AISource::Decision CDVBridgeGLES::Context::PrepareHDR10AIQueue(std::span<const Layer> queue,
 const DVBRIDGE::OutputPreferences& preferences,const char* bundle,uint64_t now,bool end,
 cb1_ai_result* result,bool paused,uint64_t presentationDeadline) FUNCTION
int main(){
 using Decision=HDR10AISource::Decision;DVBRIDGE::OutputPreferences preferences;cb1_ai_result result;
 CDVBridgeGLES::Context c;std::vector<CDVBridgeGLES::Layer> queue{{{1},0},{{2},.1}};
 assert(c.PrepareHDR10AIQueue(queue,preferences,"bundle",0,false,&result,false,0)==Decision::Wait);
 assert(c.source.analysed==2); // A partial queue must already make useful progress.
 assert(!c.beganBuffered && c.source.armed==0 && !c.source.covered);
 for(unsigned i=3;i<=11;++i)queue.push_back({{i},(i-1)*.1});
 assert(c.PrepareHDR10AIQueue(queue,preferences,"bundle",500,false,&result,false,0)==Decision::Prepare);
 assert(c.source.analysed==10 && c.source.armed==1 && c.source.covered);
 CDVBridgeGLES::Context native;preferences.hdr10Source=DVBRIDGE::HDR10SourceMode::Native;
 assert(native.PrepareHDR10AIQueue(queue,preferences,"bundle",0,false,&result,false,0)==Decision::Native);
 assert(!native.source.active && native.source.analysed==0);
}
'''.replace('FUNCTION',code)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            built=subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(ran.returncode,0,ran.stderr)
