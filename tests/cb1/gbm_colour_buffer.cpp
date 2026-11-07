#include <cassert>
#include <memory>
#include <mutex>
#include <queue>
constexpr int LOGDEBUG=0;
struct CLog {template<class... T>static void Log(T...) {}};
struct gbm_bo {bool locked=false;};
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
    gbm_surface* surface;gbm_bo* buffer;
    explicit CGBMSurfaceBuffer(gbm_surface* s):surface(s),buffer(gbm_surface_lock_front_buffer(s)){}
    ~CGBMSurfaceBuffer(){if(buffer)gbm_surface_release_buffer(surface,buffer);}
    gbm_bo* Get(){return buffer;}
  };
  gbm_surface pool;gbm_surface* m_surface=&pool;
  std::queue<std::unique_ptr<CGBMSurfaceBuffer>> m_buffers;
  std::unique_ptr<CGBMSurfaceBuffer> m_scanoutBuffer,m_pendingBuffer;
  Surface& GetDevice(){return *this;}Surface& GetSurface(){return *this;}
  CGBMSurfaceBuffer& LockFrontBuffer() @LOCK@
  gbm_bo* LockTransactionalBuffer() @PENDING@
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
  bool HasColorRangeTransition()const{return range;}
  bool LastPageAccepted()const{return lastAccepted;}
  void FlipPage(gbm_bo* bo,bool rendered,bool,bool async)override {
    ++calls;lastAsync=async;lastAccepted=accept;range=false;
    if(accept&&rendered){assert(bo&&bo->locked);displayed=bo;}
  }
};
struct Manager {int dirty=0;Manager& GetWindowManager(){return *this;}void MarkDirty(){++dirty;}};
struct CServiceBroker {static Manager* GetGUI(){static Manager value;return &value;}};
struct Bridge{void Disable(){assert(false);}};
struct Window {
  std::shared_ptr<DRM> m_DRM=std::make_shared<CDRMAtomic>();
  std::shared_ptr<Surface> m_GBM=std::make_shared<Surface>();
  std::shared_ptr<Bridge> m_videoLayerBridge;
  bool ConnectorPreferencesAllowed(){return true;}
  void DeferConnectorPreferences(){assert(false);}
  void UpdateDriverLimitedRange(){}void RetryConnectorProperties(){}
  void FlipPage(bool rendered,bool videoLayer,bool async) @FLIP@
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
  displayed=nullptr;
}
