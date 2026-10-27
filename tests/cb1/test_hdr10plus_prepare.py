"""DV HDR10+ reconstructs once; Basic mapping must not enter that path."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class HDR10PlusPrepareTests(unittest.TestCase):
    def test_pending_analysis_retains_picture_with_async_disabled(self):
        source=(TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        start=source.index('  const bool renderPending = status',source.index('// A paused final surface'))
        code=source[start:source.index('  if (std::getenv',start)]
        program=r'''
#include <cassert>
#include "dvbridge_policy.h"
struct CDVBridgeGLES {enum class FrameStatus{Pending,Busy,Ready,Failed};};
struct Metadata{bool authored=true;bool Data()const{return authored;}};
struct Context{bool AsyncPreparation(int){return false;}};
bool holds(dvbridge_mode mode,CDVBridgeGLES::FrameStatus status,bool authored=true){
 Metadata metadata{authored};struct{dvbridge_mode mode;}policy{mode};
 const bool allowAsync=false,m_dvFrame=false;bool m_cb1FramePending=false;
 Context ctx;auto*m_dvContext=&ctx;struct{struct{int stream;}binding;}layer{};
 BODY
 return m_cb1FramePending;
}
int main(){
 for(auto state:{CDVBridgeGLES::FrameStatus::Pending,CDVBridgeGLES::FrameStatus::Busy}){
  assert(holds(DVBRIDGE_MODE_HDR10PLUS,state));
  assert(holds(DVBRIDGE_MODE_ENHANCED_DV,state));
  assert(!holds(DVBRIDGE_MODE_HDR10_BASIC,state));
  assert(!holds(DVBRIDGE_MODE_HDR10PLUS,state,false));
 }
 assert(!holds(DVBRIDGE_MODE_HDR10PLUS,CDVBridgeGLES::FrameStatus::Failed));
 assert(!holds(DVBRIDGE_MODE_HDR10PLUS,CDVBridgeGLES::FrameStatus::Ready));
}
'''.replace('BODY',code).replace('#include <cassert>','#include <cassert>\n#include <initializer_list>')
        repo=Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);path=root/'test.cpp';binary=root/'test'
            path.write_text(program)
            built=subprocess.run(['c++','-std=c++20','-I'+str(repo/'CB1/src'),str(path),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_metadata_is_ready_only_for_the_current_completed_analysis(self):
        source=(TREE/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        def method(name):
            signature='CDVBridgeGLES::FrameStatus CDVBridgeGLES::'+name+'()'
            return body(source,signature) if signature in source else '{return FrameStatus::Failed;}'
        program=r'''
#include <cassert>
#include <optional>
#include <cstdint>
#include <cstddef>
struct Identity {unsigned stream=3,picture=7,revision=9;};
struct pl_rect2d {int x0,y0,x1,y1;};
struct Texture {struct {int w=3840,h=2160;}params;};
Texture texture;Texture* dvbridge_render_texture(int){return &texture;}
struct Metadata {const void* Data()const{return this;}size_t Size()const{return sizeof(*this);}};
struct AVDynamicHDRPlus {int value{};};
struct cb1_hdr10plus_statistics {int value{};};
struct cb1_dv_hdr10plus_report {int coverage=2,reason=0;bool l3_used=true;};
enum {CB1_HDR10PLUS_ANALYSIS_INVALID,CB1_HDR10PLUS_ANALYSIS_PENDING,
 CB1_HDR10PLUS_ANALYSIS_READY,CB1_HDR10PLUS_ANALYSIS_BUSY,CB1_HDR10PLUS_OK};
static int state=CB1_HDR10PLUS_ANALYSIS_PENDING;
static Identity submitted;static pl_rect2d measured;static int buildCount;
int* cb1_hdr10plus_analysis_create(int,int){static int ctx;return &ctx;}
bool dvbridge_frame_area(unsigned* margins,const void*,size_t,int){
 margins[0]=2;margins[1]=4;margins[2]=6;margins[3]=8;return true;}
int cb1_hdr10plus_analysis_submit(int*,Texture*,pl_rect2d area,Identity id){
 measured=area;submitted=id;return state;}
int cb1_hdr10plus_analysis_poll(int*,Identity id,cb1_hdr10plus_statistics* result){
 if(id.stream!=submitted.stream || id.picture!=submitted.picture || id.revision!=submitted.revision)
   return CB1_HDR10PLUS_ANALYSIS_INVALID;
 result->value=123;return state;}
bool cb1_dv_hdr10plus_metadata(AVDynamicHDRPlus* out,cb1_dv_hdr10plus_report*,const void*,size_t,
 const cb1_hdr10plus_statistics* stats){out->value=stats->value;++buildCount;return true;}
struct CDVBridgeGLES {
 enum class FrameStatus{Failed,Pending,Busy,Ready};
 int* m_hdr10plusAnalysis{};int m_log{},m_renderer=1,m_sourceGeometry{};
 struct GL{int gpu;}gl;GL* m_gl=&gl;
 Metadata m_pendingMetadata;Identity m_pendingIdentity;
 bool m_prepared{},m_pending=true;int audits{},failures{};
 Identity m_failedIdentity;
 std::optional<AVDynamicHDRPlus>m_hdr10plusMetadata;
 cb1_dv_hdr10plus_report m_hdr10plusReport;
 bool Failure(const char*){++failures;return false;}
 void Cancel(){m_prepared=m_pending=false;m_hdr10plusMetadata.reset();}
 void PreparedAudit(){++audits;}
 FrameStatus BeginHDR10Plus() BEGIN
 FrameStatus PollHDR10Plus() POLL
};
int main(){
 CDVBridgeGLES r;
 assert(r.BeginHDR10Plus()==CDVBridgeGLES::FrameStatus::Pending);
 assert(measured.x0==2 && measured.x1==3836 && measured.y0==6 && measured.y1==2152);
 assert(!r.m_prepared && !r.m_hdr10plusMetadata);
 assert(r.PollHDR10Plus()==CDVBridgeGLES::FrameStatus::Pending && buildCount==0);
 state=CB1_HDR10PLUS_ANALYSIS_READY;
 assert(r.PollHDR10Plus()==CDVBridgeGLES::FrameStatus::Ready);
 assert(r.m_prepared && r.m_hdr10plusMetadata->value==123 && buildCount==1 && r.audits==1);
 ++r.m_pendingIdentity.picture;r.m_prepared=false;
 assert(r.PollHDR10Plus()==CDVBridgeGLES::FrameStatus::Failed);
 assert(!r.m_hdr10plusMetadata && !r.m_pending && buildCount==1);
 state=CB1_HDR10PLUS_ANALYSIS_BUSY;
 assert(r.BeginHDR10Plus()==CDVBridgeGLES::FrameStatus::Busy);
 assert(!r.m_prepared && !r.m_hdr10plusMetadata);
 state=CB1_HDR10PLUS_ANALYSIS_INVALID;r.m_pending=true;
 assert(r.BeginHDR10Plus()==CDVBridgeGLES::FrameStatus::Failed);
 assert(!r.m_pending && r.failures==2 && r.m_failedIdentity.picture==r.m_pendingIdentity.picture);
}
'''.replace('BEGIN',method('BeginHDR10Plus')).replace('POLL',method('PollHDR10Plus'))
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);code=root/'check.cpp';binary=root/'check'
            code.write_text(program)
            built=subprocess.run(['c++','-std=c++20','-fsanitize=address,undefined',str(code),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_reconstruction_does_not_apply_basic_mapping_or_direct_pack(self):
        source=(TREE/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        implementation=body(source,'bool CDVBridgeGLES::Prepare(')
        program=r'''
#include <cassert>
#include <optional>
#include <limits>
#include <cstdint>
#include <cstddef>
#include "dvbridge_policy.h"
enum {DVBRIDGE_Y416,PL_CHROMA_UNKNOWN,PL_CHROMA_LEFT,PL_CHROMA_TOP_LEFT,AVCHROMA_LOC_UNSPECIFIED,LOGINFO};
enum {CB1_MASTER_READY,CB1_MASTER_INVALID,CB1_MASTER_UNSUPPORTED,CB1_MASTER_GPU_UNAVAILABLE};
struct AVDOVIMetadata {int num_ext_blocks{};};
struct Ext {int level{};struct {int min_pq{},avg_pq{},max_pq{1000};}l1;};
const Ext* av_dovi_find_level(const AVDOVIMetadata*,int){static Ext e;return &e;}
const Ext* av_dovi_get_ext(const AVDOVIMetadata*,int){static Ext e;return &e;}
struct CDVMetadataBuffer {AVDOVIMetadata value;const void* Data()const{return &value;}size_t Size()const{return sizeof(value);}};
struct dvbridge_geometry {int x{},y{},width=3840,height=2160,target_width=3840,target_height=2160;};
struct dvbridge_gl_frame {struct Frame {Frame* enhancement_layer{};}frame;};
struct dvbridge_color {struct {bool nlq_active=true;}dovi;};
struct GL {int gpu;};
static int rawCalls,basicCalls,directCalls,standardCalls,masterCalls;
template<class... A>bool dvbridge_gl_frame_import(A...){return true;}
template<class... A>bool ImportLayer(A... a){return dvbridge_gl_frame_import(a...);}
template<class... A>void dvbridge_gl_frame_release(A...){}
template<class... A>void dvbridge_gl_frame_set_chroma(A...){}
template<class... A>auto dvbridge_map_chroma(A...){return PL_CHROMA_LEFT;}
template<class... A>bool dvbridge_map_color(A...){return true;}
template<class... A>void dvbridge_renderer_set_optimized_dv(A...){}
template<class... A>void dvbridge_renderer_set_processing_optimizations(A...){}
template<class... A>void dvbridge_renderer_set_overlay_visible(A...){}
template<class... A>void dvbridge_renderer_reset(A...){}
template<class... A>bool dvbridge_render_hdr10_direct(A...){++directCalls;return true;}
template<class... A>bool dvbridge_render_hdr10_rgb(A...){++basicCalls;return true;}
template<class... A>bool dvbridge_render_rgb(A...){++rawCalls;return true;}
template<class... A>bool dvbridge_render_packed(A...){++standardCalls;return true;}
template<class... A>bool dvbridge_render_packed_overlay(A...){++standardCalls;return true;}
// The production code stores this concrete function in a local variable.
int dvbridge_render_master_reference(int,dvbridge_gl_frame::Frame*,const void*,size_t,
    double,double,dvbridge_geometry,int,bool,const int*){++masterCalls;return CB1_MASTER_READY;}
int dvbridge_render_master_reference_ipt(int,dvbridge_gl_frame::Frame*,const void*,size_t,
    double,double,dvbridge_geometry,int,bool,const int*){assert(false);return CB1_MASTER_READY;}
namespace DVBRIDGE {
bool DiagnosticsEnabled(){return false;}
uint64_t DiagnosticNowMs(){return 0;}
template<class... A>void DiagnosticLog(A...){}
struct StreamTelemetry {template<class... A>static void Metadata(A...) {}};
}
struct CDVPlaybackInfo {enum {HDR10=1,HDMI=2,FEL=4,CM4=8};};
struct CDVBridgeGLES {
 struct Layer {int layout{},width=32,height=32,planes[3]{},chromaLocation=AVCHROMA_LOC_UNSPECIFIED;
 double pts{};struct {int profile=7;}sourceInfo;};
 struct Pref {bool optimizedDV{},processingOptimizations{},masterIPT{};}m_requested;
 bool m_prepared{},m_packed{},m_direct{},m_hdr10=true,m_overlayVisible{},m_directUsable=true,
 m_nativeOverlayEnabled{},m_nativeOverlayPrimed{},m_asyncEligible=true,m_live=true,m_firstFrame=true;
 int m_renderer=1,m_scanout=1,m_nativeOverlay{};GL gl{};GL* m_gl=&gl;
 std::optional<int>m_hdr10Session=1;bool m_hdr10Limited{};unsigned m_outputBits=10;
 dvbridge_mode m_effectiveMode=DVBRIDGE_MODE_HDR10PLUS;
 unsigned m_pendingInfo{},m_pendingHDR10Fallback{};CDVMetadataBuffer m_pendingMetadata;
 uint64_t m_prepares{},m_directFrames{},m_lastSummary{};
 bool Failure(const char*){return false;}
 bool Prepare(const Layer& base,const Layer* enhancement,const CDVMetadataBuffer& metadata,
     dvbridge_geometry geometry,bool allowPacked) BODY
};
int main(){
 CDVBridgeGLES r;CDVBridgeGLES::Layer bl,el;CDVMetadataBuffer metadata;
 for(bool packed:{false,true}){
  rawCalls=basicCalls=directCalls=0;
  assert(r.Prepare(bl,&el,metadata,{},packed));
  assert(rawCalls==1 && basicCalls==0 && directCalls==0);
  assert((r.m_pendingInfo&CDVPlaybackInfo::FEL)!=0);
 }
 r.m_effectiveMode=DVBRIDGE_MODE_HDR10_BASIC;
 rawCalls=basicCalls=directCalls=0;
 assert(r.Prepare(bl,nullptr,metadata,{},false));assert(basicCalls==1 && !rawCalls);
 assert(r.Prepare(bl,nullptr,metadata,{},true));assert(directCalls==1);
}
'''.replace('BODY',implementation)
        repo=Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);code=root/'check.cpp';binary=root/'check'
            code.write_text(program)
            built=subprocess.run(['c++','-std=c++20','-fsanitize=address,undefined',
                '-I'+str(repo/'CB1/src'),str(code),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':
    unittest.main()
