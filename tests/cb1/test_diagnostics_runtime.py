"""Execute applied Kodi diagnostics and real refresh-switch functions without a GPU."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

TREE = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])


def function(relative, signature):
    text = (TREE / relative).read_text()
    start = text.index(signature)
    opening = text.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    # Include a function-try-block handler when production isolates diagnostics.
    tail = text[end:]
    if tail.lstrip().startswith('catch (...) {}'):
        end += len(tail) - len(tail.lstrip()) + len('catch (...) {}')
    return text[start:end]


class DiagnosticsRuntime(unittest.TestCase):
    def test_prepared_audit_retries_admission_without_consuming_epoch(self):
        from test_native_video_source import body
        state=(TREE/'xbmc/utils/DVBridgeDiagnosticState.h').read_text()
        state=state.replace(body(state,'inline bool DiagnosticsEnabled()'),'{ return testEnabled; }')
        state=state.replace(body(state,'inline uint64_t DiagnosticNowMs()'),'{ return testNow; }')
        state=state.replace('namespace DVBRIDGE\n{','namespace DVBRIDGE\n{\ninline bool testEnabled=true; inline uint64_t testNow=1000;',1)
        audit=function('xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp','void CDVBridgeGLES::PreparedAudit(')
        audit=audit.replace('void CDVBridgeGLES::','void ')
        audit=audit.replace('std::string_view sdr)', 'std::string_view sdr = {})')
        program=r'''
#include "utils/DVBridgeDiagnosticLog.h"
#include <cassert>
namespace DVBRIDGE {
struct Binding {uint64_t stream=1,picture=1,revision=3;};
struct StreamTelemetry {inline static unsigned stages=0;static void NativeStage(Binding,const char*){++stages;}};
}
struct CDVBridgeGLES {
 DVBRIDGE::Binding m_pendingIdentity,m_pendingBinding;
 static constexpr int DVBRIDGE_MODE_SDR=7;
 int m_auditPreparedSerial=0,m_auditSerial=17,m_effectiveMode=3;
 DVBRIDGE::DiagnosticFailures m_auditPrepared;
 @AUDIT@
};
int main(){
 using namespace DVBRIDGE;DiagnosticOpen();ObserveDiagnostic(1,1,3,17,"prepare",true,false);
 for(unsigned i=0;i<24;++i)assert(DiagnosticLog(LOGINFO,"startup {}",i));
 CDVBridgeGLES r;r.PreparedAudit();
 assert(r.m_auditPreparedSerial==0&&CLog::lines.size()==24&&StreamTelemetry::stages==1);
 testNow+=30001;r.PreparedAudit();assert(r.m_auditPreparedSerial==17&&CLog::lines.size()==25);
 for(unsigned i=0;i<1000;++i){r.PreparedAudit();}assert(CLog::lines.size()==25);
 ++r.m_auditSerial;r.PreparedAudit();assert(r.m_auditPreparedSerial==18&&CLog::lines.size()==26);
 testEnabled=false;++r.m_auditSerial;r.PreparedAudit();assert(r.m_auditPreparedSerial==18&&CLog::lines.size()==26);
 testEnabled=true;CLog::throws=true;r.PreparedAudit();assert(r.m_auditPreparedSerial==18);
 CLog::throws=false;testNow+=30001;r.PreparedAudit();assert(r.m_auditPreparedSerial==19&&CLog::lines.size()==27);
 @SDR_LIMITS@
}
'''.replace('@AUDIT@',audit)
        limits=r'''
 r.m_effectiveMode=7;++r.m_auditSerial;r.PreparedAudit();assert(r.m_auditPreparedSerial==19);
 testNow+=650;r.PreparedAudit(" sdr=2,1,1,1,0,0,-1");assert(r.m_auditPreparedSerial==20&&CLog::lines.size()==28);
 ++r.m_auditSerial;testNow+=30001;r.PreparedAudit(std::string(650,'x'));assert(r.m_auditPreparedSerial==20&&CLog::lines.size()==28);
 testNow+=30001;r.PreparedAudit(std::string(560,'x'));assert(r.m_auditPreparedSerial==21&&CLog::lines.size()==29);
 assert(CLog::lines.back().find("[truncated]")==std::string::npos);
 for(unsigned i=0;i<1000;++i){r.PreparedAudit(" sdr=retry");}assert(CLog::lines.size()==29);
'''
        program=program.replace('@SDR_LIMITS@',limits if 'std::string_view sdr' in audit else '')
        self.run_cpp(program,{'utils/DVBridgeDiagnosticState.h':state,
            'utils/DVBridgeDiagnosticLog.h':(TREE/'xbmc/utils/DVBridgeDiagnosticLog.h').read_text(),'utils/log.h':r'''
#pragma once
#include <fmt/format.h>
#include <string>
#include <vector>
#include <stdexcept>
constexpr int LOGINFO=1,LOGWARNING=2,LOGERROR=3;
struct CLog {
 inline static bool throws=false;inline static std::vector<std::string>lines;
 template<class...T>static void Log(int,fmt::format_string<T...>f,T&&...a){if(throws)throw std::runtime_error("offline");lines.push_back(fmt::format(f,std::forward<T>(a)...));}
};
'''})

    def test_renderer_counters_survive_normal_budget_and_bound_real_reset_lifetime(self):
        from test_native_video_source import body
        relative='xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp'
        header=(TREE/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.h').read_text()
        state=(TREE/'xbmc/utils/DVBridgeDiagnosticState.h').read_text()
        state=state.replace(body(state,'inline bool DiagnosticsEnabled()'),'{ return testEnabled; }')
        state=state.replace(body(state,'inline uint64_t DiagnosticNowMs()'),'{ return testNow; }')
        state=state.replace('namespace DVBRIDGE\n{','namespace DVBRIDGE\n{\ninline bool testEnabled=true;\ninline uint64_t testNow=1000;',1)
        member=''
        if 'using ResetDiagnosticSnapshot' in header:
            start=header.index('  using ResetDiagnosticSnapshot')
            member=header[start:header.index('m_lastResetReported;',start)+len('m_lastResetReported;')]
        source='\n'.join(function(relative, signature) for signature in (
            'void CDVBridgeGLES::Summary(', 'void CDVBridgeGLES::CountPresentation(',
            'void CDVBridgeGLES::BeginDiagnosticStream(', 'void CDVBridgeGLES::Reset()',
            'void CDVBridgeGLES::Cancel()', 'CDVBridgeGLES::~CDVBridgeGLES()'))
        log=(TREE/'xbmc/utils/DVBridgeDiagnosticLog.h').read_text()
        counter_log='DiagnosticRendererCounterLog' if 'bool DiagnosticRendererCounterLog(' in log else 'DiagnosticLog'
        self.run_cpp(r'''
#define CB1_HAS_HDR10_AI
#include "utils/DVBridgeDiagnosticLog.h"
#include <cassert>
#include <array>
#include <memory>
#include <optional>
#include <tuple>
#include <vector>
unsigned resets=0,cancels=0,driverEpoch=0;
void cb1_hdr10plus_analysis_reset(int*){++cancels;}
void cb1_hdr10plus_analysis_clear_scene(int*p){assert(!p);}
void cb1_hdr10plus_analysis_destroy(int**p){*p=nullptr;}
void dvbridge_render_dv_policy_cancel(int*){++driverEpoch;}
void dvbridge_render_policy_cancel(int*){++driverEpoch;}
void dvbridge_renderer_reset(int*){++resets;++driverEpoch;}
void glDeleteFramebuffers(int,unsigned*){}
void glDeleteTextures(int,unsigned*){}
void dvbridge_gl_packer_destroy(int*){}
void pl_tex_destroy(int,int*){}
struct CDVBridgeGLES {
 struct Context{unsigned epoch=1;void ClearNextHDR10AI(){++epoch;}void Detach(int*){}};
 struct {void reset(){}} m_playerLedCpu;
 std::shared_ptr<Context>m_context=std::make_shared<Context>();
 struct GL{int gpu=1;}gl;GL*m_gl=&gl;
 struct{int texture=1,degamma=2,pq=3;}m_nativeOverlay;
 int m_scanout=1,*m_renderer=nullptr,*m_packer=nullptr,*m_hdr10plusAnalysis=nullptr;
 int m_playerLedSource{},m_playerLedFitted{},m_playerLedCarrier{};
 unsigned m_playerLedTexture{};
 unsigned m_framebuffer=0,m_pendingInfo=8;bool m_live=true,m_advanced=true,m_dvPolicyActive=false;
 bool m_prepared=true,m_packed=true,m_pending=true,m_asyncEligible=true,m_direct=true;
 bool m_aiOutputAccepted=true,m_aiFrame=true,m_firstFrame=false;
 std::optional<int>m_aiGuidance=1,m_hdr10plusMetadata=1;
 struct{unsigned sequence=0;}m_submission{99};
 std::vector<int>m_rawELCache{1,2};
 uint64_t m_diagnosticStream=7,m_prepares=0,m_directFrames=0,m_presentations=120,m_failedPresentations=0;
 uint64_t m_lastSummary=0,m_lastReported=0,m_rawELImports=0,m_rawELHits=0;
 uint64_t m_lastPresentedSourcePicture=0,m_nonadvancingSource=0,m_sourceGaps=0;
 struct Binding{uint64_t stream=7,picture=31,revision=11;}m_pendingBinding;
 struct{uint64_t revision=13;}m_requested;
 int m_effectiveMode=8;
 DVBRIDGE::DiagnosticFailures m_failures;
 int m_hdr10plusDiagnostics=0,m_hdr10plusAnalyzed=0,m_hdr10plusGenerated=0,m_hdr10plusAccepted=0;
 unsigned m_hdr10plusSubmits=0,m_pendingHDR10Fallback=6;std::array<double,4>m_hdr10plusLight{};
 @MEMBER@
 void ClearFELPrefetch(){}
 void Summary(const char*);void CountPresentation(bool,uint64_t=0,uint64_t=0);void BeginDiagnosticStream(uint64_t);
 void Reset();void Cancel();~CDVBridgeGLES();
};
namespace DVBRIDGE{struct StreamTelemetry{static void ClearOutput(){}};}
@SOURCE@
void full(bool reserve=false){
 using namespace DVBRIDGE;
 DiagnosticOpen();ObserveDiagnostic(7,31,11,13,"prepare",true,false);
 if(reserve)DiagnosticReserveProgress();
 for(unsigned i=0;i<(reserve?18:24);++i)assert(DiagnosticLog(LOGINFO,"menu/setup {}",i));
 if(reserve)for(unsigned i=0;i<6;++i)assert(DiagnosticProgressLog(LOGINFO,"progress {}",i));
 assert(!DiagnosticLog(LOGINFO,"full"));
}
void has(const std::string&s,const char*part){assert(s.find(part)!=std::string::npos);}
int main(){
 using namespace DVBRIDGE;
 for(bool reserve:{false,true}){
  testNow=1000;full(reserve);auto count=CLog::lines.size();
  {
   CDVBridgeGLES r;r.CountPresentation(true); // Not120 boundary yet.
   assert(CLog::lines.size()==count);
   r.m_presentations=119;r.m_prepared=false;testNow=30000;r.CountPresentation(true,7);r.m_prepared=true;
   assert(CLog::lines.size()==++count && "Actual renderer periodic summary must survive full Normal/Progress ring");
   has(CLog::lines.back(),"advanced renderer summary: presented=120");
   has(CLog::lines.back(),"counter_stream=7 source_picture=0 nonadvancing_source=0 source_gaps=0 stream=7 picture=31 revision=11 policy=13");
   assert(!DiagnosticLog(LOGINFO,"Normal still full") && CLog::lines.size()==count);
   r.CountPresentation(true,6);
   assert(r.m_presentations==120 && CLog::lines.size()==count); // A retiring old stream is not new progress.
   r.Summary("summary");assert(CLog::lines.size()==count); // Same count is not a new periodic report.
   testNow=30001;r.m_presentations=239;r.CountPresentation(true);
   assert(CLog::lines.size()==count); // No new30s opportunity.
   DiagnosticFinal("close-file");assert(CLog::lines.size()==++count);
   DiagnosticFinal("duplicate");assert(CLog::lines.size()==count);
   const auto suppressed=diagnosticSession.Suppressed();
   r.Reset();assert(CLog::lines.size()==++count);has(CLog::lines.back(),"renderer reset:");
   assert(diagnosticSession.Suppressed()==suppressed);
   const auto calls=resets,epoch=driverEpoch,contextEpoch=r.m_context->epoch;
   for(int i=0;i<1000;++i)r.Reset();
   assert(CLog::lines.size()==count && resets==calls+1000 && driverEpoch>epoch && r.m_context->epoch>contextEpoch);
   assert(!r.m_prepared&&!r.m_pending&&!r.m_packed&&!r.m_direct&&!r.m_aiFrame&&r.m_firstFrame);
   assert(r.m_presentations==240 && r.m_submission.sequence==0 && r.m_rawELCache.empty());
   // Each persistent work/counter component independently permits a later reset.
   auto changed=[&]{r.Reset();assert(CLog::lines.size()==++count);r.Reset();assert(CLog::lines.size()==count);};
   ++r.m_presentations;changed();++r.m_failedPresentations;changed();
   r.m_failures.Record(testNow,"actual-stage");changed();
   ++r.m_diagnosticStream;changed();++r.m_pendingBinding.stream;changed();++r.m_pendingBinding.revision;changed();
   ++r.m_requested.revision;changed();++r.m_effectiveMode;changed();
   r.m_advanced=false;changed();has(CLog::lines.back(),"DVBridge renderer reset: prepared=0");
   ++r.m_prepares;changed();++r.m_directFrames;changed();++r.m_rawELImports;changed();++r.m_rawELHits;changed();
   ++r.m_pendingBinding.picture;r.Reset();assert(CLog::lines.size()==count); // Decoder picture alone is not new diagnostic work.
   testEnabled=false;++r.m_presentations;r.Reset();assert(CLog::lines.size()==count);
   testEnabled=true;r.Reset();assert(CLog::lines.size()==++count); // Disabled call consumed no key.
   CLog::throws=true;++r.m_presentations;r.Reset();assert(CLog::lines.size()==count);
   CLog::throws=false;r.Reset();assert(CLog::lines.size()==++count); // Failed emit consumed no key.
  }
  assert(CLog::lines.size()==++count);has(CLog::lines.back(),"renderer closed:");
  assert(!DiagnosticLog(LOGINFO,"Normal unchanged after terminal"));
  const auto failed=CLog::lines.size();DiagnosticFailureLog("first",true,LOGERROR,"real failure");
  assert(CLog::lines.size()==failed+1);DiagnosticFailureLog("first",false,LOGERROR,"duplicate failure");
  assert(CLog::lines.size()==failed+1);testNow=31000;assert(DiagnosticLog(LOGINFO,"native30s refill"));
 }
 // A real source change reports old counters with the truthful current suffix.
 testNow=100000;DiagnosticOpen();ObserveDiagnostic(7,31,11,13,"old",true,false);
 {
  CDVBridgeGLES r;r.Reset();auto count=CLog::lines.size();
  ObserveDiagnostic(9,1,17,19,"successor",true,false);r.BeginDiagnosticStream(9);
  assert(CLog::lines.size()==count+1);has(CLog::lines.back(),"renderer stream-end:");
  has(CLog::lines.back(),"counter_stream=7 source_picture=0 nonadvancing_source=0 source_gaps=0 stream=9 picture=1 revision=17 policy=19");
  assert(r.m_diagnosticStream==9&&r.m_presentations==0&&r.m_failedPresentations==0&&r.m_failures.Count()==0);
  r.Reset();assert(CLog::lines.size()==count+2); // New domain cannot reuse prior reset key.
  r.BeginDiagnosticStream(0);r.BeginDiagnosticStream(9);assert(CLog::lines.size()==count+2);
  r.CountPresentation(true,9,20);r.CountPresentation(true,9,20);r.CountPresentation(true,9,23);
  r.CountPresentation(true,7,900);
  assert(r.m_lastPresentedSourcePicture==23&&r.m_nonadvancingSource==1&&r.m_sourceGaps==2);
 }
 // All counter records retain the one formatter's byte/newline/suffix limits.
 std::string longEvent(10000,'x');longEvent[1]='\n';longEvent[2]='\r';longEvent[3]='\0';
 assert(@COUNTER_LOG@(LOGINFO,"{}",longEvent));const auto& bounded=CLog::lines.back();
 assert(bounded.size()<896 && bounded.find('\n')==std::string::npos && bounded.find('\r')==std::string::npos && bounded.find('\0')==std::string::npos);
 has(bounded,"[truncated]");has(bounded,"stream=9 picture=1 revision=17 policy=19 suppressed=");has(bounded,"truncations=1");
 testEnabled=false;auto count=CLog::lines.size();assert(!@COUNTER_LOG@(LOGINFO,"disabled"));assert(CLog::lines.size()==count);
 // No new callback means no synthetic record or timer-driven retry.
 testNow+=100000;assert(CLog::lines.size()==count);
}
'''.replace('@MEMBER@',member).replace('@SOURCE@',source).replace('@COUNTER_LOG@',counter_log),
            {'utils/DVBridgeDiagnosticState.h':state,'utils/DVBridgeDiagnosticLog.h':log,'utils/log.h':r'''
#pragma once
#include <fmt/format.h>
#include <string>
#include <vector>
#include <stdexcept>
constexpr int LOGINFO=1,LOGWARNING=2,LOGERROR=3;
struct CLog {
 inline static std::vector<std::string>lines;inline static bool throws=false;
 template<class...T>static void Log(int,fmt::format_string<T...>f,T&&...a){
  if(throws)throw std::runtime_error("controlled logger failure");
  lines.push_back(fmt::format(f,std::forward<T>(a)...));}
};
'''})

    def test_fel_dma_witness_reports_exported_pitch_offset_and_modifier(self):
        text=(TREE/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        marker=text.find('"CB1 FEL DMA:')
        witness=''
        if marker>=0:
            start=text.rfind('      if (cacheable && !m_rawELImports)',0,marker)
            witness=text[start:text.index('      if (cacheable && !m_rawELCache.empty()',marker)]
        self.run_cpp(r'''
#include <fmt/format.h>
#include <cassert>
#include <string>
#include <vector>
constexpr int LOGINFO=1;
namespace DVBRIDGE {
inline std::vector<std::string> lines;
template<class...T>void DiagnosticLog(int,fmt::format_string<T...> f,T&&...a){
 lines.push_back(fmt::format(f,std::forward<T>(a)...));}
}
void Report(bool cacheable,bool newFELSource){
 (void)cacheable;(void)newFELSource;
 const unsigned m_rawELImports=newFELSource?0:3;(void)m_rawELImports;
 struct {struct{unsigned stream=3,picture=1,revision=7;}binding;}base;
 struct {unsigned objects_count=2;unsigned objects[2][4]={{0,0,0,0x123},{0,0,0,0x456}};
 unsigned layers[2][5]={{1,1,1,4096,4096},{2,1,0,8192,4096}};}key;
 BLOCK
}
int main(){
 Report(true,true);assert(DVBRIDGE::lines.size()==1);
 for(auto part:{"source=3/1/7","pitch=4096/4096","offset=4096/8192","modifier=0x456/0x123"})
  assert(DVBRIDGE::lines.back().find(part)!=std::string::npos);
 Report(false,true);Report(true,false);assert(DVBRIDGE::lines.size()==1);
}
'''.replace('BLOCK',witness))

    def test_incomplete_profile_reports_the_values_before_output_admission(self):
        text = (TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        start = text.index('  if (m_dvSelection.reason == DVBRIDGE::OutputReason::TVProfileRequired)')
        end = text.index('  if (m_dvConfiguredOutput', start)
        self.run_cpp(r'''
#include <fmt/format.h>
#include <cassert>
#include <cstdint>
#include <string>
#include <vector>
constexpr int LOGWARNING=2;
namespace DVBRIDGE {
enum class OutputReason {None,TVProfileRequired};
inline std::vector<std::string> lines;
void DiagnosticStage(const char*){}
template<class...T>bool DiagnosticLog(int,fmt::format_string<T...> f,T&&...a){
 lines.push_back(fmt::format(f,std::forward<T>(a)...));return true;}
}
struct Window {
 uint64_t m_dvProfileLoggedRevision{},m_dvProfileLoggedStream{};
 struct {DVBRIDGE::OutputReason reason=DVBRIDGE::OutputReason::TVProfileRequired;}m_dvSelection;
 struct {uint64_t stream=12;}binding;
 struct {uint64_t revision=3;int panel=0,gamut=0;double peak=1410;}preferences;
 void Report(){ BLOCK }
};
int main(){
 Window window;window.Report();
 assert(DVBRIDGE::lines.size()==1);
 for(auto part:{"peak=1410","panel=0","gamut=0","peak_and_gamut_required"})
  assert(DVBRIDGE::lines.back().find(part)!=std::string::npos);
 window.Report();assert(DVBRIDGE::lines.size()==1);
 ++window.preferences.revision;window.Report();assert(DVBRIDGE::lines.size()==2);
 window.m_dvSelection.reason=DVBRIDGE::OutputReason::None;
 ++window.preferences.revision;window.Report();assert(DVBRIDGE::lines.size()==2);
}
'''.replace('BLOCK',text[start:end]))

    def test_real_render_failure_identifies_ipt_and_target_without_changing_policy(self):
        failure = function('xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp', 'bool CDVBridgeGLES::Failure(')
        self.run_cpp(r'''
#include "utils/DVBridgeDiagnosticState.h"
#include <fmt/format.h>
#include <cassert>
#include <vector>
constexpr int LOGERROR=3,LOGWARNING=2;
namespace DVBRIDGE {
inline std::vector<std::string> lines;
template<class...T>void DiagnosticFailureLog(const char*,bool,int,fmt::format_string<T...> f,T&&...a){
 lines.push_back(fmt::format(f,std::forward<T>(a)...));}
template<class...T>void DiagnosticLog(T...){}
struct StreamTelemetry{static void ReferenceWarning(){}};
}
struct CDVBridgeGLES {
 bool m_live=true,m_advanced=false,m_hasCommitted=false,m_hdr10=false,m_pending=false,m_prepared=false;
 int m_effectiveMode=5;void* m_scanout=this;unsigned m_outputBits=8;
 struct {bool masterIPT=true;}m_requested;
 struct {int stream=3,revision=1;}m_pendingBinding,m_committedBinding;
 DVBRIDGE::DiagnosticFailures m_failures;
 bool Failure(const char* stage);
};
''' + failure + r'''
int main(){
 CDVBridgeGLES renderer;
 assert(!renderer.Failure("master-reference-invalid-metadata"));
 assert(renderer.m_effectiveMode==5 && renderer.m_requested.masterIPT && renderer.m_failures.Count()==1);
 const auto& text=DVBRIDGE::lines.back();
 for(auto part:{"master-reference-invalid-metadata","mode=5","master_ipt=true","target=true","output_bits=8"})
  assert(text.find(part)!=std::string::npos);
}
''')

    def test_boot_capability_denial_survives_until_kodi_collects_it(self):
        self.run_cpp(r'''
#include "utils/DVBridgeKernelLog.h"
#include <cassert>
int main(){
 DVBRIDGE::KernelLogFilter filter;
 auto line=filter.Accept("6,1,1000000,-;amdgpu 0000:03:00.0: DVBridge: AMD capability connector=409 family_supported=0 native_hdmi=1\n",900000000);
 assert(line && line->find("family_supported=0")!=std::string::npos);
 assert(!filter.Accept("6,2,1000000,-;DVBridge: old frame detail\n",900000000));
 assert(!filter.Accept("6,3,1000000000,-;DVBridge: AMD capability future\n",900000000));
 assert(!filter.Accept("6,1,1000000,-;DVBridge: AMD capability duplicate\n",900000000));
}
''')

    def test_first_frame_and_policy_details_report_real_layer_and_display_values(self):
        # A swapped logical/physical size or omitted display value loses the witness.
        text = (TREE / 'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        calls = []
        for message in ('DVBridge first frame:', 'DVBridge policy requested:'):
            start = text.rfind('DVBRIDGE::DiagnosticLog(', 0, text.index(message))
            end = text.index(';', start) + 1
            calls.append(text[start:end])
        self.run_cpp(r'''
#include "utils/DVBridgeDiagnosticLog.h"
#include <cassert>
struct Layer { int width,height,layout; struct Plane {int width,height;unsigned texture=0;} planes[3]; int chromaLocation; };
struct Binding {int stream=3,picture=4,revision=5;};
struct Base : Layer {Binding binding;};
struct CDVPlaybackInfo {static constexpr int FEL=1,CM4=2;};
struct ReturnedPolicy {int mode=2;};
struct Preferences {
 int method=1,panel=2,gamut=3;double peak=1500;
 bool ProfileValid()const{return true;}
 ReturnedPolicy Policy()const{return {};}
 bool L2TrimsDisabled(int)const{return false;}
};
int main(){
 DVBRIDGE::DiagnosticOpen();
 Base base{{1920,1080,1,{{2048,1088},{1024,544},{0,0}},2},{}};
 Layer el{960,540,2,{{1024,544},{512,272},{0,0}},1};const Layer* enhancement=&el;
 base.planes[0].texture=11;base.planes[1].texture=12;
 el.planes[0].texture=21;el.planes[1].texture=22;
 struct {int width=3840,height=2160,x=0,y=0;bool ignore_l5=false;} geometry;
 int m_pendingInfo=3;bool m_direct=true,m_fallback=false;
 int revision=7;Preferences preferences;ReturnedPolicy policy;
 FIRST
 POLICY
 assert(CLog::lines.size()==2);
 const auto& frame=CLog::lines[0];
 for(auto key:{"bl_layout=1","bl_texture=2048x1088","el=960x540", "el_texture=1024x544","bl_chroma=2","el_chroma=1"})
  assert(frame.find(key)!=std::string::npos);
 for(auto key:{"bl_uv_texture=1024x544","el_uv_texture=512x272"})
  assert(frame.find(key)!=std::string::npos);
 for(auto key:{"bl_texture_ids=11,12","el_texture_ids=21,22"})
  assert(frame.find(key)!=std::string::npos);
 const auto& settings=CLog::lines[1];
 for(auto key:{"tv_peak=1500","tv_panel=2","tv_gamut=3","tv_profile_valid=true","method=1","encoded_active_area=false"})
  assert(settings.find(key)!=std::string::npos);
 enhancement=nullptr;
 FIRST
 assert(CLog::lines.back().find("el=0x0")!=std::string::npos);
 assert(CLog::lines.back().find("el_texture=0x0")!=std::string::npos);
}
'''.replace('FIRST', calls[0]).replace('POLICY', calls[1]), {'utils/log.h':r'''
#pragma once
#include <fmt/format.h>
#include <string>
#include <vector>
constexpr int LOGINFO=1,LOGWARNING=2,LOGERROR=3;
struct CLog {
 inline static std::vector<std::string> lines;
 template<class...T>static void Log(int,fmt::format_string<T...> f,T&&...a){
  lines.push_back(fmt::format(f,std::forward<T>(a)...));
 }
};
'''})

    def test_first_presentation_logs_once_only_for_the_current_live_stream(self):
        self.run_cpp(r'''
#include "utils/DVBridgeDiagnosticLog.h"
#include <cassert>
int main(){
 using namespace DVBRIDGE;
 DiagnosticOpen();const auto previous=DiagnosticGeneration();DiagnosticPresented(0);
 assert(!diagnosticSession.FirstPresented() && CLog::lines.empty());
 ObserveDiagnostic(7,1,1,1,"prepare",true,false);
 DiagnosticPresented(6);assert(!diagnosticSession.FirstPresented() && CLog::lines.empty());
 DiagnosticPresented(7);assert(diagnosticSession.FirstPresented() && CLog::lines.size()==1);
 assert(CLog::lines.back().find("stage=first-presented")!=std::string::npos);
 for(int n=0;n<1000;++n)DiagnosticPresented(7);
 assert(CLog::lines.size()==1);
 DiagnosticFinal("stop");auto count=CLog::lines.size();
 DiagnosticPresented(7);assert(CLog::lines.size()==count);
 DiagnosticOpen();DiagnosticCandidate();const auto current=DiagnosticGeneration();
 DiagnosticStartup(previous,7,"late-decoder",true,1);
 assert(CLog::lines.size()==count);
 DiagnosticStartup(current,8,"base-decoded",false,0);
 assert(CLog::lines.size()==count+1);
 assert(std::string_view(diagnosticSession.Stage())=="base-decoded");
 DiagnosticFinal("before-picture");auto closed=CLog::lines.size();
 DiagnosticStartup(current,8,"late-after-stop",false,0);assert(CLog::lines.size()==closed);
 DiagnosticOpen();ObserveDiagnostic(8,1,1,1,"prepare",true,false);
 DiagnosticPresented(7);assert(!diagnosticSession.FirstPresented());
 DiagnosticPresented(8);assert(CLog::lines.size()==closed+1);
 const auto open=DiagnosticGeneration();
 DiagnosticStartup(open,9,"reopened-decoder",true,1);
 assert(CLog::lines.back().find("decoder_stream=9")!=std::string::npos);
 assert(std::string_view(diagnosticSession.Stage())=="prepare");
 ObserveDiagnostic(9,1,1,1,"new-render",true,false);
 auto latest=CLog::lines.size();
 DiagnosticStartup(open,8,"old-codec-late",true,0);
 assert(CLog::lines.size()==latest);
 assert(std::string_view(diagnosticSession.Stage())=="new-render");
}
''', {'utils/log.h':r'''
#pragma once
#include <fmt/format.h>
#include <string>
#include <vector>
constexpr int LOGINFO=1,LOGWARNING=2,LOGERROR=3;
struct CLog{
 inline static std::vector<std::string> lines;
 template<class...T>static void Log(int,fmt::format_string<T...> f,T&&...a){
  lines.push_back(fmt::format(f,std::forward<T>(a)...));
 }
};
'''})

    def test_diagnostic_details_keep_the_shared_line_budget(self):
        for _ in range(1):
            self.run_cpp(r'''
#include "utils/DVBridgeDiagnosticLog.h"
#include <cassert>
int main(){
 DVBRIDGE::DiagnosticOpen();
 for(unsigned i=0;i<100;++i) DVBRIDGE::DiagnosticLog(LOGDEBUG,"detail {}",i);
 assert(CLog::levels.size()==24);
 for(int level:CLog::levels) assert(level==EXPECTED);
}
'''.replace('EXPECTED', 'LOGDEBUG'), {'utils/log.h':r'''
#pragma once
#include <fmt/format.h>
#include <vector>
constexpr int LOGDEBUG=0,LOGINFO=1,LOGWARNING=2,LOGERROR=3;
struct CLog {
 inline static std::vector<int> levels;
 template<class...T>static void Log(int level,fmt::format_string<T...>,T&&...){levels.push_back(level);}
};
'''})

    def run_cpp(self, program, files=None):
        with tempfile.TemporaryDirectory(prefix='dv-diagnostic-') as folder:
            root = Path(folder)
            (root / 'check.cpp').write_text(program)
            for name, data in (files or {}).items():
                destination = root / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(data)
            result = subprocess.run(['c++', '-std=c++20', '-Wall', '-Wextra', '-Werror',
                '-pthread', '-DFMT_HEADER_ONLY', '-I', folder, '-I', str(TREE / 'xbmc'),
                '-idirafter', os.environ.get('CB1_FMT_INCLUDE', '/usr/include'),
                str(root / 'check.cpp'), '-o', str(root / 'check')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(root / 'check')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_common_sliding_budget_first_failure_final_and_wait_lifecycle(self):
        # Removing the shared line gate or resetting it on recovery must overflow this test.
        self.run_cpp(r'''
#include "utils/DVBridgeDiagnosticState.h"
#include <cassert>
#include <vector>
#include <thread>
int main() {
  using namespace DVBRIDGE;
  DiagnosticSession adoption;
  adoption.Candidate(1);
  for(unsigned n=0;n<24;++n) assert(adoption.Admit(1,DiagnosticEvent::Normal));
  assert(adoption.Admit(1,DiagnosticEvent::Failure));
  adoption.Observe(2,99,1,1,1,"first-bound-picture",true,false);
  assert(!adoption.Admit(2,DiagnosticEvent::Normal));
  assert(!adoption.Admit(2,DiagnosticEvent::Failure));
  adoption.Open();
  assert(adoption.Admit(3,DiagnosticEvent::Normal));
  DiagnosticSession session;
  session.Observe(100,12,1,7,9,"admission",true,false);
  std::vector<uint64_t> emitted;
  for(unsigned now=100;now<60100;++now) {
    if(session.Admit(now,DiagnosticEvent::Normal)) emitted.push_back(now);
  }
  for(auto first:emitted) {
    unsigned count=0;
    for(auto time:emitted) count+=time>=first && time-first<30000;
    assert(count<=24);
  }
  assert(session.Suppressed()>59000);
  for(unsigned n=0;n<24;++n) session.Admit(60100,DiagnosticEvent::Normal);
  assert(session.Admit(60100,DiagnosticEvent::Failure));
  assert(!session.Admit(60100,DiagnosticEvent::Failure));
  session.Failure("old-generation");
  session.Observe(60100,12,2,8,10,"seek",true,false);
  assert(std::string_view(session.FirstFailure())=="none");
  assert(!session.Admit(60100,DiagnosticEvent::Failure)); // No new exemption on seek/policy.
  assert(session.Admit(60100,DiagnosticEvent::Final));
  assert(!session.Admit(60100,DiagnosticEvent::Final));
  assert(!session.WaitDue(60101));
  session.Observe(70000,13,1,8,10,"import",true,false);
  assert(!session.WaitDue(74999));
  assert(session.WaitDue(75000));
  assert(!session.WaitDue(104999));
  assert(session.WaitDue(105000));
  session.Observe(105001,13,1,8,10,"import",true,true);
  assert(!session.WaitDue(150000));
  session.Observe(150000,13,2,8,10,"import",true,false);
  assert(!session.WaitDue(154999));
  assert(session.WaitDue(155000));
  session.Presented(13);
  assert(!session.WaitDue(200000));
  session.Observe(200000,12,99,7,9,"late-old-stream",true,false);
  assert(session.Stream()==13);
  assert(session.Admit(200000,DiagnosticEvent::Final));
  session.Observe(200001,13,3,8,10,"late-after-stop",true,false);
  assert(!session.WaitDue(300000));
  session.Open(); session.Candidate(1);
  assert(session.Admit(2,DiagnosticEvent::Final)); // Stop before any picture/renderer.
  assert(!session.Admit(2,DiagnosticEvent::Final));
  DiagnosticProperty unknown(false,std::nullopt), absent(true,std::nullopt),
      zero(true,0),one(true,1);
  assert(unknown.Presence()==std::string_view("unknown") && unknown.Value()=="unavailable");
  assert(absent.Presence()==std::string_view("absent") && absent.Value()=="unavailable");
  assert(zero.Presence()==std::string_view("present") && zero.Value()=="0");
  assert(one.Presence()==std::string_view("present") && one.Value()=="1");
  assert(!(absent==zero));
}
''')

    def test_same_size_refresh_updates_only_accepted_current_mode(self):
        # Missing SetFullScreen refresh leaves startup-120Hz facts after 23.976Hz success.
        relative = 'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp'
        switch = function(relative, 'bool CWinSystemGbmGLESContext::SetFullScreen(')
        refresh = function(relative, 'void CWinSystemGbmGLESContext::RefreshDVOutputCapabilities()')
        self.run_cpp(r'''
#include <cassert>
#include <memory>
#include <mutex>
#include <array>
#include <optional>
#include <stdexcept>
#include "utils/DVBridgeDiagnosticState.h"
#include "windowing/gbm/ModeChangeHold.h"
#include <atomic>
using namespace KODI::WINDOWING::GBM;
#define HAVE_DVBRIDGE
constexpr int EGL_NO_CONTEXT=0, EGL_OPENGL_ES3_BIT=3, LOGDEBUG=0, LOGERROR=1, LOGINFO=2;
constexpr int D3DPRESENTFLAG_MODE3DSBS=1,D3DPRESENTFLAG_MODE3DTB=2;
enum class RenderStereoMode {MONO};
enum dvbridge_mode {DVBRIDGE_MODE_DISABLED,DVBRIDGE_MODE_SDR=7};
namespace DVBRIDGE {enum class OutputReason {None,NoGPUProcessing};
inline std::atomic<int> modeChangeResolution{-1};
inline thread_local std::optional<int> guiModeChangeResolution;
template<class... T> void DiagnosticLog(T...) {}}
struct Admission {bool usable=false; DVBRIDGE::OutputReason reason{};};
struct Caps {unsigned generation=1;bool nativeDV=false,hdr10=false,hdr10plus=false,processingKnown=false;
  std::array<Admission,7> processing{},hdr10Processing{};};
inline int eglGetCurrentContext() {return 1;}
inline bool pl_opengl_has_ext(int,const char*) {return true;}
inline bool dvbridge_renderer_supports_mode(int*,dvbridge_mode) {return true;}
inline bool dvbridge_renderer_supports_hdr10_ai(int*,dvbridge_mode) {return true;}
struct CLog {template<class... T> static void Log(T...) {}};
struct CEGLUtils {template<class... T> static void Log(T...) {}};
struct RESOLUTION_INFO {int iWidth=3840,iHeight=2160,dwFlags=0; double rate=60; std::string strId;};
enum RESOLUTION {RES_DESKTOP};
struct CDisplaySettings {static CDisplaySettings& GetInstance() {static CDisplaySettings value; return value;}
 RESOLUTION_INFO GetResolutionInfo(RESOLUTION) {return {};}};
struct Connector {bool HasPropertyInventory() const {return true;}
  bool SupportsProperty(const char*) const {return false;}
  std::optional<uint64_t> GetPropertyValue(const char*) const {return 0;}
  unsigned GetId() const {return 42;}};
struct DRM {virtual ~DRM()=default; double rate=120; bool accept=true,receipt=true;
  Connector connector; Connector* GetConnector() {return &connector;}};
struct Info {struct Sink {unsigned status=0,version=2;}; Sink GetDolbyVisionCaps() const {return {};}
 int HDR10PlusVersion() const {return -1;}};
inline const char* dvbridge_edid_reason(unsigned) {return "standard-dv";}
struct CDRMAtomic:DRM {bool IsSelectedModeCommitted() const {return receipt;}};
struct EGL {bool TrySwapBuffers() {return true;} int GetEGLContext() const {return 1;}};
struct CDVBridgeGLES {
  bool HasRenderer() const {return true;}
  bool SupportsMode(dvbridge_mode) const {return true;}
  bool SupportsHDR10AI(dvbridge_mode) const {return true;}
  struct Context {bool Initialize(bool) {return true;} int* Attach() {return nullptr;}
    int GL() const {return 1;} void Detach(int*) {}};
};
struct CWinSystemGbm {
  std::shared_ptr<DRM> m_DRM=std::make_shared<CDRMAtomic>();
  bool SetFullScreen(bool,RESOLUTION_INFO& res,bool) {
    if(!m_DRM->accept) return false;
    if(m_DRM->receipt) m_DRM->rate=res.rate;
    return true;
  }
};
struct CRenderSystemGLES {static void ResetRenderSystem(int,int) {}};
struct CWinSystemGbmGLESContext:CWinSystemGbm,CRenderSystemGLES {
  CModeChangeHold m_modeHold; CHeldModeAnnouncement m_modeAnnouncement;
  bool HoldCB1Mode(RESOLUTION_INFO&) {return false;}
  bool SupportsDVOutputMode() const {return m_DRM->rate<=60;}
  int m_nWidth=3840,m_nHeight=2160,m_renderableType=EGL_OPENGL_ES3_BIT;
  EGL m_eglContext; Caps m_dvCapabilities; std::mutex m_dvCapabilityMutex;
  std::unique_ptr<Info> m_info=std::make_unique<Info>();
  const Info* GetDisplayInfo() const {return m_info.get();}
  std::unique_ptr<CDVBridgeGLES> m_dvBridge;
  std::shared_ptr<CDVBridgeGLES::Context> m_dvContext;
  bool m_dvAvailableNativeDV=false,m_dvAvailableHDR10=false;
  int m_dvLldvStatus{};
  int GetLldvConnectorStatus() const {return m_dvLldvStatus;}
  bool EndDVBridge() {return true;} bool RetireDVContext() {return true;}
  bool PrepareNvidiaModeRestore(const RESOLUTION_INFO&) {return true;}
  bool SupportsNativeDVOutput(bool current=true) const {return !current || m_DRM->rate<=60;}
  bool SupportsHDR10Conversion(bool current=true) const {return SupportsNativeDVOutput(current);}
  Caps GetDVOutputCapabilities(std::nullptr_t) const {return m_dvCapabilities;}
  struct Gfx {void SetStereoMode(RenderStereoMode) {}};
  Gfx GetGfxContext() {return {};}
  bool CreateNewWindow(const char*,bool,RESOLUTION_INFO&) {return true;}
  bool SetFullScreen(bool,RESOLUTION_INFO&,bool);
  void RefreshDVOutputCapabilities();
  void RefreshHDR10LinkDepth() {}
};
''' + refresh + '\n' + switch + r'''
int main() {
  CWinSystemGbmGLESContext w;
  w.RefreshDVOutputCapabilities();
  assert(!w.m_dvCapabilities.nativeDV && w.m_dvAvailableNativeDV);
  RESOLUTION_INFO film; film.rate=24000.0/1001;
  assert(w.SetFullScreen(true,film,false));
  assert(w.m_DRM->rate<24 && w.m_dvCapabilities.nativeDV);
  film.rate=120;
  assert(w.SetFullScreen(true,film,false));
  assert(!w.m_dvCapabilities.nativeDV && w.m_dvAvailableNativeDV);
  film.rate=60; w.m_DRM->accept=false;
  assert(w.SetFullScreen(true,film,false)); // Preserve ordinary caller's historical return.
  assert(!w.m_dvCapabilities.nativeDV);
  w.m_DRM->accept=true; w.m_DRM->receipt=false;
  assert(w.SetFullScreen(true,film,false));
  assert(!w.m_dvCapabilities.nativeDV); // A test/request is not an accepted mode.
}
''')

    def test_actual_logging_adapter_bounds_lines_and_swallows_callback_exceptions(self):
        backend = function('xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp', 'void BackendLog(')
        self.run_cpp(r'''
#include "utils/DVBridgeDiagnosticLog.h"
#include <cassert>
using pl_log_level=int;
''' + backend + r'''
int main() {
  using namespace DVBRIDGE;
  ObserveDiagnostic(12,1,7,9,"admission",true,false);
  for(unsigned n=0;n<100;++n) DiagnosticLog(LOGINFO,"producer={} value={}",n%8,n);
  assert(CLog::lines.size()==24);
  DiagnosticFailureLog("base-import",true,LOGERROR,"first failure");
  assert(CLog::lines.size()==25);
  DiagnosticFinal("stop"); DiagnosticFinal("duplicate-stop");
  assert(CLog::lines.size()==26);
  assert(CLog::lines.back().find("first_failure=base-import")!=std::string::npos);
  assert(CLog::lines.back().find("first_present=false")!=std::string::npos);
  ObserveDiagnostic(13,1,1,1,"prepare",true,false);
  DiagnosticLog(LOGINFO,"long={}\nsecret-line",std::string(4096,'x'));
  assert(CLog::lines.back().size()+128<=1024);
  assert(CLog::lines.back().find("[truncated]")!=std::string::npos);
  assert(CLog::lines.back().find('\n')==std::string::npos);
  BackendLog(nullptr,1,"old renderer callback");
  assert(CLog::lines.back().find("association=backend-unscoped")!=std::string::npos);
  CLog::throws=true;
  BackendLog(nullptr,2,"C callback failure");
  DiagnosticLog(LOGERROR,"callback error");
  DiagnosticFailureLog("graphics",true,LOGERROR,"callback {}",42);
  CLog::throws=false;
  DiagnosticOpen();
  diagnosticSession.Observe(0,14,1,1,1,"output-admission",true,false);
  const auto beforeDisable=CLog::lines.size();
  DiagnosticTick(false);
  assert(!diagnosticSession.WaitDue(DiagnosticNowMs()+60000));
  assert(CLog::lines.size()==beforeDisable); // No missing-activation alert after disabling.
  DiagnosticOpen();
  DiagnosticTick(true);
  assert(!diagnosticSession.WaitDue(DiagnosticNowMs()+60000)); // Do not arm ordinary SDR/HDR.
}
''', {'utils/log.h': r'''
#pragma once
#include <fmt/format.h>
#include <string>
#include <vector>
#include <stdexcept>
constexpr int LOGINFO=1,LOGWARNING=2,LOGERROR=3;
struct CLog {
  inline static bool throws=false;
  inline static std::vector<std::string> lines;
  template<class... T> static void Log(int,fmt::format_string<T...> f,T&&... a) {
    if(throws) throw std::runtime_error("logger unavailable");
    lines.push_back(fmt::format(f,std::forward<T>(a)...));
  }
};
'''})

    def test_signal_cache_distinguishes_missing_zero_one_and_unknown(self):
        report = function('xbmc/windowing/gbm/drm/DRMAtomic.cpp', 'void CDRMAtomic::ReportSignalState()')
        self.run_cpp(r'''
#include "utils/DVBridgeDiagnosticLog.h"
#include <cassert>
#include <map>
#include <memory>
#include <vector>
inline uint64_t DVNowMs() {return 1;}
struct Object {
  bool known=true;
  std::map<std::string,uint64_t> properties;
  bool HasPropertyInventory() const {return known;}
  std::optional<int> PropertyInventoryError() const {return std::nullopt;}
  unsigned GetId() const {return 42;}
  std::optional<uint64_t> GetPropertyValue(const char* name) const {
    auto it=properties.find(name);
    return it==properties.end()?std::nullopt:std::optional<uint64_t>(it->second);
  }
};
struct Mode {uint64_t hdisplay=3840,vdisplay=2160,clock=594000,htotal=4400,vtotal=2250,flags=0,vscan=0;};
struct State {
  std::vector<uint64_t> values;
  template<size_t N> bool operator==(const std::array<uint64_t,N>& other) const {
    return values==std::vector<uint64_t>(other.begin(),other.end());
  }
  template<size_t N> State& operator=(const std::array<uint64_t,N>& other) {
    values.assign(other.begin(),other.end()); return *this;
  }
};
struct CDRMAtomic {
  Object connectorStorage, crtcStorage;
  Object* m_connector=&connectorStorage;
  Object* m_crtc=&crtcStorage;
  Mode storage,*m_mode=&storage,m_committedMode;
  bool m_signalKnown=false; State m_signalState;
  uint64_t m_signalWindow=0; unsigned m_signalReports=0;
  void ReportSignalState() noexcept;
};
''' + report + r'''
int main() {
  CDRMAtomic drm;
  drm.ReportSignalState();
  assert(CLog::lines.back().find("dv_property=absent dv_value=unavailable")!=std::string::npos);
  auto count=CLog::lines.size();
  drm.m_connector->properties["DVBRIDGE_DV_STANDARD_LAB"]=0;
  drm.ReportSignalState();
  assert(CLog::lines.size()==count+1);
  assert(CLog::lines.back().find("dv_property=present dv_value=0")!=std::string::npos);
  drm.m_connector->properties["DVBRIDGE_DV_STANDARD_LAB"]=1;
  drm.ReportSignalState();
  assert(CLog::lines.back().find("dv_property=present dv_value=1")!=std::string::npos);
  count=CLog::lines.size();
  drm.m_connector->properties["NV_HDMI_VSIF_METADATA"]=9;
  drm.ReportSignalState();
  assert(CLog::lines.size()==count+1);
  assert(CLog::lines.back().find("nv_vsif_value=9")!=std::string::npos);
  drm.ReportSignalState();
  assert(CLog::lines.size()==count+1);
  drm.m_connector->properties["dithering mode"]=1;
  drm.ReportSignalState();
  assert(CLog::lines.size()==count+2);
  assert(CLog::lines.back().find("dither_value=1")!=std::string::npos);
  drm.m_connector->known=false; drm.ReportSignalState();
  assert(CLog::lines.back().find("dv_property=unknown dv_value=unavailable")!=std::string::npos);
  drm.m_connector=nullptr; drm.ReportSignalState();
}
''', {'utils/log.h': r'''
#pragma once
#include <fmt/format.h>
#include <string>
#include <vector>
constexpr int LOGINFO=1,LOGWARNING=2,LOGERROR=3;
struct CLog {
  inline static std::vector<std::string> lines;
  template<class... T> static void Log(int,fmt::format_string<T...> f,T&&... a) {
    lines.push_back(fmt::format(f,std::forward<T>(a)...));
  }
};
'''})

    def test_kernel_reader_reports_complete_empty_and_io_error_coverage(self):
        reader = function('xbmc/windowing/gbm/drm/DVBridgeKernelLogReader.h', 'class KernelLogReader') + ';'
        self.run_cpp(r'''
#include "utils/DVBridgeKernelLog.h"
#include <fmt/format.h>
#include <array>
#include <mutex>
#include <chrono>
#include <cerrno>
#include <fcntl.h>
#include <unistd.h>
#include <cassert>
#include <vector>
#include <cstring>
constexpr int LOGINFO=1,LOGWARNING=2,LOGERROR=3;
struct CLog {
  inline static std::vector<std::string> lines;
  template<class... T> static void Log(int,fmt::format_string<T...> f,T&&... a) {
    lines.push_back(fmt::format(f,std::forward<T>(a)...));
  }
};
inline int readError=EAGAIN,openError=0; inline bool recordReady=false;
inline int fakeOpen(const char*,int) {if(openError) {errno=openError; return -1;} return 42;}
inline int fakeClose(int) {return 0;}
inline int fakeClock(int,timespec* now) {now->tv_sec=70;now->tv_nsec=0; return 0;}
inline ssize_t fakeRead(int,char* bytes,size_t) {
  if(recordReady) {recordReady=false;const char* record="3,1,69000000,-;DVBridge: link rejected\n";
    std::memcpy(bytes,record,std::strlen(record));return std::strlen(record);}
  errno=readError;return -1;
}
#define open fakeOpen
#define close fakeClose
#define read fakeRead
#define clock_gettime fakeClock
namespace DVBRIDGE {
''' + reader + r'''
}
#undef open
#undef close
#undef read
#undef clock_gettime
bool contains(const char* part) {for(auto& line:CLog::lines) if(line.find(part)!=std::string::npos) return true; return false;}
int main() {
  using namespace DVBRIDGE;
  {KernelLogReader reader; assert(!reader.Collect());
   assert(contains("complete=true") && contains("matched=0"));}
  CLog::lines.clear(); readError=EIO;
  {KernelLogReader reader; assert(!reader.Collect());
   assert(contains("complete=false") && contains("read-error") && contains("error=5"));}
  CLog::lines.clear(); openError=EACCES;
  {KernelLogReader reader; assert(!reader.Collect());
   assert(contains("complete=false") && contains("open-error") && contains("error=13"));}
  CLog::lines.clear(); openError=0;readError=EAGAIN;recordReady=true;
  {KernelLogReader reader; assert(!reader.Collect());
   assert(contains("complete=true") && contains("matched=1"));}
}
''')

    def test_actual_inventory_keeps_exact_query_error_across_cleanup(self):
        query = function('xbmc/windowing/gbm/drm/DRMObject.cpp', 'bool CDRMObject::GetProperties(')
        inventory = function('xbmc/windowing/gbm/drm/DRMObject.h', 'bool HasPropertyInventory() const')
        self.run_cpp(r'''
#include <cassert>
#include <memory>
#include <vector>
#include <optional>
#include <cstdint>
#include <cerrno>
struct drmModeObjectProperties {uint32_t count_props=2; uint32_t props[2]={1,2};};
struct drmModePropertyRes {};
inline bool failList=false,failProperty=false; inline unsigned count=2;
inline drmModeObjectProperties* drmModeObjectGetProperties(int,unsigned,unsigned) {
  if(failList) {errno=EIO;return nullptr;} auto* p=new drmModeObjectProperties; p->count_props=count;return p;
}
inline drmModePropertyRes* drmModeGetProperty(int,unsigned id) {
  if(failProperty && id==1) {errno=ENOMEM;return nullptr;}
  errno=ERANGE;return new drmModePropertyRes;
}
struct CDRMObject {
  struct DrmModeObjectPropertiesDeleter {
    void operator()(drmModeObjectProperties* p) const {delete p;errno=EBADF;}
  };
  struct DrmModePropertyResDeleter {void operator()(drmModePropertyRes* p) const {delete p;errno=EBADF;}};
  std::unique_ptr<drmModeObjectProperties,DrmModeObjectPropertiesDeleter> m_props;
  std::vector<std::unique_ptr<drmModePropertyRes,DrmModePropertyResDeleter>> m_propsInfo;
  std::optional<int> m_propertyInventoryError;
  int m_fd=1;unsigned m_id=0,m_type=0;
  bool GetProperties(uint32_t,uint32_t);
''' + inventory + r'''
};
''' + query + r'''
int main() {
  CDRMObject object;
  assert(!object.HasPropertyInventory());
  assert(object.GetProperties(42,1) && object.HasPropertyInventory());
  assert(!object.m_propertyInventoryError);
  failList=true;
  assert(!object.GetProperties(42,1) && !object.HasPropertyInventory());
  assert(object.m_propertyInventoryError==EIO); // Old inventory deleter changed errno to EBADF.
  failList=false;failProperty=true;
  CDRMObject partial;
  assert(partial.GetProperties(42,1)); // Preserve historical playback result.
  assert(!partial.HasPropertyInventory() && partial.m_propertyInventoryError==ENOMEM);
  failProperty=false;count=0;
  CDRMObject empty;
  assert(empty.GetProperties(42,1) && empty.HasPropertyInventory());
  assert(!empty.m_propertyInventoryError);
}
''')


if __name__ == '__main__':
    unittest.main()
