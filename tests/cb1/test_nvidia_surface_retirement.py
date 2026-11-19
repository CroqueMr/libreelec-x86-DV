"""Replay NVIDIA GBM/EGL teardown ordering against the shipped Kodi methods."""

from pathlib import Path
import subprocess
import tempfile
import unittest

from test_native_video_source import TREE, body


class NvidiaSurfaceRetirement(unittest.TestCase):
    def test_retire_the_matching_buffers_before_destroying_the_drawable(self):
        gbm = TREE / "xbmc/windowing/gbm"
        egl_source = (TREE / "xbmc/utils/EGLUtils.cpp").read_text()
        gbm_source = (gbm / "GBMUtils.cpp").read_text()
        window_source = (gbm / "WinSystemGbmEGLContext.cpp").read_text()

        choose = body(egl_source, "bool CEGLContextUtils::ChooseConfig(")
        snippets = {
            "drain": body(gbm_source, "void CGBMUtils::CGBMDevice::ReleaseSurfaceBuffers("),
            "destroy_all": body(egl_source, "bool CEGLContextUtils::DestroyRetiredContext("),
            "destroy_egl": body(egl_source, "bool CEGLContextUtils::DestroyAfterRelease("),
            "shutdown": body(window_source, "bool CWinSystemGbmEGLContext::DestroyNvidiaWindowSystem("),
            "config_error": choose[choose.index("  if (errorMsg)"):choose.index("  EGLConfig match")],
            "ordinary_egl": body(egl_source, "bool CEGLContextUtils::DestroySurfaceAfterRelease("),
            "ordinary_window": body(window_source, "bool CWinSystemGbmEGLContext::DestroyOutputSurface("),
            "gbm": body(gbm_source, "void CGBMUtils::CGBMDevice::CompleteOutputSurface("),
            "egl": body(egl_source, "bool CEGLContextUtils::CompleteOutputSurface("),
            "window": body(window_source, "bool CWinSystemGbmEGLContext::CompleteDVOutputSurface("),
        }
        program = r"""
#include <cassert>
#include <functional>
#include <memory>
#include <string>
#include <vector>

constexpr int EGL_TRUE = 1, EGL_NO_SURFACE = 0, EGL_NO_CONTEXT = 0, EGL_NO_DISPLAY = 0;
enum { LOGERROR, LOGINFO };
struct CEGLUtils { static void Log(int, const char*) {} };
constexpr int oldSurface = 1, newSurface = 2;
constexpr int QUIRK_NVIDIA_EGL_GBM = 1;
std::vector<std::string> events;
bool alive[3]{};
bool rebindWorks, destroyWorks, unbindWorks;

void Mark(const char* action, int surface)
{
  events.emplace_back(action + std::to_string(surface));
}

int eglDestroySurface(int, int surface)
{
  assert(alive[surface]);
  Mark("destroy ", surface);
  if (!destroyWorks)
    return 0;
  alive[surface] = false;
  return EGL_TRUE;
}

int eglMakeCurrent(int, int draw, int read, int context)
{
  assert(draw == EGL_NO_SURFACE && read == EGL_NO_SURFACE && context == EGL_NO_CONTEXT);
  events.emplace_back("unbind");
  return unbindWorks ? EGL_TRUE : 0;
}

int eglDestroyContext(int, int) { return EGL_TRUE; }

int eglTerminate(int)
{
  events.emplace_back("terminate");
  return EGL_TRUE;
}

struct CEGLContextUtils
{
  bool m_outputSurfaceTransaction{true};
  int m_eglSurface{newSurface}, m_priorSurface{oldSurface};
  int m_eglDisplay{1}, m_eglContext{1}, m_eglUploadContext{2};
  int m_eglConfig{}, m_priorConfig{}, m_eglHDRConfig{}, m_priorHDRConfig{};
  struct RetainedContext
  {
    int display, context, uploadContext, surface, priorSurface;
  };

  static bool DestroyRetiredContext(RetainedContext& state,
                                    const std::function<void()>& releaseBuffers) @destroy_all@
  bool DestroyAfterRelease(const std::function<void()>& releaseBuffers) @destroy_egl@
  void Destroy() { events.emplace_back("premature display destruction"); }
  bool ConfigQueryFailed(bool preserveSurface)
  {
    const char* errorMsg = "eglChooseConfig failed";
    const bool probe = false, hdr = false, floating = false;
    @config_error@
    return true;
  }

  bool CompleteOutputSurface(bool presented,
                             const std::function<void()>& releaseBuffers = {}) @egl@
  bool DestroySurfaceAfterRelease(const std::function<void()>& releaseBuffers) @ordinary_egl@
  bool BindContext()
  {
    Mark("bind ", m_eglSurface);
    return true;
  }
  void DestroySurface()
  {
    eglDestroySurface(m_eglDisplay, m_eglSurface);
    m_eglSurface = EGL_NO_SURFACE;
  }
  bool BindPriorOutputSurface()
  {
    Mark("rebind ", m_priorSurface);
    return rebindWorks;
  }
};

struct CGBMUtils
{
  struct CGBMDevice
  {
    struct Surface
    {
      int id{};
      int buffers{3};

      void ReleaseBuffers()
      {
        if (!buffers)
          return;
        Mark(alive[id] ? "release " : "release after EGL ", id);
        buffers = 0;
      }
    };
    struct Deleter
    {
      bool releaseBuffers{true};
      void operator()(Surface* surface) const
      {
        if (releaseBuffers)
          surface->ReleaseBuffers();
        Mark("delete native ", surface->id);
        delete surface;
      }
    };

    std::unique_ptr<Surface, Deleter> m_surface{new Surface{newSurface}, Deleter{}};
    std::unique_ptr<Surface, Deleter> m_priorSurface{new Surface{oldSurface}, Deleter{}};
    void CompleteOutputSurface(bool presented) @gbm@
    void ReleaseSurfaceBuffers([[maybe_unused]] bool prior) @drain@
  } state;

  CGBMDevice& GetDevice() { return state; }
  void ReleaseSurfaceBuffers(bool prior = false) { state.ReleaseSurfaceBuffers(prior); }
};

struct CWinSystemGbmEGLContext
{
  struct Plane
  {
    void SetFormat(int) {}
    void SetModifier(int) {}
  };
  struct DRM
  {
    bool nvidia{true};
    bool HasQuirk(int quirk) const { return nvidia && quirk == QUIRK_NVIDIA_EGL_GBM; }
    bool FindVideoPlane(int, int) { return true; }
    bool FindGuiPlane(int, int) { return true; }
  };
  CEGLContextUtils m_eglContext;
  std::unique_ptr<CGBMUtils> m_GBM{new CGBMUtils};
  std::unique_ptr<DRM> m_DRM{new DRM};
  bool m_dvSurfacePending{true}, m_priorOutputVideo{};
  Plane* m_priorOutputPlane{};
  int m_priorOutputFormat{}, m_priorOutputModifier{};

  bool UsesNvidiaGbm() const { return m_DRM->HasQuirk(QUIRK_NVIDIA_EGL_GBM); }
  bool CompleteDVOutputSurface(bool submitted) @window@
  bool DestroyOutputSurface() @ordinary_window@
  bool DestroyNvidiaWindowSystem() @shutdown@
};

void Reset()
{
  events.clear();
  alive[oldSurface] = alive[newSurface] = true;
  rebindWorks = destroyWorks = unbindWorks = true;
}

void Accepted()
{
  Reset();
  CWinSystemGbmEGLContext window;
  // The driver's blocking commit returned; its physical notification comes later.
  destroyWorks = false;
  assert(!window.CompleteDVOutputSurface(true));
  assert((events == std::vector<std::string>{"release 1", "destroy 1"}));
  assert(alive[oldSurface] && alive[newSurface]);

  events.clear();
  destroyWorks = true;
  assert(window.CompleteDVOutputSurface(true));
  assert((events == std::vector<std::string>{"destroy 1", "delete native 1"}));
  assert(alive[newSurface]);
  assert(window.m_GBM->GetDevice().m_surface->buffers == 3);
}

void Rejected()
{
  Reset();
  CWinSystemGbmEGLContext window;
  rebindWorks = false;
  assert(!window.CompleteDVOutputSurface(false));
  assert((events == std::vector<std::string>{"rebind 1"}));
  assert(alive[oldSurface] && alive[newSurface]);
  assert(window.m_GBM->GetDevice().m_surface->buffers == 3);

  rebindWorks = true;
  destroyWorks = false;
  events.clear();
  assert(!window.CompleteDVOutputSurface(false));
  assert((events == std::vector<std::string>{"rebind 1", "release 2", "destroy 2"}));
  assert(alive[oldSurface] && alive[newSurface]);
  assert(window.m_GBM->GetDevice().m_priorSurface->buffers == 3);

  destroyWorks = true;
  events.clear();
  assert(window.CompleteDVOutputSurface(false));
  assert((events == std::vector<std::string>{"rebind 1", "destroy 2", "delete native 2"}));
  assert(alive[oldSurface] && window.m_GBM->GetDevice().m_surface->buffers == 3);
}

void OrdinaryRecreation()
{
  Reset();
  CWinSystemGbmEGLContext window;
  unbindWorks = false;
  assert(!window.DestroyOutputSurface());
  assert((events == std::vector<std::string>{"unbind"}));
  assert(alive[newSurface] && window.m_GBM->GetDevice().m_surface->buffers == 3);

  unbindWorks = true;
  destroyWorks = false;
  events.clear();
  assert(!window.DestroyOutputSurface());
  assert((events == std::vector<std::string>{"unbind", "release 2", "destroy 2", "bind 2"}));
  assert(alive[newSurface]);

  destroyWorks = true;
  events.clear();
  assert(window.DestroyOutputSurface());
  assert((events == std::vector<std::string>{"unbind", "destroy 2"}));
  assert(alive[oldSurface] && window.m_GBM->GetDevice().m_priorSurface->buffers == 3);
}

void Shutdown()
{
  Reset();
  CWinSystemGbmEGLContext pending;
  destroyWorks = false;
  assert(!pending.DestroyNvidiaWindowSystem());
  assert((events == std::vector<std::string>{"unbind", "release 1", "release 2", "destroy 1"}));
  assert(alive[oldSurface] && alive[newSurface]);

  events.clear();
  destroyWorks = true;
  assert(pending.DestroyNvidiaWindowSystem());
  assert((events == std::vector<std::string>{"unbind", "destroy 1", "destroy 2", "terminate"}));

  Reset();
  CWinSystemGbmEGLContext alias;
  alias.m_GBM->GetDevice().m_priorSurface.reset();
  alias.m_eglContext.m_priorSurface = newSurface;
  events.clear();
  assert(alias.DestroyNvidiaWindowSystem());
  assert((events == std::vector<std::string>{"unbind", "release 2", "destroy 2", "terminate"}));
}

void ConfigSelectionFailure()
{
  Reset();
  CWinSystemGbmEGLContext window;
  window.m_eglContext.m_outputSurfaceTransaction = false;
  assert(!window.m_eglContext.ConfigQueryFailed(true));
  assert(events.empty() && alive[newSurface]);
  assert(!window.m_eglContext.ConfigQueryFailed(false));
  assert((events == std::vector<std::string>{"premature display destruction"}));
}

void UnchangedAndAliased()
{
  Reset();
  CWinSystemGbmEGLContext unchanged;
  unchanged.m_DRM->nvidia = false;
  assert(unchanged.CompleteDVOutputSurface(true));
  assert((events == std::vector<std::string>{"destroy 1", "release after EGL 1", "delete native 1"}));

  Reset();
  CWinSystemGbmEGLContext alias;
  alias.m_GBM->GetDevice().m_priorSurface.reset();
  alias.m_eglContext.m_priorSurface = newSurface;
  events.clear();
  assert(alias.CompleteDVOutputSurface(true));
  assert(events.empty() && alias.m_GBM->GetDevice().m_surface->buffers == 3);
}

int main()
{
  Accepted();
  Rejected();
  OrdinaryRecreation();
  Shutdown();
  ConfigSelectionFailure();
  UnchangedAndAliased();
}
"""
        for name, source in snippets.items():
            program = program.replace(f"@{name}@", source)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "test.cpp"
            source.write_text(program)
            compile_result = subprocess.run(
                ["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror",
                 "-Wno-unused-parameter", str(source), "-o", str(root / "test")],
                capture_output=True,
                text=True,
            )
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            result = subprocess.run([str(root / "test")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
