#include <cassert>
#include <memory>
#include <mutex>
#include <queue>
#include <optional>
#include <string_view>
#include <utility>
#include "utils/DVBridgeLldv.h"
constexpr uint32_t DRM_FORMAT_XRGB8888=1, DRM_FORMAT_ARGB8888=2;
constexpr int LOGDEBUG=0, LOGWARNING=1;
struct CLog {template<class... T>static void Log(T...) {}};
struct gbm_bo {bool locked=false;};
unsigned gbm_bo_get_width(gbm_bo*) {return 3840;}
unsigned gbm_bo_get_height(gbm_bo*) {return 2160;}
uint32_t gbm_bo_get_format(gbm_bo*) {return DRM_FORMAT_XRGB8888;}
struct gbm_surface {gbm_bo pool[4];};
gbm_bo* displayed=nullptr;
gbm_bo* gbm_surface_lock_front_buffer(gbm_surface* surface) {
  for(auto& bo:surface->pool)if(!bo.locked){bo.locked=true;return &bo;}
  assert(false && "rejected frames must not exhaust the GBM pool");return nullptr;
}
bool gbm_surface_has_free_buffers(gbm_surface* surface) {
  for(auto& bo:surface->pool)if(!bo.locked)return true;return false;
}
void gbm_surface_release_buffer(gbm_surface*,gbm_bo* bo) {
  assert(bo!=displayed && "the accepted scanout must stay locked until replacement");
  assert(bo->locked);bo->locked=false;
}
std::once_flag flag;
struct Surface {
  struct CGBMSurfaceBuffer {
    gbm_surface* surface;gbm_bo* buffer;std::shared_ptr<void> lease;
    explicit CGBMSurfaceBuffer(gbm_surface* s):surface(s),buffer(gbm_surface_lock_front_buffer(s)){}
    CGBMSurfaceBuffer(gbm_bo* bo,std::shared_ptr<void> owner):surface(nullptr),buffer(bo),lease(std::move(owner)){}
    ~CGBMSurfaceBuffer(){if(surface && buffer)gbm_surface_release_buffer(surface,buffer);}
    gbm_bo* Get(){return buffer;}
  };
  gbm_surface pool;gbm_surface* m_surface=&pool;
  std::queue<std::unique_ptr<CGBMSurfaceBuffer>> m_buffers;
  std::unique_ptr<CGBMSurfaceBuffer> m_scanoutBuffer,m_pendingBuffer;
  Surface& GetDevice(){return *this;}Surface& GetSurface(){return *this;}
  CGBMSurfaceBuffer& LockFrontBuffer() @LOCK@
  gbm_bo* LockTransactionalBuffer() @PENDING@
  gbm_bo* AdoptTransactionalBuffer(gbm_bo* buffer,std::shared_ptr<void> lease) @ADOPT@
  void CompleteTransactionalBuffer(bool presented) @COMPLETE@
  void EndTransactionalMode() @END@
};
struct DRM {
  virtual ~DRM()=default;
  virtual void FlipPage(gbm_bo*,bool,bool,bool)=0;
  void ReleaseVideoPlane(){assert(false);}
  struct Plane{int GetFormat(){return 0;}int GetModifier(){return 0;}};
  Plane* GetGuiPlane(){assert(false);return nullptr;}
  void FindGuiPlane(int,int){assert(false);}
};
struct CDRMAtomic:DRM {
  bool range=false,accept=true,lastAccepted=false,lastAsync=false;
  int calls=0;
  bool clearHDR10Plus=false, modeset=false, pending=false;
  bool fenceReady=false;
  gbm_bo* queued=nullptr;
  uint64_t requested=0, active=0;
  struct Connector {
    std::optional<uint64_t> GetPropertyEnumValue(std::string_view key,std::string_view name) const
    {
      assert(key=="CB1_LLDV_FORMAT");
      if(name=="YCbCr 4:2:2 10 useful bits") return 1;
      if(name=="YCbCr 4:2:2 12 bits") return 2;
      if(name=="YCbCr 4:2:2 10 bits forced") return 3;
      return {};
    }
  } connector;
  Connector* GetConnector() {return &connector;}
  bool IsSDRRestorePending() const {return false;}
  void AllowModeset() {modeset=true;}
  void StageHDR10Plus(std::nullopt_t,uint64_t) {clearHDR10Plus=true;}
  bool FlipPageTransactional(gbm_bo* bo,bool restore=false,bool async=false)
  {
    assert(!restore);
    ++calls;
    const bool cleared=std::exchange(clearHDR10Plus,false);
    if(bo) assert(cleared);
    if(!bo || !accept) {requested=active;return false;}
    assert(bo->locked);
    if(async)
    {
      assert(requested==active && !modeset);
      pending=true;queued=bo;return true;
    }
    if(requested!=active) assert(modeset);
    modeset=false;
    active=requested;
    displayed=bo;
    return true;
  }
  bool HasPendingCB1Page()const{return pending;}
  bool CompleteCB1Page(int)
  {
    if(!fenceReady)return false;
    assert(queued&&queued->locked);
    displayed=std::exchange(queued,nullptr);pending=false;return true;
  }
  bool HasColorRangeTransition()const{return range;}
  bool LastPageAccepted()const{return lastAccepted;}
  void FlipPage(gbm_bo* bo,bool rendered,bool,bool async)override {
    ++calls;lastAsync=async;lastAccepted=accept;range=false;
    if(accept&&rendered){assert(bo&&bo->locked);displayed=bo;}
  }
};
struct CDVBridgeState {
  bool captured=false;
  bool Captured() const {return captured;}
  bool CapturePlayerLed(CDRMAtomic&) {captured=true;return true;}
  bool StagePlayerLed(CDRMAtomic& drm,uint64_t format) {drm.requested=format;return true;}
};
struct Manager {int dirty=0;Manager& GetWindowManager(){return *this;}void MarkDirty(){++dirty;}};
struct CServiceBroker {static Manager* GetGUI(){static Manager value;return &value;}};
struct Bridge{void Disable(){assert(false);}};
struct Window {
  std::mutex m_lldvEdidMutex;
  DVBRIDGE::LldvTransport m_lldvRejected{};
  std::shared_ptr<DRM> m_DRM=std::make_shared<CDRMAtomic>();
  std::shared_ptr<Surface> m_GBM=std::make_shared<Surface>();
  std::shared_ptr<Bridge> m_videoLayerBridge;
  bool ConnectorPreferencesAllowed(){return true;}
  void DeferConnectorPreferences(){assert(false);}
  void UpdateDriverLimitedRange(){}void RetryConnectorProperties(){}
  void FlipPage(bool rendered,bool videoLayer,bool async) @FLIP@
  bool CompleteDVBridgePage(int timeoutMs=0) @PAGE@
  bool StageTransportPreferences() {return true;}
  DVBRIDGE::LldvConnectorStatus GetLldvConnectorStatus() const
  {
    using namespace DVBRIDGE;
    const auto& drm=static_cast<const CDRMAtomic&>(*m_DRM);
    LldvConnectorStatus status;
    status.connectorId=17;status.currentTiming=true;status.timingCommitted=true;
    status.sink.status=DV_EDID_LLDV_ONLY;status.sink.lldv_422=true;
    status.display.status=LldvEdidStatus::Ready;
    status.driverFormats=LLDV_422;
    status.active=static_cast<LldvFormat>(drm.active);
    return status;
  }
  bool FlipPlayerLedPage(CDVBridgeState& state, const DVBRIDGE::LldvTransport& packed,
                         bool async=false,gbm_bo* carrier=nullptr,std::shared_ptr<void> lease={}) @LLDV@
};
int main(){
  Window window;auto drm=std::dynamic_pointer_cast<CDRMAtomic>(window.m_DRM);
  window.FlipPage(true,false,true);auto* original=displayed;
  assert(original&&original->locked&&drm->lastAsync);
  for(int i=0;i<8;++i){
    drm->range=true;drm->accept=false;window.FlipPage(true,false,true);
    assert(displayed==original&&original->locked);
    assert(!window.m_GBM->m_pendingBuffer);
  }
  drm->range=true;drm->accept=true;window.FlipPage(true,false,true);
  assert(displayed!=original&&displayed->locked&&!original->locked);
  assert(!drm->lastAsync && "colour replacement must finish before old buffers unlock");
  window.FlipPage(true,false,true);assert(drm->lastAsync&&displayed->locked);
  auto* borrowed=window.m_GBM->LockTransactionalBuffer();assert(borrowed);
  const int calls=drm->calls,dirty=CServiceBroker::GetGUI()->dirty;
  drm->range=true;window.FlipPage(true,false,true);
  assert(drm->calls==calls&&window.m_GBM->m_pendingBuffer->Get()==borrowed);
  assert(CServiceBroker::GetGUI()->dirty==dirty+1);
  window.m_GBM->CompleteTransactionalBuffer(false);
  using namespace DVBRIDGE;
  CDVBridgeState state;
  auto* before=displayed;
  assert(!window.FlipPlayerLedPage(state,{18,LldvFormat::Y422_10,false}));
  assert(!state.Captured() && displayed==before);
  drm->pending=true;
  assert(!window.FlipPlayerLedPage(state,{17,LldvFormat::Y422_10,false}));
  assert(!state.Captured() && displayed==before);
  drm->pending=false;
  drm->accept=false;
  assert(!window.FlipPlayerLedPage(state,{17,LldvFormat::Y422_10,false}));
  assert(state.Captured() && displayed==before && drm->active==0);
  drm->accept=true;
  assert(window.FlipPlayerLedPage(state,{17,LldvFormat::Y422_10,false}));
  auto* ten=displayed;
  assert(ten!=before && ten->locked && !before->locked && drm->active==1);
  drm->accept=false;
  assert(!window.FlipPlayerLedPage(state,{17,LldvFormat::Y422_12,false}));
  assert(displayed==ten && ten->locked && drm->active==1);
  drm->accept=true;
  assert(window.FlipPlayerLedPage(state,{17,LldvFormat::Y422_12,false}));
  assert(!ten->locked && displayed->locked && drm->active==2);
  auto* twelve=displayed;
  assert(window.FlipPlayerLedPage(state,{17,LldvFormat::Y422_12,false},true));
  assert(drm->pending && drm->queued && drm->queued->locked && displayed==twelve && twelve->locked);
  assert(!window.CompleteDVBridgePage() && displayed==twelve && twelve->locked);
  drm->fenceReady=true;
  assert(window.CompleteDVBridgePage() && displayed!=twelve && displayed->locked && !twelve->locked);
  auto* egl=displayed;
  auto cpu=std::make_shared<gbm_bo>();cpu->locked=true;
  auto* cpuBO=cpu.get();std::weak_ptr<gbm_bo> displayedLease=cpu;
  drm->fenceReady=false;
  assert(window.FlipPlayerLedPage(state,{17,LldvFormat::Y422_12,false},true,cpuBO,std::move(cpu)));
  assert(!displayedLease.expired() && displayed==egl && !window.CompleteDVBridgePage());
  drm->fenceReady=true;
  assert(window.CompleteDVBridgePage() && displayed==cpuBO && !displayedLease.expired() && !egl->locked);

  auto refused=std::make_shared<gbm_bo>();refused->locked=true;
  auto* refusedBO=refused.get();std::weak_ptr<gbm_bo> refusedLease=refused;
  drm->accept=false;
  assert(!window.FlipPlayerLedPage(state,{17,LldvFormat::Y422_12,false},true,refusedBO,std::move(refused)));
  assert(refusedLease.expired() && !displayedLease.expired() && displayed==cpuBO);
  drm->accept=true;
  assert(window.FlipPlayerLedPage(state,{17,LldvFormat::Y422_12,false}));
  assert(displayedLease.expired() && displayed!=cpuBO);
  displayed=nullptr;
}
