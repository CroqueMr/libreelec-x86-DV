"""Exercise Kodi's configuration retry at a cross-file DV output restore."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_native_video_source import TREE, body


class RendererOutputRestore(unittest.TestCase):
    def test_incoming_picture_waits_for_previous_output(self):
        renderer = (TREE / 'xbmc/cores/VideoPlayer/VideoRenderers/RenderManager.cpp').read_text()
        window = (TREE / 'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        configure = body(renderer, 'bool CRenderManager::Configure()')
        configure = configure[configure.index('std::unique_lock lock(m_statelock);'):
                              configure.index('  CreateRenderer();')]
        defer = ('return false;' if '::DeferRendererForOutputRestore()' not in window else
                 body(window, '::DeferRendererForOutputRestore()')[1:-1])
        cancel = ('{}' if 'void CRenderManager::CancelPendingConfigure()' not in renderer else
                  body(renderer, 'void CRenderManager::CancelPendingConfigure()'))
        worker = body(renderer, 'bool CRenderManager::Configure(const VideoPicture&')
        worker = worker[worker.index('const bool finished = m_stateEvent.Wait(1000ms);'):]
        teardown = body(renderer, 'void CRenderManager::UnInit()')
        teardown = teardown[teardown.index('std::unique_lock lock(m_statelock);'):
                            teardown.index('  m_overlays.UnInit();')]
        program = r'''
#include <cassert>
#include <chrono>
#include <memory>
#include <mutex>
using namespace std::chrono_literals;
struct Gui {
  int dirty = 0;
  Gui& GetWindowManager() { return *this; }
  void MarkDirty() { ++dirty; }
};
struct Window { virtual ~Window() = default; };
namespace KODI::WINDOWING::GBM {
struct CWinSystemGbmGLESContext : Window {
  bool m_dvStopPending = false, m_dvRollbackFailed = false;
  bool DeferRendererForOutputRestore();
};
}
using KODI::WINDOWING::GBM::CWinSystemGbmGLESContext;
struct CServiceBroker {
  static inline Gui gui;
  static inline CWinSystemGbmGLESContext win;
  static Gui* GetGUI() { return &gui; }
  static Window* GetWinSystem() { return &win; }
};
bool CWinSystemGbmGLESContext::DeferRendererForOutputRestore() { DEFER }
struct Event {
  bool set = false;
  bool Wait(std::chrono::milliseconds) { return set; }
  void Set() { set = true; }
  void notifyAll() { set = true; }
};
enum { STATE_UNCONFIGURED, STATE_CONFIGURING, STATE_CONFIGURED, PRESENT_IDLE, PRESENT_READY };
constexpr int LOGWARNING = 1;
struct CLog { template<class... T> static void Log(T...) {} };
struct Manager {
  int m_renderState = STATE_CONFIGURING, m_presentstep = PRESENT_READY;
  int deleted = 0, created = 0, displayed = 0;
  bool m_pRenderer = true;
  std::unique_ptr<int> m_pConfigPicture = std::make_unique<int>(17);
  Event m_stateEvent, m_presentevent;
  std::mutex m_statelock, m_presentlock, m_datalock;
  void DeleteRenderer() { ++deleted; m_pRenderer = false; CServiceBroker::win.m_dvStopPending = true; }
  void CancelPendingConfigure() CANCEL
  bool Worker() { WORKER
  void Teardown() { TEARDOWN }
  bool GuiConfigure() {
    CONFIGURE
    ++created;
    displayed = *m_pConfigPicture;
    m_pConfigPicture.reset();
    m_renderState = STATE_CONFIGURED;
    m_stateEvent.Set();
    return true;
  }
};
int main() {
  Manager m;
  assert(!m.GuiConfigure() && m.deleted == 1 && m.created == 0);
  assert(!m.GuiConfigure() && !m.m_stateEvent.set && m.m_pConfigPicture);
  assert(CServiceBroker::gui.dirty == 2 && m.deleted == 1);
  CServiceBroker::win.m_dvStopPending = false;
  assert(m.GuiConfigure() && m.Worker() && m.created == 1 && m.displayed == 17);

  Manager timeout;
  assert(!timeout.GuiConfigure());
  assert(!timeout.Worker());
  assert(timeout.m_renderState == STATE_UNCONFIGURED && !timeout.m_pConfigPicture);
  assert(timeout.m_presentstep == PRESENT_IDLE && timeout.m_presentevent.set);
  assert(!timeout.GuiConfigure() && timeout.created == 0);

  Manager stopped;
  assert(!stopped.GuiConfigure());
  stopped.Teardown();
  assert(stopped.m_stateEvent.set && !stopped.Worker() && !stopped.m_pConfigPicture);
  assert(!stopped.GuiConfigure() && stopped.created == 0);

  Manager fresh;
  fresh.m_pRenderer = false;
  CServiceBroker::win.m_dvStopPending = false;
  assert(fresh.GuiConfigure() && fresh.deleted == 0 && fresh.created == 1);

  Manager failedRestore;
  CServiceBroker::win.m_dvRollbackFailed = true;
  assert(failedRestore.GuiConfigure()); // Let the existing error path report a terminal rollback.
  assert(CServiceBroker::gui.dirty == 4);
}
'''.replace('DEFER', defer).replace('CANCEL', cancel).replace('WORKER', worker).replace(
            'TEARDOWN', teardown).replace('CONFIGURE\n', configure + '\n')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'test.cpp'
            source.write_text(program)
            binary = root / 'test'
            subprocess.run(['c++', '-std=c++17', '-DHAVE_DVBRIDGE', '-DHAVE_GBM', '-DHAS_GLES',
                            str(source), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)
