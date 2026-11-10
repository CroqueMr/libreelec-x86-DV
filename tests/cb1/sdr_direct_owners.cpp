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
#include <fmt/ranges.h>
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
inline bool auditAdmit=true;inline std::vector<std::string>auditLines;
template<class...T>bool DiagnosticLog(int,fmt::format_string<T...>f,T&&...a){
 if(!auditAdmit)return false;
 auto message=fmt::format(f,std::forward<T>(a)...);
 if(message.starts_with("DVBridge policy prepared:"))auditLines.push_back(message);
 return true;
}
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
unsigned directCalls=0,stagedCalls=0,resolveCalls=0,releaseCalls=0,commitCalls=0,queryCalls=0;
bool queryOK=true,drawOK=true,importOK=true,commitOK=true;
int retired=DVBRIDGE_DV_IDLE;bool fenceOK=true;unsigned fences=0;
dvbridge_hdr10_policy_output pending{},accepted{};
pl_opengl_t gl{};
pl_fmt_t sourceFormats[2]{},targetFormat{};
pl_tex_t sourceTextures[2]{},targetTexture{};
pl_chroma_location SourceChroma(AVChromaLocation source,unsigned profile) @CHROMA@
bool ImportDVLayer(dvbridge_gl_frame* frame,pl_gpu gpu,const CDVBridgeGLES::Layer& layer,unsigned*hdrInputUsed=nullptr) @IMPORT@
@SDR_AUDIT@
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
bool dvbridge_render_sdr_policy_direct_eligible(const dvbridge_renderer*,const dvbridge_policy*,const dvbridge_identity*,const pl_frame*,const void*,size_t,double,double,dvbridge_geometry,pl_tex,unsigned){++queryCalls;return queryOK;}
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
bool dvbridge_gl_frame_import(dvbridge_gl_frame*out,pl_gpu,dvbridge_gl_layout,int,int,const dvbridge_gl_plane[3]){
 out->frame.repr.alpha=PL_ALPHA_UNKNOWN;out->frame.repr.bits={16,10,6};
 out->frame.num_planes=2;out->frame.crop={0,0,8,8};
 for(int p=0;p<2;p++){
  sourceFormats[p].type=PL_FMT_UNORM;sourceFormats[p].num_components=p+1;
  sourceFormats[p].component_depth[0]=sourceFormats[p].component_depth[1]=16;
  sourceTextures[p].params.w=p?4:8;sourceTextures[p].params.h=p?4:8;sourceTextures[p].params.format=&sourceFormats[p];
  out->frame.planes[p].texture=&sourceTextures[p];out->frame.planes[p].components=p+1;
  out->frame.planes[p].component_mapping[0]=p;if(p)out->frame.planes[p].component_mapping[1]=2;
 }return importOK;
}
bool dvbridge_frame_area(unsigned margins[4],const void*,size_t,dvbridge_geometry){margins[0]=margins[1]=0;margins[2]=margins[3]=42;return true;}
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
static void setup(CDVBridgeGLES& r){
 targetFormat.type=PL_FMT_UNORM;targetFormat.num_components=4;
 for(unsigned i=0;i<4;i++)targetFormat.component_depth[i]=8;
 targetTexture.params.w=targetTexture.params.h=8;targetTexture.params.format=&targetFormat;
 r.m_context=std::make_shared<CDVBridgeGLES::Context>();r.m_gl=&gl;r.m_renderer=reinterpret_cast<dvbridge_renderer*>(1);r.m_scanout=&targetTexture;r.m_hdr10=true;r.m_requested.output=DVBRIDGE::OutputMode::SDR;
}
@PROVENANCE@
static void audit_cases(){
 using namespace DVBRIDGE;testEnabled=true;
 for(int scenario=0;scenario<5;scenario++){
  CDVBridgeGLES r;setup(r);CDVBridgeGLES::Layer base{};base.binding={90,1,1};base.pts=1;base.lease=std::make_shared<int>(1);
  CDVMetadataBuffer metadata;uint8_t byte=1;
  if(scenario>=3){assert(metadata.Assign(&byte,1,base.binding));}
  if(scenario==4){base.sourceInfo.profile=7;base.sourceInfo.rpu=true;}
  OutputPreferences prefs;prefs.output=OutputMode::SDR;prefs.revision=100;auto policy=prefs.Policy();
  queryOK=scenario!=2&&scenario!=4;auto queries=queryCalls,direct=directCalls,staged=stagedCalls;auto logs=auditLines.size();
  const bool allow=scenario!=1;
  assert(r.PrepareFrame(base,nullptr,metadata,{8,8,0,0,8,8,8,8},prefs,allow,&policy,false)==CDVBridgeGLES::FrameStatus::Ready);
  const bool evaluated=scenario!=1&&scenario!=3;assert(queryCalls==queries+evaluated);
  assert(directCalls==direct+(scenario==0)&&stagedCalls==staged+(scenario!=0));
  assert(auditLines.size()==logs+1&&r.m_auditPreparedSerial==r.m_auditSerial);
  const auto&line=auditLines.back();assert(line.size()<=640);
  assert(line.find(scenario==0?"sdr=2,1,1,1,1,1,1":scenario==1?"sdr=2,0,1,1,-1,0,-1":scenario==2?"sdr=2,1,1,1,0,0,-1":scenario==3?"sdr=0,1,1,1,-1,0,-1":"sdr=1,1,1,1,0,0,-1")!=std::string::npos);
  assert(line.find(" t=8,8,")!=std::string::npos&&line.find(" g=8,8,0,0,8,8,8,8")!=std::string::npos);
  assert(line.find(scenario>=3?" l5=0,0,42,42/false":" l5=na/false")!=std::string::npos);
  r.Cancel();++base.binding.picture;if(metadata.Data())assert(metadata.Assign(&byte,1,base.binding));
  assert(r.PrepareFrame(base,nullptr,metadata,{8,8,0,0,8,8,8,8},prefs,allow,&policy,false)==CDVBridgeGLES::FrameStatus::Ready);
  assert(auditLines.size()==logs+1); // Same source/settings epoch never spams.
 }
 // Exercise the real formatter with 4K native two-plane BL/EL and fractional
 // coordinates. It must fit without hiding a float mismatch or a source alias.
 CDVBridgeGLES formatted;setup(formatted);dvbridge_gl_frame imported{};
 assert(dvbridge_gl_frame_import(&imported,nullptr,DVBRIDGE_P010,8,8,nullptr));
 auto frame=imported.frame;frame.crop={0.125f,0,std::nextafter(3840.0f,INFINITY),2160};
 sourceTextures[0].params.w=3840;sourceTextures[0].params.h=2160;
 sourceTextures[1].params.w=1920;sourceTextures[1].params.h=1080;
 frame.repr.sys=PL_COLOR_SYSTEM_BT_2020_NC;frame.repr.levels=PL_COLOR_LEVELS_LIMITED;
 frame.color.primaries=PL_COLOR_PRIM_BT_2020;frame.color.transfer=PL_COLOR_TRC_PQ;
 frame.color.hdr={};frame.color.hdr.min_luma=0.005f;frame.color.hdr.max_luma=1000;
 frame.color.hdr.max_cll=1000;frame.color.hdr.max_pq_y=0.75f;frame.color.hdr.avg_pq_y=0.25f;
 targetTexture.params.w=3840;targetTexture.params.h=2160;targetTexture.params.renderable=true;
 auto el=frame;frame.enhancement_layer=&el;
 dvbridge_geometry fractional{3840,2160,0,0,3840,2160,3840,2160};fractional.placement[0]=0.25f;
 uint8_t payload=1;CDVMetadataBuffer realMetadata;assert(realMetadata.Assign(&payload,1,{1234567890,1234567890,1234567890}));
 auto detail=SDRPreparationAudit(frame,&el,realMetadata,fractional,&targetTexture,8,true,1,1,{1,1,1,1,0,0,-1});
 assert(detail.find("0.125")!=std::string::npos&&detail.find("3840.00024")!=std::string::npos&&detail.find(" p=0.25,")!=std::string::npos);
 assert(detail.find(" v=1,1,1")!=std::string::npos);
 formatted.m_effectiveMode=DVBRIDGE_MODE_SDR;formatted.m_pendingBinding={1234567890,1234567890,1234567890};
 formatted.m_pendingIdentity={1234567890,1234567890,1234567890};formatted.m_auditSerial=1;
 auto formattedCount=auditLines.size();formatted.PreparedAudit(detail);
 assert(auditLines.size()==formattedCount+1&&auditLines.back().size()<=640);
 std::cout<<"SDR_AUDIT native4k_BL_EL_payload="<<auditLines.back().size()<<"\n";
 frame.planes[0].texture=&targetTexture;
 detail=SDRPreparationAudit(frame,&el,realMetadata,fractional,&targetTexture,8,true,NAN,2,{1,1,1,1,0,0,-1});
 assert(detail.find(" a=1,0")!=std::string::npos&&detail.find(" v=0,1,0")!=std::string::npos);
 queryOK=true;testEnabled=false;
 CDVBridgeGLES off;setup(off);CDVBridgeGLES::Layer base{};base.binding={99,1,1};base.pts=1;base.lease=std::make_shared<int>(1);
 OutputPreferences prefs;prefs.output=OutputMode::SDR;prefs.revision=110;auto policy=prefs.Policy();CDVMetadataBuffer none;
 auto logs=auditLines.size();auto queries=queryCalls;assert(off.PrepareFrame(base,nullptr,none,{8,8,0,0,8,8,8,8},prefs,true,&policy,false)==CDVBridgeGLES::FrameStatus::Ready);
 assert(queryCalls==queries+1&&auditLines.size()==logs&&off.m_auditPreparedSerial==0);
 testEnabled=true;auditAdmit=false;CDVBridgeGLES blocked;setup(blocked);
 assert(blocked.PrepareFrame(base,nullptr,none,{8,8,0,0,8,8,8,8},prefs,true,&policy,false)==CDVBridgeGLES::FrameStatus::Ready);
 assert(blocked.m_auditPreparedSerial==0&&auditLines.size()==logs);
 auditAdmit=true;testNow+=30001;blocked.Cancel();++base.binding.picture;
 assert(blocked.PrepareFrame(base,nullptr,none,{8,8,0,0,8,8,8,8},prefs,true,&policy,false)==CDVBridgeGLES::FrameStatus::Ready);
 assert(blocked.m_auditPreparedSerial==blocked.m_auditSerial&&auditLines.size()==logs+1);
 testEnabled=false;std::cout<<"COMPLETE actual SDR audit decisions and query counts\n";
}
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
 audit_cases();
 std::cout<<"COMPLETE actual PrepareFrame/ResolveHDR10/Presented owners\n";
}
