/* Actual post-stack class/method bodies are inserted by the unittest. Only
 * external GPU, retirement and publication boundaries are deterministic. */
#include <algorithm>
#include <array>
#include <atomic>
#include <bit>
#include <cassert>
#include <cmath>
#include <memory>
#include <mutex>
#include <optional>
#include <span>
#include <tuple>
#include <vector>
#include <iostream>
#include <deque>
#include <GLES3/gl3.h>
#define HAVE_DVBRIDGE
extern "C" {
#include "dvbridge_render.h"
#include "dvbridge_gl_frame.h"
#include "dvbridge_gl_pack.h"
#include "dvbridge_dmabuf.h"
#include "dvbridge_fel_vpp.h"
#include "cb1_dv_hdr10plus.h"
#include "cb1_hdr10plus_dovi.h"
#include "cb1_circuit.h"
}
#include "cores/VideoPlayer/DVDCodecs/Video/DVMetadataBuffer.h"
#include "cores/VideoPlayer/DVDCodecs/Video/DVPlaybackInfo.h"
#include "utils/DVBridgeDiagnosticState.h"
#include "utils/Crc32.h"
#include "cores/VideoProcessingInfo.h"
#include "cores/VideoSourceSideData.h"
namespace KODI::RENDERING::CAPTURE {struct ReadbackBuffer;}
struct CRect {};
enum ESCALINGMETHOD {VS_SCALINGMETHOD_MAX,VS_SCALINGMETHOD_LINEAR};
constexpr int LOGINFO=1;
@SETTINGS@
namespace DVBRIDGE {
template<class...T>bool DiagnosticLog(T...){return false;}
template<class...T>void ObserveDiagnostic(T...){}
void DiagnosticReserveProgress(){}
void DiagnosticStage(const char*){}
struct StreamSnapshot @SNAPSHOT@;
struct StreamTelemetry {
 inline static StreamSnapshot accepted{};inline static unsigned publications=0;
 static StreamSnapshot Read(){return accepted;}
 static void NativePresented(const SourceInfo&,const CDVMetadataBuffer&,const StreamSnapshot::Output& output){accepted.output=output;++publications;}
 static void NativeRequest(SourceBinding,int,int,SourceBinding){}
 static void NativeStage(SourceBinding,const char*){}
 template<class...T>static void PublishNativePending(T...){}
 template<class...T>static void PublishNativeInfo(T...){}
};
}
class VideoSourceSideData;
@CLASS@
namespace {
unsigned directCalls=0,stagedCalls=0,resolveCalls=0,releaseCalls=0,commitCalls=0;
bool queryOK=true,drawOK=true,importOK=true,commitOK=true;
int retired=DVBRIDGE_DV_IDLE;bool fenceOK=true;unsigned fences=0;
dvbridge_hdr10_policy_output pending{},accepted{};
pl_opengl_t gl{};
pl_chroma_location SourceChroma(AVChromaLocation source,unsigned profile) @CHROMA@
bool ImportDVLayer(dvbridge_gl_frame* frame,pl_gpu gpu,const CDVBridgeGLES::Layer& layer,unsigned*hdrInputUsed=nullptr) @IMPORT@
}
struct CDVBridgeGLES::Context::State {
 struct SourceUse {GLsync fence{};std::vector<std::shared_ptr<void>>leases;};
 std::deque<SourceUse>inFlight;std::vector<std::shared_ptr<void>>foreign;
 bool quarantined=false,attached=true;dvbridge_retirement_owner*owner=nullptr;
};
extern "C" {
GLsync glFenceSync(GLenum,GLbitfield){++fences;return fenceOK?reinterpret_cast<GLsync>(1):nullptr;}
void glFlush(){}
GLenum glGetError(){return GL_NO_ERROR;}
void glDeleteSync(GLsync){}
GLenum glClientWaitSync(GLsync,GLbitfield,GLuint64){return retired==DVBRIDGE_DV_BUSY?GL_TIMEOUT_EXPIRED:retired==DVBRIDGE_DV_FAILED?GL_WAIT_FAILED:GL_ALREADY_SIGNALED;}
dvbridge_dv_policy_status dvbridge_retirement_owner_poll(dvbridge_retirement_owner*){return static_cast<dvbridge_dv_policy_status>(retired);}
}
CDVBridgeGLES::Context::Context():m_state(std::make_unique<State>()){}
CDVBridgeGLES::Context::~Context()=default;
bool CDVBridgeGLES::Context::Quarantined()const{return m_state->quarantined;}
bool CDVBridgeGLES::Context::AsyncPreparation(uint64_t){return true;}
@CONTEXT@
void CDVBridgeGLES::Context::SetSpatialMethod(ESCALINGMETHOD,bool){}
CDVBridgeGLES::~CDVBridgeGLES()=default;
bool CDVBridgeGLES::Failure(const char*){return false;}
void CDVBridgeGLES::BeginDiagnosticStream(uint64_t){}
void CDVBridgeGLES::PreparedAudit(){}
void CDVBridgeGLES::CountPresentation(bool){}
void CDVBridgeGLES::ReportHDR10Plus(){}
bool CDVBridgeGLES::Presented(bool){return false;}
bool CDVBridgeGLES::PollReady(){return m_prepared;}
bool CDVBridgeGLES::Prepare(const Layer&,const Layer*,const CDVMetadataBuffer&,dvbridge_geometry,bool){return false;}
CDVBridgeGLES::FrameStatus CDVBridgeGLES::BeginHDR10Plus(){return FrameStatus::Failed;}
void CDVBridgeGLES::CaptureMetadata(const CDVMetadataBuffer&,bool){m_pendingInfo=CDVPlaybackInfo::SDR;}
DVBRIDGE::SourceBinding CDVBridgeGLES::SelectionIdentity(DVBRIDGE::SourceBinding b,const DVBRIDGE::OutputPreferences&,dvbridge_mode)const{return b;}
void CDVBridgeGLES::Cancel(){m_pending=m_prepared=m_packed=false;m_submission={};}
const dvbridge_hdr10_policy_output*CDVBridgeGLES::HDR10Output()const{return &pending;}
@METHODS@
extern "C" {
void dvbridge_renderer_set_l2_trims_disabled(dvbridge_renderer*,bool){}
void dvbridge_renderer_set_cmv40(dvbridge_renderer*,const cb1_cmv40_options*){}
void dvbridge_renderer_set_optimized_dv(dvbridge_renderer*,bool){}
void dvbridge_renderer_set_fel_filter(dvbridge_renderer*,dvbridge_fel_filter){}
void dvbridge_renderer_set_processing_optimizations(dvbridge_renderer*,bool){}
void dvbridge_renderer_set_overlay_visible(dvbridge_renderer*,bool){}
bool dvbridge_render_sdr_policy_direct_eligible(const dvbridge_renderer*,const dvbridge_policy*,const dvbridge_identity*,const pl_frame*,const void*,size_t,double,double,dvbridge_geometry,pl_tex,unsigned){return queryOK;}
bool dvbridge_render_hdr10_policy_direct(dvbridge_renderer*,const dvbridge_policy* p,const dvbridge_identity*id,const pl_frame*,const void*,size_t,double,double,dvbridge_geometry,pl_tex target,bool,bool,unsigned){++directCalls;pending.identity=*id;pending.policy=*p;pending.final_target=target;return drawOK;}
bool dvbridge_render_sdr_policy_rgb(dvbridge_renderer*,const dvbridge_policy*p,const dvbridge_identity*id,const pl_frame*,const void*,size_t,double,double,dvbridge_geometry){++stagedCalls;pending.identity=*id;pending.policy=*p;return drawOK;}
bool dvbridge_render_hdr10_policy_rgb(dvbridge_renderer*r,const dvbridge_policy*p,const dvbridge_identity*id,const pl_frame*f,const void*m,size_t n,double a,double b,dvbridge_geometry g){return dvbridge_render_sdr_policy_rgb(r,p,id,f,m,n,a,b,g);}
bool dvbridge_render_sdr_policy_resolve(dvbridge_renderer*,pl_tex t,bool,bool,unsigned){++resolveCalls;pending.final_target=t;return drawOK;}
bool dvbridge_render_hdr10_policy_resolve(dvbridge_renderer*r,pl_tex t,bool a,bool b,unsigned c){return dvbridge_render_sdr_policy_resolve(r,t,a,b,c);}
bool dvbridge_render_hdr10(dvbridge_renderer*,pl_tex,bool,bool,unsigned){return false;}
bool dvbridge_render_policy_commit(dvbridge_renderer*,const dvbridge_identity*id,pl_tex target){++commitCalls;if(!commitOK||!dvbridge_identity_equal(id,&pending.identity)||target!=pending.final_target)return false;accepted=pending;return true;}
bool dvbridge_render_policy_committed(const dvbridge_renderer*,dvbridge_hdr10_policy_output*out){*out=accepted;return true;}
void dvbridge_render_policy_cancel(dvbridge_renderer*){}
void dvbridge_gl_frame_release(dvbridge_gl_frame*){++releaseCalls;}
bool dvbridge_gl_frame_import(dvbridge_gl_frame*out,pl_gpu,dvbridge_gl_layout,int,int,const dvbridge_gl_plane[3]){out->frame.repr.alpha=PL_ALPHA_UNKNOWN;return importOK;}
void dvbridge_gl_frame_set_chroma(dvbridge_gl_frame*,pl_chroma_location){}
pl_chroma_location dvbridge_map_chroma(AVChromaLocation){return PL_CHROMA_LEFT;}
bool dvbridge_map_color(dvbridge_color*,const void*,size_t,bool){return false;}
dvbridge_dv_policy_status dvbridge_render_dv_policy_prepare_packed(dvbridge_renderer*,const dvbridge_policy*,const dvbridge_identity*,const pl_frame*,const void*,size_t,double,double,dvbridge_geometry,pl_tex,bool,const dvbridge_native_overlay*){return DVBRIDGE_DV_UNSUPPORTED;}
dvbridge_dv_policy_status dvbridge_render_dv_policy_prepare(dvbridge_renderer*,const dvbridge_policy*,const dvbridge_identity*,const pl_frame*,const void*,size_t,double,double,dvbridge_geometry){return DVBRIDGE_DV_UNSUPPORTED;}
dvbridge_dv_policy_status dvbridge_render_dv_policy_poll(dvbridge_renderer*){return static_cast<dvbridge_dv_policy_status>(retired);}
dvbridge_dv_policy_status dvbridge_render_dv_policy_advance(dvbridge_renderer*){return static_cast<dvbridge_dv_policy_status>(retired);}
bool dvbridge_render_dv_policy_update_overlay(dvbridge_renderer*,const dvbridge_native_overlay*,bool){return false;}
bool dvbridge_render_dv_policy_commit(dvbridge_renderer*,const dvbridge_identity*,pl_tex,uint64_t){return false;}
bool dvbridge_render_dv_policy_committed(const dvbridge_renderer*,dvbridge_dv_policy_snapshot*){return false;}
bool dvbridge_render_commit(dvbridge_renderer*){return false;}
}
static void setup(CDVBridgeGLES& r){r.m_context=std::make_shared<CDVBridgeGLES::Context>();r.m_gl=&gl;r.m_renderer=reinterpret_cast<dvbridge_renderer*>(1);r.m_scanout=reinterpret_cast<pl_tex>(2);r.m_hdr10=true;r.m_requested.output=DVBRIDGE::OutputMode::SDR;}
@PROVENANCE@
int main(){
 setenv("DVBRIDGE_DIAGNOSTICS","0",1);
 CDVBridgeGLES r;setup(r);CDVBridgeGLES::Layer base{};base.binding={1,1,1};base.pts=1;base.lease=std::make_shared<int>(1);
 base.sourceInfo.profile=7;base.sourceInfo.rpu=true;base.sourceInfo.informationGeneration=9;
 uint8_t payload=1;CDVMetadataBuffer metadata;assert(metadata.Assign(&payload,1,base.binding));
 dvbridge_geometry geometry{8,8,0,0,8,8,8,8};DVBRIDGE::OutputPreferences prefs;prefs.output=DVBRIDGE::OutputMode::SDR;prefs.revision=3;
 dvbridge_policy policy=prefs.Policy();
 auto prepare=[&](bool packed=true){return r.PrepareFrame(base,nullptr,metadata,geometry,prefs,packed,&policy,false);};
 assert(prepare()==CDVBridgeGLES::FrameStatus::Ready&&directCalls==1&&!stagedCalls&&!resolveCalls&&fences==1&&releaseCalls==2);
 assert(!DVBRIDGE::StreamTelemetry::publications&&r.ResolveHDR10(false));
 auto submission=r.m_submission;auto stale=submission;++stale.sequence;assert(!r.Presented(true,stale)&&!commitCalls);
 stale=submission;stale.target=reinterpret_cast<pl_tex>(3);assert(!r.Presented(true,stale)&&!commitCalls);
 stale=submission;++stale.identity.revision;assert(!r.Presented(true,stale)&&!commitCalls);
 stale=submission;++stale.identity.stream;assert(!r.Presented(true,stale)&&!commitCalls);
 stale=submission;++stale.identity.picture;assert(!r.Presented(true,stale)&&!commitCalls);
 stale=submission;++stale.resolveSerial;assert(!r.Presented(true,stale)&&!commitCalls);
 stale=submission;stale.asyncEligible=!stale.asyncEligible;assert(!r.Presented(true,stale)&&!commitCalls);
 assert(r.Presented(true,submission)&&commitCalls==1&&DVBRIDGE::StreamTelemetry::publications==1);
 auto prior=r.m_committedBinding;assert(DVBRIDGE::StreamTelemetry::accepted.output.sdrHDRInputUsed==0);
 unsigned framebuffer,bits; // Paused movie refresh after blending final SDR GUI.
 ++base.binding.picture;assert(metadata.Assign(&payload,1,base.binding));assert(prepare()==CDVBridgeGLES::FrameStatus::Ready);
 assert(r.GetHDR10OutputTarget(framebuffer,bits)&&bits==8&&r.ResolveHDR10(false));assert(r.Presented(true,r.m_submission));
 const auto draws=directCalls;assert(prepare()==CDVBridgeGLES::FrameStatus::Ready&&directCalls==draws+1);
 r.Cancel();
 // Settings, seek and source successors invalidate an already resolved callback.
 for(unsigned changed=0;changed<3;changed++){
  ++base.binding.picture;assert(metadata.Assign(&payload,1,base.binding));
  assert(prepare()==CDVBridgeGLES::FrameStatus::Ready&&r.ResolveHDR10(false));auto old=r.m_submission;
  if(changed==0)++prefs.revision;
  if(changed==1)++base.binding.revision;
  if(changed==2){++base.binding.stream;++base.binding.revision;++base.sourceInfo.informationGeneration;}
  assert(metadata.Assign(&payload,1,base.binding));
  assert(prepare()==CDVBridgeGLES::FrameStatus::Ready&&r.ResolveHDR10(false));
  auto publication=DVBRIDGE::StreamTelemetry::publications;
  assert(!r.Presented(true,old)&&DVBRIDGE::StreamTelemetry::publications==publication);
  assert(r.Presented(true,r.m_submission)&&r.m_committedBinding==base.binding);
 }
 auto publication=DVBRIDGE::StreamTelemetry::publications;prior=r.m_committedBinding;
 ++base.binding.picture;assert(metadata.Assign(&payload,1,base.binding));
 assert(prepare()==CDVBridgeGLES::FrameStatus::Ready&&r.ResolveHDR10(false));commitOK=false;
 assert(!r.Presented(true,r.m_submission)&&r.m_committedBinding==prior&&DVBRIDGE::StreamTelemetry::publications==publication);commitOK=true;
 ++base.binding.picture;assert(metadata.Assign(&payload,1,base.binding));
 assert(prepare()==CDVBridgeGLES::FrameStatus::Ready&&r.ResolveHDR10(false));
 assert(!r.Presented(false,r.m_submission)&&r.m_committedBinding==prior&&DVBRIDGE::StreamTelemetry::publications==publication);
 auto beforeAssociation=directCalls;++base.binding.revision;
 assert(prepare()==CDVBridgeGLES::FrameStatus::Failed&&directCalls==beforeAssociation); // Stale bound metadata.
 assert(metadata.Assign(&payload,1,base.binding));
 // Raw HDR+ captures the actual importer mask/values, including source/settings epochs.
 base.sourceInfo={};base.sourceInfo.informationGeneration=10;metadata.Reset();++base.binding.picture;++prefs.revision;
 assert(prepare()==CDVBridgeGLES::FrameStatus::Ready&&r.ResolveHDR10(false));assert(r.Presented(true,r.m_submission));
 assert(DVBRIDGE::StreamTelemetry::accepted.output.sdrHDRInputUsed==0);
 prior=r.m_committedBinding;const auto pubs=DVBRIDGE::StreamTelemetry::publications;
 ++base.binding.picture;drawOK=false;const auto stages=stagedCalls,resolves=resolveCalls,oldFences=fences,oldReleases=releaseCalls;
 assert(prepare()==CDVBridgeGLES::FrameStatus::Failed&&stagedCalls==stages&&resolveCalls==resolves&&fences==oldFences+1&&releaseCalls==oldReleases+2);
 assert(r.m_committedBinding==prior&&DVBRIDGE::StreamTelemetry::publications==pubs);
 assert(base.lease.use_count()==2);assert(r.m_context->Poll()==DVBRIDGE_DV_IDLE&&base.lease.use_count()==1);
 drawOK=true;++base.binding.picture;fenceOK=false;assert(prepare()==CDVBridgeGLES::FrameStatus::Failed&&!r.m_pending&&r.m_context->Quarantined());fenceOK=true;
 // Each independent boundary failure starts with a fresh deterministic context.
 r.m_context=std::make_shared<CDVBridgeGLES::Context>();
 ++base.binding.picture;importOK=false;assert(prepare()==CDVBridgeGLES::FrameStatus::Failed);importOK=true;
 assert(r.m_context->FenceLastUse());
 retired=DVBRIDGE_DV_BUSY;++base.binding.picture;auto d=directCalls;assert(prepare()==CDVBridgeGLES::FrameStatus::Busy&&directCalls==d);retired=DVBRIDGE_DV_IDLE;
 queryOK=false;assert(prepare()==CDVBridgeGLES::FrameStatus::Ready&&stagedCalls==stages+1&&resolveCalls==resolves+1);r.Cancel();queryOK=true;
 assert(r.m_directUsable); // Known pre-draw ineligibility is local to this picture.
 assert(r.m_context->Poll()==DVBRIDGE_DV_IDLE&&base.lease.use_count()==1);
 provenance();
 raw_sources();
 std::cout<<"COMPLETE actual PrepareFrame/ResolveHDR10/Presented owners\n";
}
