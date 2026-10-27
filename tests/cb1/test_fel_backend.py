"""Execute native FEL import/cache ownership; only GPU/VAAPI boundaries are doubled."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class FELBackendTests(unittest.TestCase):
    def test_filter_changes_preserve_the_matched_residual_and_source_leases(self):
        # Removing the filter cache key or its VPP bypass must fail this test.
        source = (TREE / 'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        method = body(source, 'CDVBridgeGLES::FrameStatus CDVBridgeGLES::PrepareHardwareFrame')
        program = r'''
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <memory>
#include <vector>
struct dvbridge_policy {int mode{};};
namespace DVBRIDGE {
struct SourceBinding {
 uint64_t stream{},picture{},revision{};
 bool Valid() const {return stream && picture && revision;}
 bool operator==(const SourceBinding&) const = default;
};
struct OutputPreferences {int felUpscaling{}; uint64_t revision{1}; dvbridge_policy Policy() const {return {};}
 };
template<class... T> void DiagnosticLog(T&&...) {}
}
constexpr int LOGINFO=0;
enum dvbridge_gl_layout {DVBRIDGE_P010,DVBRIDGE_Y416};
enum pl_chroma_location {PL_CHROMA_UNKNOWN,PL_CHROMA_LEFT,PL_CHROMA_TOP_LEFT};
enum AVChromaLocation {AVCHROMA_LOC_UNSPECIFIED,AVCHROMA_LOC_TOPLEFT};
pl_chroma_location dvbridge_map_chroma(AVChromaLocation p) {return p==AVCHROMA_LOC_TOPLEFT?PL_CHROMA_TOP_LEFT:PL_CHROMA_UNKNOWN;}
pl_chroma_location SourceChroma(AVChromaLocation source,unsigned profile) SOURCECHROMA
constexpr int DVBRIDGE_MODE_STANDARD=0, DVBRIDGE_MODE_MASTER_REFERENCE=5,DVBRIDGE_MODE_ENHANCED_DV=4;
struct dvbridge_gl_plane {unsigned texture{};};
struct AVBufferRef {unsigned char* data{};};
AVBufferRef* av_buffer_ref(AVBufferRef* p) {return new AVBufferRef(*p);}
void av_buffer_unref(AVBufferRef** p) {delete *p; *p=nullptr;}
struct AVHWFramesContext {AVBufferRef* device_ref{};};
struct AVFrame {int width{32},height{24}; int64_t pts{42}; AVBufferRef* hw_frames_ctx{}; unsigned pixels{17}; unsigned char* data[1]{}; AVChromaLocation chroma_location{AVCHROMA_LOC_TOPLEFT};};
struct AVDRMFrameDescriptor {};
struct dvbridge_dmabuf {dvbridge_gl_plane planes[3]{}; dvbridge_gl_layout layout{};
 AVFrame* mapping{}; void* display{}; int width{},height{}; void* images[2]{};};
struct dvbridge_dmabuf_key {uintptr_t surface{},pool{};};
void* eglGetCurrentContext() {return reinterpret_cast<void*>(1);}
bool dvbridge_dmabuf_make_key(dvbridge_dmabuf_key* key,const AVDRMFrameDescriptor* desc,int,int,const void* pool,void*,void*) {
 *key={reinterpret_cast<uintptr_t>(desc),reinterpret_cast<uintptr_t>(pool)}; return true;
}
bool dvbridge_dmabuf_key_equal(const dvbridge_dmabuf_key* a,const dvbridge_dmabuf_key* b) {
 return a->surface==b->surface && a->pool==b->pool;
}
struct dvbridge_geometry {};
struct CDVMetadataBuffer {bool fel{true}; const void* Data() const {return this;} size_t Size() const {return sizeof(*this);}};
struct dvbridge_color {struct {bool nlq_active{};} dovi;};
bool dvbridge_map_color(dvbridge_color* out,const void* data,size_t,bool) {
 out->dovi.nlq_active=static_cast<const CDVMetadataBuffer*>(data)->fel; return true;
}
struct dvbridge_fel_vpp_image {dvbridge_gl_plane plane; int width{},height{};};
struct dvbridge_fel_vpp {dvbridge_fel_vpp_image image; bool leased{};};
enum {DVBRIDGE_VPP_OK,DVBRIDGE_VPP_BUSY,DVBRIDGE_VPP_FAILED};
int importedImages{},scaledImages{},mappedPictures{},createdImages{};
bool importWorks=true,probeWorks=true;
int vppStatus=DVBRIDGE_VPP_OK;
pl_chroma_location lastChroma=PL_CHROMA_UNKNOWN;
dvbridge_fel_vpp* dvbridge_fel_vpp_create(AVBufferRef*,int w,int h) {
 return new dvbridge_fel_vpp{{{},w,h}};
}
bool dvbridge_fel_vpp_destroy(dvbridge_fel_vpp** vpp) {assert(!(*vpp)->leased); delete *vpp; *vpp=nullptr; return true;}
int dvbridge_fel_vpp_acquire(dvbridge_fel_vpp* vpp,const AVFrame* source,const dvbridge_fel_vpp_image** out) {
 if(vppStatus!=DVBRIDGE_VPP_OK) return vppStatus;
 assert(!vpp->leased); vpp->leased=true;
 vpp->image.plane.texture=source->pixels; *out=&vpp->image; ++scaledImages; return DVBRIDGE_VPP_OK;
}
int dvbridge_fel_vpp_acquire_chroma(dvbridge_fel_vpp* vpp,const AVFrame* source,
    pl_chroma_location chroma,const dvbridge_fel_vpp_image** out) {
 lastChroma=chroma;return dvbridge_fel_vpp_acquire(vpp,source,out);
}
void dvbridge_fel_vpp_release(dvbridge_fel_vpp* vpp,const dvbridge_fel_vpp_image* image) {
 assert(vpp && vpp->leased && image==&vpp->image); vpp->leased=false; --scaledImages;
}
bool dvbridge_dmabuf_import(dvbridge_dmabuf* out,const AVFrame* source) {
 if(!importWorks) return false;
 out->layout=DVBRIDGE_P010; out->planes[0].texture=source->pixels; ++importedImages; ++createdImages; return true;
}
bool dvbridge_dmabuf_map(dvbridge_dmabuf* out,const AVFrame* source) {
 if(!importWorks) return false;
 out->mapping=new AVFrame(*source); out->mapping->data[0]=reinterpret_cast<unsigned char*>(uintptr_t(source->pixels));
 out->width=32; out->height=24; ++mappedPictures; return true;
}
bool dvbridge_dmabuf_import_mapped(dvbridge_dmabuf* out) {return dvbridge_dmabuf_import(out,out->mapping);}
void dvbridge_dmabuf_release(dvbridge_dmabuf* out) {if(out->planes[0].texture) --importedImages; delete out->mapping; *out={};}
struct dvbridge_gl_frame {};
bool dvbridge_gl_frame_import(dvbridge_gl_frame*,void*,dvbridge_gl_layout,int,int,const dvbridge_gl_plane*) {return probeWorks;}
void dvbridge_gl_frame_release(dvbridge_gl_frame*) {}
struct GL {void* gpu{};};
struct Context {bool FELHardwareUpscaling(uint64_t) {return true;} void Poll(bool) {}
 bool AsyncPreparation(uint64_t) {return false;}};
class CDVBridgeGLES {
public:
 enum class FrameStatus {Failed,Pending,Busy,Ready,Reused,Unsupported};
 struct Layer {
  dvbridge_gl_layout layout{}; int width{64},height{48}; dvbridge_gl_plane planes[3]{};
  double pts{42}; DVBRIDGE::SourceBinding binding{7,1,3}; std::shared_ptr<void> lease;
  AVChromaLocation chromaLocation{AVCHROMA_LOC_UNSPECIFIED};
 };
 struct {bool asyncEligible{};} m_submission;
 bool m_asyncEligible{},m_felVppEnabled{},m_felVppReported{};
 bool m_hardwareFELVpp{};
 uint64_t m_felVppStream{};
 int m_hardwareFELFilter{-1};
 pl_chroma_location m_hardwareFELChroma{PL_CHROMA_UNKNOWN};
 DVBRIDGE::SourceBinding m_hardwareBinding{};
 std::shared_ptr<void> m_hardwareLease;
 std::weak_ptr<AVFrame> m_hardwareFrame;
 void ClearFELPrefetch() {}
 FrameStatus TakeFELPrefetch(const std::shared_ptr<AVFrame>&,DVBRIDGE::SourceBinding,
     const DVBRIDGE::OutputPreferences&,std::shared_ptr<dvbridge_fel_vpp>&,
     const dvbridge_fel_vpp_image*&) {assert(false && "Legacy test must not enter prefetch");return FrameStatus::Unsupported;}
 std::vector<std::shared_ptr<void>> m_rawELCache;
 uint64_t m_rawELImports{},m_rawELHits{};
 std::shared_ptr<dvbridge_fel_vpp> m_felVpp;
 std::shared_ptr<Context> m_context=std::make_shared<Context>();
 GL gl; GL* m_gl=&gl;
 // The render boundary holds the lease just as the actual source-read owner does.
 Layer submitted{}; bool hasEL{},packed{},async{}; int filter{-1},submissions{};
 const dvbridge_policy* policy{}; FrameStatus renderStatus{FrameStatus::Ready};
 FrameStatus PrepareFrame(const Layer&,const Layer* el,const CDVMetadataBuffer&,dvbridge_geometry,
     const DVBRIDGE::OutputPreferences& p,bool allowPacked,const dvbridge_policy* selected,bool allowAsync) {
  ++submissions; hasEL=el; submitted=el?*el:Layer{}; filter=p.felUpscaling;
  packed=allowPacked; async=allowAsync; policy=selected; return renderStatus;
 }
 FrameStatus PrepareHardwareFrame(const Layer& base,std::shared_ptr<AVFrame> enhancement,
     DVBRIDGE::SourceBinding enhancementBinding,const CDVMetadataBuffer& metadata,dvbridge_geometry geometry,
     const DVBRIDGE::OutputPreferences& preferences,bool allowPacked,const dvbridge_policy* selected,bool allowAsync) METHOD
};
int main() {
 using Status=CDVBridgeGLES::FrameStatus;
 AVHWFramesContext frames{}; AVBufferRef hw{reinterpret_cast<unsigned char*>(&frames)};
 CDVBridgeGLES::Layer base; CDVMetadataBuffer metadata; dvbridge_policy selected;
 auto el=std::make_shared<AVFrame>(); el->hw_frames_ctx=&hw;
 std::weak_ptr<AVFrame> retained=el;
 {
  CDVBridgeGLES r; DVBRIDGE::OutputPreferences p;
  auto run=[&](bool packed=true,bool async=true) {
   return r.PrepareHardwareFrame(base,el,base.binding,metadata,{},p,packed,&selected,async);
  };
  assert(run()==Status::Ready);
  assert(lastChroma==PL_CHROMA_TOP_LEFT);
  assert(r.hasEL && r.submitted.layout==DVBRIDGE_Y416 && r.submitted.width==64 && r.submitted.height==48);
  assert(r.submitted.planes[0].texture==17 && r.submitted.binding==base.binding && r.submitted.pts==42);
  assert(r.filter==0 && r.packed && r.async && r.policy==&selected);
  assert(r.m_hardwareFELVpp);
  auto first=r.submitted.lease;
  assert(run()==Status::Ready && r.submitted.lease==first); // Same policy/frame reuses its import.
  r.submitted.lease.reset();first.reset();selected.mode=1;
  assert(run()==Status::Ready && lastChroma==PL_CHROMA_TOP_LEFT);
  r.submitted.lease.reset();selected.mode=0;
  assert(run()==Status::Ready && lastChroma==PL_CHROMA_TOP_LEFT);
  first=r.submitted.lease;
  r.renderStatus=Status::Pending;
  p.felUpscaling=1; ++p.revision;
  assert(run()==Status::Pending); // Policy switch may not reuse a full-size VPP result.
  assert(r.hasEL && r.submitted.layout==DVBRIDGE_P010 && r.submitted.width==32 && r.submitted.height==24);
  assert(!r.m_hardwareFELVpp);
  assert(r.submitted.planes[0].texture==17 && r.submitted.binding==base.binding && r.filter==1);
  assert(r.submitted.lease!=first && scaledImages==1); // Previous GPU owner still retains its VPP image.
  first.reset(); assert(scaledImages==0);
  auto nearest=r.submitted.lease;
  assert(run(false,false)==Status::Pending && r.submitted.lease==nearest);
  assert(!r.packed && !r.async && r.policy==&selected);
  p.felUpscaling=0; ++p.revision;
  assert(run()==Status::Pending && r.submitted.layout==DVBRIDGE_Y416 && r.submitted.width==64);
  assert(r.submitted.lease!=nearest && importedImages==1);
  nearest.reset(); assert(importedImages<=1);
  // New picture, stream and source revision must each replace the cached residual.
  for(int change=0;change<3;++change) {
   auto prior=r.submitted.lease;
   if(change==0) ++base.binding.picture;
   if(change==1) ++base.binding.stream;
   if(change==2) ++base.binding.revision;
   // Retire the old picture before the two-slot VPP owner is reused.
   r.submitted.lease.reset(); prior.reset();
   el=std::make_shared<AVFrame>(*el); ++el->pixels;
   assert(run()==Status::Pending && r.submitted.planes[0].texture==18u+change);
   assert(r.submitted.binding==base.binding);
  }
  assert(retained.expired()); // The first decoded frame has now retired.
 }
 assert(retained.expired() && importedImages==0 && scaledImages==0);
 {
  CDVBridgeGLES r; DVBRIDGE::OutputPreferences p{1,10};
  auto run=[&](DVBRIDGE::SourceBinding binding) {
   return r.PrepareHardwareFrame(base,el,binding,metadata,{},p,false,nullptr,true);
  };
  assert(run(base.binding)==Status::Ready && r.hasEL);
  const int accepted=r.submissions;
  auto wrong=base.binding; ++wrong.picture;
  r.m_submission.asyncEligible=r.m_asyncEligible=true;
  assert(run(wrong)==Status::Failed && r.submissions==accepted);
  assert(!r.m_submission.asyncEligible && !r.m_asyncEligible);
  ++base.binding.picture; ++el->pts; // A matched ID is insufficient if PTS differs.
  assert(run(base.binding)==Status::Failed && r.submissions==accepted); --el->pts;
  importWorks=false;
  assert(run(base.binding)==Status::Failed && r.submissions==accepted); // Never submit an old/empty residual.
  importWorks=true;
  assert(run(base.binding)==Status::Ready && r.hasEL && r.submitted.planes[0].texture==el->pixels);
 }
 assert(importedImages==0 && scaledImages==0);
 // VPP failures retain the full residual for nearest GPU; non-FEL never gets VPP enlargement.
 for(bool fel : {false,true}) {
  CDVBridgeGLES r; DVBRIDGE::OutputPreferences p; metadata.fel=fel;
  vppStatus=DVBRIDGE_VPP_FAILED;
  assert(r.PrepareHardwareFrame(base,el,base.binding,metadata,{},p,false,nullptr,false)==Status::Ready);
  assert(r.hasEL && r.submitted.layout==DVBRIDGE_P010 && r.submitted.width==32);
  assert(r.submitted.planes[0].texture==el->pixels);
  if(fel) assert(!r.m_felVppEnabled);
 }
 vppStatus=DVBRIDGE_VPP_OK;
 {
  CDVBridgeGLES r; DVBRIDGE::OutputPreferences p; metadata.fel=true;
  vppStatus=DVBRIDGE_VPP_BUSY;
  assert(r.PrepareHardwareFrame(base,el,base.binding,metadata,{},p,false,nullptr,true)==Status::Ready);
  assert(r.hasEL && r.submitted.layout==DVBRIDGE_P010 && !r.m_hardwareFELVpp && r.m_felVppEnabled);
  vppStatus=DVBRIDGE_VPP_OK; ++base.binding.picture;
  assert(r.PrepareHardwareFrame(base,el,base.binding,metadata,{},p,false,nullptr,true)==Status::Ready);
  assert(r.submitted.layout==DVBRIDGE_Y416 && r.m_hardwareFELVpp);
 }
 assert(importedImages==0 && scaledImages==0);
 {
  CDVBridgeGLES r; DVBRIDGE::OutputPreferences p{1,20};
  assert(r.PrepareHardwareFrame(base,nullptr,{},metadata,{},p,true,&selected,true)==Status::Ready);
  assert(!r.hasEL && r.filter==1 && r.packed && r.async && r.policy==&selected);
 }
 assert(importedImages==0 && scaledImages==0);
 {
  CDVBridgeGLES r; DVBRIDGE::OutputPreferences p{1,40};
  const int before=createdImages, maps=mappedPictures;
  for(int i=0;i<3;++i) {
   ++base.binding.picture;
   assert(r.PrepareHardwareFrame(base,el,base.binding,metadata,{},p,false,nullptr,true)==Status::Ready);
  }
  assert(mappedPictures-maps==3);
  assert(createdImages-before==1);
  assert(r.m_rawELCache.size()==1);
  auto inFlight=r.submitted.lease;
  for(unsigned i=1;i<=40;++i) {
   ++base.binding.picture; el=std::make_shared<AVFrame>(*el); el->pixels=100+i;
   assert(r.PrepareHardwareFrame(base,el,base.binding,metadata,{},p,false,nullptr,true)==Status::Ready);
   assert(r.m_rawELCache.size()<=32);
  }
  assert(importedImages==33);
  inFlight.reset(); assert(importedImages==32);
 }
 assert(importedImages==0 && scaledImages==0);
}
'''.replace('METHOD', method).replace('SOURCECHROMA', body(source, 'pl_chroma_location SourceChroma('))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test.cpp').write_text(program)
            build = subprocess.run(['c++', '-std=c++20', '-fsanitize=address,undefined',
                                    str(root / 'test.cpp'), '-o', str(root / 'test')],
                                   capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(root / 'test')], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == '__main__':
    unittest.main()
