"""A scanout still refreshing the final picture cannot hold EOF open."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from shipped_kodi import shipped_code
from test_native_video_source import body


class VideoPresentationDrain(unittest.TestCase):
    def test_waits_for_new_source_through_scanout_and_ignores_redraws(self):
        window = shipped_code('xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp')
        bridge = shipped_code('xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp')
        manager = shipped_code('xbmc/cores/VideoPlayer/VideoRenderers/RenderManager.cpp')
        program = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <deque>
#include <mutex>
#include <optional>
namespace DVBRIDGE {
struct SourceBinding {
  unsigned stream{}, picture{}, revision{};
  bool operator==(const SourceBinding&) const = default;
  bool Valid() const { return stream && picture && revision; }
};
}
struct DRM { virtual ~DRM() = default; };
struct CDRMAtomic : DRM { bool busy{}; bool HasPendingCB1Page() const { return busy; } };
struct Handle { DRM* driver; DRM* get() const { return driver; } };
struct PlayerLedPage { DVBRIDGE::SourceBinding decoded; };
struct CDVBridgeGLES {
  struct Queue {
    struct Slot { std::optional<PlayerLedPage> frame; };
    std::array<Slot, 2> slots;
    std::deque<unsigned> queue;
  } cpu;
  Queue* m_playerLedCpu{&cpu};
  bool PlayerLedCpuPending() const { return !cpu.queue.empty(); }
  bool PlayerLedCpuHasNewPicture(DVBRIDGE::SourceBinding displayed) const @@FIFO@@
};
struct CWinSystemGbm {
  CDRMAtomic driver;
  bool retires{true};
  bool CompleteDVBridgePage(int) {
    if (driver.busy && !retires) return false;
    driver.busy = false;
    return true;
  }
};
struct CWinSystemGbmGLESContext : CWinSystemGbm {
  Handle m_DRM{&driver};
  DVBRIDGE::SourceBinding m_preparedSource{}, m_cb1PageSource{}, m_cb1DisplayedSource{};
  std::optional<PlayerLedPage> m_playerLedPage;
  double m_playerLedPagePts{};
  bool preparing{}, m_cb1SourcePreparing{}, m_dvFrame{}, m_dvActivating{};
  CDVBridgeGLES bridge;
  CDVBridgeGLES* m_dvBridge{&bridge};
  bool FinishPlayerLedFrame(const PlayerLedPage& frame, double) {
    m_cb1DisplayedSource = frame.decoded;
    return true;
  }
  void RejectDVOutputSurface() { assert(false); }
  bool HasPendingCB1VideoPresentation() const @@WINDOW@@
  void TrackCB1VideoPage(bool pending) @@TRACK@@
  bool CompleteDVBridgePage(int timeoutMs) @@COMPLETE@@
};
struct CRenderManager {
  enum { PRESENT_IDLE, PRESENT_FRAME };
  std::mutex m_presentlock;
  std::deque<int> m_queued;
  int m_presentstep{PRESENT_IDLE};
  bool m_cb1PresentPending{}, m_cb1OutputPending{};
  bool HasPendingVideoPresentation() @@MANAGER@@
};
int main() {
  CWinSystemGbmGLESContext window;
  CRenderManager manager;
  auto pending = [&] {
    manager.m_cb1PresentPending = window.preparing;
    manager.m_cb1OutputPending = window.HasPendingCB1VideoPresentation();
    return manager.HasPendingVideoPresentation();
  };
  const DVBRIDGE::SourceBinding penultimate{1, 240, 1}, last{1, 241, 1};
  window.m_preparedSource = penultimate;
  window.TrackCB1VideoPage(false);
  window.m_preparedSource = last;
  window.preparing = window.m_cb1SourcePreparing = true;
  assert(pending()); // Final source awaits asynchronous preparation.
  window.preparing = false;
  assert(pending()); // Synchronous OSD preparation can still return Busy.
  window.m_cb1SourcePreparing = false;
  window.m_dvFrame = true;
  assert(pending()); // A synchronous frame is ready but its flip has not happened.
  window.m_dvFrame = false;
  window.driver.busy = true;
  window.TrackCB1VideoPage(true);
  assert(pending()); // The first flip of that picture has yet to retire.
  window.retires = false;
  assert(!window.CompleteDVBridgePage(0) && pending());
  window.retires = true;
  assert(window.CompleteDVBridgePage(0) && !pending());
  window.driver.busy = true;
  window.TrackCB1VideoPage(true);
  window.preparing = window.m_cb1SourcePreparing = window.m_dvFrame = true;
  assert(!pending()); // Repeated preparation and page of a displayed picture.
  window.preparing = window.m_cb1SourcePreparing = window.m_dvFrame = false;
  window.m_playerLedPage = {{1, 242, 1}};
  assert(pending()); // A new player-led page is independent of the old EGL page.
  assert(window.CompleteDVBridgePage(0) && !pending());
  window.m_preparedSource = last;
  window.TrackCB1VideoPage(false);
  auto& cpu = window.bridge.cpu;
  cpu.slots[0].frame = {last};
  cpu.queue.push_back(0);
  assert(!pending()); // A CPU-packed GUI refresh of the same frame.
  cpu.slots[1].frame = {{1, 241, 2}};
  cpu.queue.push_back(1);
  assert(pending()); // A new decoder epoch behind a duplicate FIFO head.
  cpu.queue.clear();
  manager.m_queued.push_back(1);
  assert(pending());
  manager.m_queued.clear();
  manager.m_presentstep = CRenderManager::PRESENT_FRAME;
  assert(pending()); // Ordinary Kodi presentation state still gates EOF.
}
'''.replace('@@WINDOW@@', body(window, 'bool CWinSystemGbmGLESContext::HasPendingCB1VideoPresentation() const')).replace(
            '@@MANAGER@@', body(manager, 'bool CRenderManager::HasPendingVideoPresentation()'))
        program = program.replace('@@TRACK@@', body(window, 'void CWinSystemGbmGLESContext::TrackCB1VideoPage('))
        program = program.replace('@@COMPLETE@@', body(window, 'bool CWinSystemGbmGLESContext::CompleteDVBridgePage('))
        program = program.replace('@@FIFO@@', body(bridge, 'bool CDVBridgeGLES::PlayerLedCpuHasNewPicture('))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'check.cpp'
            source.write_text(program)
            binary = root / 'check'
            subprocess.run(['c++', '-std=c++20', '-DHAVE_DVBRIDGE', str(source),
                            '-o', str(binary)], check=True, cwd=root)
            subprocess.run([str(binary)], check=True, cwd=root)
