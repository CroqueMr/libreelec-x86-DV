"""Probe the same GBM buffer used to route a newly swapped output surface."""
import unittest

from test_native_video_source import TREE, body
from test_process_info_metadata import run


class GbmFrontBufferTests(unittest.TestCase):
    def test_float_probe_reuses_the_front_buffer_without_a_second_lock(self):
        gbm = TREE / 'xbmc/windowing/gbm'
        method = body((gbm / 'WinSystemGbmEGLContext.cpp').read_text(),
                      'bool CWinSystemGbmEGLContext::SetVideoOutput(')
        start = method.index('    if (!m_eglContext.TrySwapBuffers()')
        end = method.index('  // No new drawable exists', start)
        surface = (gbm / 'GBMUtils.cpp').read_text()
        access = body(surface, 'CGBMSurface::GetLockedFrontBuffer()')
        program = r'''
#include <cassert>
#include <cstdint>
#include <memory>
#include <queue>

struct gbm_bo {};
unsigned gbm_bo_get_format(gbm_bo*) { return 1; }
constexpr int DRM_FORMAT_MOD_LINEAR=0, LOGINFO=1;
namespace KODI::WINDOWING::GBM { enum { QUIRK_NEEDSPRIMARY }; }
struct CLog { template<class... T> static void LogF(T...) {} };

struct Surface
{
  struct Buffer { gbm_bo* value; gbm_bo* Get() const { return value; } };
  std::queue<std::unique_ptr<Buffer>> m_buffers;
  std::unique_ptr<Buffer> m_scanoutBuffer;
  gbm_bo buffer;
  int locks=0;
  bool frameReady=false;
  Surface& GetDevice(){return *this;}
  Surface& GetSurface(){return *this;}
  Buffer& LockFrontBuffer()
  {
    ++locks;
    m_buffers.push(std::make_unique<Buffer>(Buffer{frameReady ? &buffer : nullptr}));
    frameReady=false;
    return *m_buffers.back();
  }
  gbm_bo* GetLockedFrontBuffer() const ACCESS
};
struct EGL { Surface& surface; bool TrySwapBuffers(){surface.frameReady=true;return true;} };
struct Plane { void SetFormat(unsigned){} void SetModifier(int){} };
struct DRM
{
  virtual ~DRM()=default;
  Plane plane;
  bool HasQuirk(int){return false;}
  void SetActive(bool){}
  Plane* GetGuiPlane(){return nullptr;}
  Plane* GetVideoPlane(){return &plane;}
};
struct CDRMAtomic:DRM
{
  bool accepts=true;
  gbm_bo* tested=nullptr;
  bool TestFramebuffer(gbm_bo* bo){tested=bo;return bo && accepts;}
};
struct CWinSystemGbm {bool SetVideoOutput(void*){return true;}};
struct Window:CWinSystemGbm
{
  Surface surface;
  EGL m_eglContext{surface};
  Surface* m_GBM=&surface;
  std::shared_ptr<CDRMAtomic> drm=std::make_shared<CDRMAtomic>();
  std::shared_ptr<DRM> m_DRM=drm;
  bool m_dvOutputSurface=false;
  bool HasFloatOutput() const{return true;}
  bool Configure(bool swapped)
  {
    void* videoPicture=nullptr;
    const int bitDepth=10;
    auto reject=[](){return false;};
    if(swapped){
    PROBE
    return true;
  }
};
int main()
{
  Window window;
  assert(window.Configure(true));
  assert(window.surface.locks==1 && window.drm->tested==&window.surface.buffer);
  assert(window.Configure(false));
  assert(window.surface.locks==1 && window.drm->tested==&window.surface.buffer);
  window.drm->accepts=false;
  assert(!window.Configure(false));
  assert(window.surface.locks==1 && window.drm->tested==&window.surface.buffer);
  Window unavailable;
  assert(!unavailable.Configure(false));
  assert(unavailable.surface.locks==0);
  unavailable.surface.m_scanoutBuffer=std::make_unique<Surface::Buffer>(Surface::Buffer{&unavailable.surface.buffer});
  assert(unavailable.Configure(false));
  assert(unavailable.surface.locks==0 && unavailable.drm->tested==&unavailable.surface.buffer);
}
'''.replace('ACCESS', access).replace('PROBE', method[start:end])
        run(self, {'test.cpp': program})
